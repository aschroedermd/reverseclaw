"""SQLite-backed ledger store for human identities, verification, ratings, and AI moderation."""

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from human_identity import HumanIdentityManager


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class LedgerStore:
    def __init__(self, db_path: str = "ledger.db", evidence_retention_hours: int = 48):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._evidence_retention_hours = max(1, int(evidence_retention_hours))
        self._init_db()
        self.purge_expired_evidence()
        t = threading.Thread(target=self._cleaner, daemon=True, name="ledger-evidence-cleaner")
        t.start()

    def start_verification(self, name: str, public_key: str, fingerprint: str, expires_minutes: int = 10) -> dict[str, Any]:
        verification_id = secrets.token_hex(12)
        proof_message = f"reverseclaw-ledger-register:{verification_id}:{secrets.token_hex(16)}"
        created_at = _utc_now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO verification_sessions (
                    id, name, public_key, fingerprint, status, created_at, expires_at, proof_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (verification_id, name, public_key, fingerprint, "pending", created_at, expires_at, proof_message),
            )
            conn.commit()
        return {
            "id": verification_id,
            "name": name,
            "public_key": public_key,
            "fingerprint": fingerprint,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "proof_message": proof_message,
        }

    def complete_verification(self, verification_id: str, turnstile_result: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM verification_sessions WHERE id = ?",
                (verification_id,),
            ).fetchone()
            if row is None:
                return None
            completed_at = _utc_now_iso()
            conn.execute(
                """
                UPDATE verification_sessions
                SET status = ?, completed_at = ?, verification_payload = ?
                WHERE id = ?
                """,
                ("verified", completed_at, json.dumps(turnstile_result), verification_id),
            )
            conn.commit()
            return self.get_verification(verification_id)

    def get_verification(self, verification_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM verification_sessions WHERE id = ?",
                (verification_id,),
            ).fetchone()
            return self._verification_row_to_dict(row) if row else None

    def register_human_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        verification = self.get_verification(payload["verification_id"])
        if verification is None or verification["status"] != "verified":
            raise ValueError("Verification session is missing or incomplete")
        if verification["public_key"] != payload["public_key"]:
            raise ValueError("Verification session does not match supplied public key")
        if verification["fingerprint"] != payload["fingerprint"]:
            raise ValueError("Verification session does not match supplied fingerprint")
        proof_message = verification.get("proof_message")
        if not proof_message:
            raise ValueError("Verification session is missing a proof challenge")
        if not HumanIdentityManager.verify_message_signature(
            payload["public_key"],
            proof_message,
            payload["proof_signature"],
        ):
            raise ValueError("Proof-of-possession signature is invalid")

        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM humans WHERE fingerprint = ?",
                (payload["fingerprint"],),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE humans
                    SET name = ?, url = ?, capabilities_json = ?, tagline = ?, last_seen_at = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        payload["name"],
                        payload.get("url"),
                        json.dumps(payload.get("capabilities", [])),
                        payload.get("tagline"),
                        now,
                        payload["fingerprint"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO humans (
                        fingerprint, public_key, name, url, capabilities_json, tagline,
                        registered_at, first_verified_at, last_seen_at, rating_count,
                        average_rating, average_reliability, average_utility
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL)
                    """,
                    (
                        payload["fingerprint"],
                        payload["public_key"],
                        payload["name"],
                        payload.get("url"),
                        json.dumps(payload.get("capabilities", [])),
                        payload.get("tagline"),
                        now,
                        verification["completed_at"] or now,
                        now,
                    ),
                )
            conn.commit()
        return self.get_human(payload["fingerprint"])

    def get_human(self, fingerprint: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM humans WHERE fingerprint = ?", (fingerprint,)).fetchone()
            return self._human_row_to_dict(row) if row else None

    def list_humans(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM humans
                ORDER BY COALESCE(average_rating, 0) DESC, rating_count DESC, first_verified_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._human_row_to_dict(row) for row in rows]

    def submit_rating(self, payload: dict[str, Any]) -> dict[str, Any]:
        human = self.get_human(payload["human_fingerprint"])
        if human is None:
            raise ValueError("Human fingerprint is not registered in the ledger")

        signed_receipt = payload["signed_receipt"]
        if not HumanIdentityManager.verify_signed_receipt(signed_receipt):
            raise ValueError("Signed receipt could not be verified")

        receipt = signed_receipt["receipt"]
        if receipt.get("human_fingerprint") != payload["human_fingerprint"]:
            raise ValueError("Receipt fingerprint does not match rated human")
        if receipt.get("human_public_key") != human["public_key"]:
            raise ValueError("Receipt public key does not match ledger record")
        if receipt.get("caller_id") and receipt.get("caller_id") != payload["caller_id"]:
            raise ValueError("Receipt caller_id does not match rating caller_id")
        self._verify_evidence_against_receipt(receipt, payload.get("evidence"))

        receipt_hash = hashlib.sha256(_canonical_json(receipt) + signed_receipt["signature"].encode("utf-8")).hexdigest()
        rating_id = secrets.token_hex(12)
        rated_at = _utc_now_iso()
        auto_moderate = self._should_auto_moderate(payload)
        rating_status = "under_review" if auto_moderate else "accepted"
        moderation_status = "pending" if auto_moderate else "not_requested"
        moderation_case_id = None
        evidence = payload.get("evidence")
        evidence_manifest = self._build_evidence_manifest(evidence)
        evidence_expires_at = (
            (datetime.now(timezone.utc) + timedelta(hours=self._evidence_retention_hours)).isoformat()
            if evidence else None
        )

        with self._connect() as conn:
            self._purge_expired_evidence_conn(conn)
            existing = conn.execute(
                "SELECT id FROM ratings WHERE caller_id = ? AND receipt_hash = ?",
                (payload["caller_id"], receipt_hash),
            ).fetchone()
            if existing:
                raise ValueError("This caller has already rated that signed receipt")

            conn.execute(
                """
                INSERT INTO ratings (
                    id, caller_id, human_fingerprint, task_id, receipt_hash,
                    rating, reliability, utility, comment, rated_at, signed_receipt_json,
                    evidence_json, evidence_manifest_json, evidence_expires_at, status, moderation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rating_id,
                    payload["caller_id"],
                    payload["human_fingerprint"],
                    receipt.get("task_id"),
                    receipt_hash,
                    payload["rating"],
                    payload.get("reliability"),
                    payload.get("utility"),
                    payload.get("comment"),
                    rated_at,
                    json.dumps(signed_receipt),
                    json.dumps(evidence) if evidence else None,
                    json.dumps(evidence_manifest) if evidence_manifest else None,
                    evidence_expires_at,
                    rating_status,
                    moderation_status,
                ),
            )
            if auto_moderate:
                moderation_case_id = self._create_moderation_case_conn(
                    conn=conn,
                    rating_id=rating_id,
                    human_fingerprint=payload["human_fingerprint"],
                    caller_id=payload["caller_id"],
                    trigger="auto_low_score",
                    dispute_statement=None,
                    disputed_by=None,
                )
            self._recalculate_human_aggregates_conn(conn, payload["human_fingerprint"], rated_at)
            conn.commit()

        return {
            "id": rating_id,
            "accepted": True,
            "rated_at": rated_at,
            "status": rating_status,
            "moderation_case_id": moderation_case_id,
        }

    def get_rating(self, rating_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ratings WHERE id = ?", (rating_id,)).fetchone()
            return self._rating_row_to_dict(row) if row else None

    def create_dispute(
        self,
        rating_id: str,
        disputed_by: str,
        dispute_statement: str,
        evidence: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        rating = self.get_rating(rating_id)
        if rating is None:
            raise ValueError("Rating not found")
        if evidence:
            self._verify_evidence_against_receipt(rating["signed_receipt"]["receipt"], evidence)
        with self._connect() as conn:
            self._purge_expired_evidence_conn(conn)
            if evidence:
                evidence_manifest = self._build_evidence_manifest(evidence)
                evidence_expires_at = (
                    datetime.now(timezone.utc) + timedelta(hours=self._evidence_retention_hours)
                ).isoformat()
                conn.execute(
                    """
                    UPDATE ratings
                    SET evidence_json = ?, evidence_manifest_json = ?, evidence_expires_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(evidence),
                        json.dumps(evidence_manifest),
                        evidence_expires_at,
                        rating_id,
                    ),
                )
            case_id = self._create_moderation_case_conn(
                conn=conn,
                rating_id=rating_id,
                human_fingerprint=rating["human_fingerprint"],
                caller_id=rating["caller_id"],
                trigger="dispute",
                dispute_statement=dispute_statement,
                disputed_by=disputed_by,
            )
            conn.execute(
                """
                UPDATE ratings
                SET status = ?, moderation_status = ?
                WHERE id = ? AND status != 'removed'
                """,
                ("under_review", "pending", rating_id),
            )
            self._recalculate_human_aggregates_conn(conn, rating["human_fingerprint"], _utc_now_iso())
            conn.commit()
        return self.get_moderation_case(case_id)

    def list_moderation_cases(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM moderation_cases WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM moderation_cases ORDER BY created_at DESC"
                ).fetchall()
            return [self._moderation_row_to_dict(row) for row in rows]

    def get_moderation_case(self, case_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM moderation_cases WHERE id = ?", (case_id,)).fetchone()
            return self._moderation_row_to_dict(row) if row else None

    def mark_moderation_case_running(self, case_id: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE moderation_cases SET status = ?, updated_at = ? WHERE id = ?",
                ("running", _utc_now_iso(), case_id),
            )
            conn.commit()

    def mark_moderation_case_failed(self, case_id: str, summary: str):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE moderation_cases
                SET status = ?, updated_at = ?, result_summary = ?
                WHERE id = ?
                """,
                ("pending", _utc_now_iso(), summary, case_id),
            )
            conn.commit()

    def build_moderation_context(self, case_id: str) -> dict[str, Any]:
        case = self.get_moderation_case(case_id)
        if case is None:
            raise ValueError("Moderation case not found")
        rating = self.get_rating(case["rating_id"])
        if rating is None:
            raise ValueError("Associated rating not found")
        human = self.get_human(case["human_fingerprint"])
        return {
            "case": case,
            "rating": rating,
            "human": human,
        }

    def apply_moderation_result(self, case_id: str, result: dict[str, Any]) -> dict[str, Any]:
        case = self.get_moderation_case(case_id)
        if case is None:
            raise ValueError("Moderation case not found")
        rating = self.get_rating(case["rating_id"])
        if rating is None:
            raise ValueError("Associated rating not found")

        verdict = str(result.get("verdict") or "uphold").strip().lower()
        if verdict not in {"uphold", "adjust", "remove", "inconclusive"}:
            raise ValueError("Unsupported moderation verdict")

        final_rating = rating["rating"]
        final_reliability = rating.get("reliability")
        final_utility = rating.get("utility")
        status = "accepted"
        moderation_summary = str(result.get("summary") or "").strip()

        if verdict == "adjust":
            if result.get("adjusted_rating") is not None:
                final_rating = result.get("adjusted_rating")
            if result.get("adjusted_reliability") is not None:
                final_reliability = result.get("adjusted_reliability")
            if result.get("adjusted_utility") is not None:
                final_utility = result.get("adjusted_utility")
            status = "adjusted"
        elif verdict == "remove":
            status = "removed"
            final_rating = None
            final_reliability = None
            final_utility = None
        elif verdict == "inconclusive":
            status = "removed"
            final_rating = None
            final_reliability = None
            final_utility = None

        moderated_at = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ratings
                SET status = ?, moderation_status = ?, final_rating = ?, final_reliability = ?,
                    final_utility = ?, moderated_at = ?, moderation_summary = ?
                WHERE id = ?
                """,
                (
                    status,
                    "completed",
                    final_rating,
                    final_reliability,
                    final_utility,
                    moderated_at,
                    moderation_summary,
                    rating["id"],
                ),
            )
            conn.execute(
                """
                UPDATE moderation_cases
                SET status = ?, updated_at = ?, result_json = ?, result_summary = ?
                WHERE id = ?
                """,
                ("completed", moderated_at, json.dumps(result), moderation_summary, case_id),
            )
            self._recalculate_human_aggregates_conn(conn, rating["human_fingerprint"], moderated_at)
            conn.commit()
        return self.get_rating(rating["id"])

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    completed_at TEXT,
                    verification_payload TEXT,
                    proof_message TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS humans (
                    fingerprint TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT,
                    capabilities_json TEXT NOT NULL,
                    tagline TEXT,
                    registered_at TEXT NOT NULL,
                    first_verified_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    rating_count INTEGER NOT NULL DEFAULT 0,
                    average_rating REAL,
                    average_reliability REAL,
                    average_utility REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ratings (
                    id TEXT PRIMARY KEY,
                    caller_id TEXT NOT NULL,
                    human_fingerprint TEXT NOT NULL,
                    task_id TEXT,
                    receipt_hash TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    reliability INTEGER,
                    utility INTEGER,
                    comment TEXT,
                    rated_at TEXT NOT NULL,
                    signed_receipt_json TEXT NOT NULL,
                    evidence_json TEXT,
                    evidence_manifest_json TEXT,
                    evidence_expires_at TEXT,
                    status TEXT NOT NULL DEFAULT 'accepted',
                    moderation_status TEXT NOT NULL DEFAULT 'not_requested',
                    final_rating INTEGER,
                    final_reliability INTEGER,
                    final_utility INTEGER,
                    moderated_at TEXT,
                    moderation_summary TEXT,
                    UNIQUE(caller_id, receipt_hash)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS moderation_cases (
                    id TEXT PRIMARY KEY,
                    rating_id TEXT NOT NULL,
                    human_fingerprint TEXT NOT NULL,
                    caller_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    disputed_by TEXT,
                    dispute_statement TEXT,
                    result_json TEXT,
                    result_summary TEXT
                )
                """
            )
            self._ensure_column(conn, "ratings", "evidence_json", "TEXT")
            self._ensure_column(conn, "ratings", "evidence_manifest_json", "TEXT")
            self._ensure_column(conn, "ratings", "evidence_expires_at", "TEXT")
            self._ensure_column(conn, "ratings", "status", "TEXT NOT NULL DEFAULT 'accepted'")
            self._ensure_column(conn, "ratings", "moderation_status", "TEXT NOT NULL DEFAULT 'not_requested'")
            self._ensure_column(conn, "ratings", "final_rating", "INTEGER")
            self._ensure_column(conn, "ratings", "final_reliability", "INTEGER")
            self._ensure_column(conn, "ratings", "final_utility", "INTEGER")
            self._ensure_column(conn, "ratings", "moderated_at", "TEXT")
            self._ensure_column(conn, "ratings", "moderation_summary", "TEXT")
            self._ensure_column(conn, "verification_sessions", "proof_message", "TEXT")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _verification_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "public_key": row["public_key"],
            "fingerprint": row["fingerprint"],
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "completed_at": row["completed_at"],
            "proof_message": row["proof_message"],
        }

    def _human_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "fingerprint": row["fingerprint"],
            "public_key": row["public_key"],
            "name": row["name"],
            "url": row["url"],
            "capabilities": json.loads(row["capabilities_json"] or "[]"),
            "tagline": row["tagline"],
            "registered_at": row["registered_at"],
            "first_verified_at": row["first_verified_at"],
            "last_seen_at": row["last_seen_at"],
            "rating_count": int(row["rating_count"] or 0),
            "average_rating": row["average_rating"],
            "average_reliability": row["average_reliability"],
            "average_utility": row["average_utility"],
        }

    def _rating_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        evidence = json.loads(row["evidence_json"]) if row["evidence_json"] else None
        evidence_manifest = (
            json.loads(row["evidence_manifest_json"])
            if row["evidence_manifest_json"] else None
        )
        return {
            "id": row["id"],
            "caller_id": row["caller_id"],
            "human_fingerprint": row["human_fingerprint"],
            "task_id": row["task_id"],
            "receipt_hash": row["receipt_hash"],
            "status": row["status"] or "accepted",
            "moderation_status": row["moderation_status"] or "not_requested",
            "rating": row["rating"],
            "reliability": row["reliability"],
            "utility": row["utility"],
            "final_rating": row["final_rating"],
            "final_reliability": row["final_reliability"],
            "final_utility": row["final_utility"],
            "comment": row["comment"],
            "rated_at": row["rated_at"],
            "moderated_at": row["moderated_at"],
            "moderation_summary": row["moderation_summary"],
            "signed_receipt": json.loads(row["signed_receipt_json"]),
            "evidence": evidence,
            "evidence_available": evidence is not None,
            "evidence_manifest": evidence_manifest,
        }

    def _moderation_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "rating_id": row["rating_id"],
            "human_fingerprint": row["human_fingerprint"],
            "caller_id": row["caller_id"],
            "trigger": row["trigger"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "disputed_by": row["disputed_by"],
            "dispute_statement": row["dispute_statement"],
            "result_summary": row["result_summary"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }

    def _should_auto_moderate(self, payload: dict[str, Any]) -> bool:
        if int(payload["rating"]) <= 2:
            return True
        for field in ("reliability", "utility"):
            value = payload.get(field)
            if value is not None and int(value) <= 2:
                return True
        return False

    def _verify_evidence_against_receipt(self, receipt: dict[str, Any], evidence: Optional[dict[str, Any]]):
        if not evidence:
            return
        hash_fields = [
            ("task_description", "description_sha256"),
            ("task_context", "context_sha256"),
            ("task_result", "result_sha256"),
        ]
        for field, receipt_hash_field in hash_fields:
            value = evidence.get(field)
            if value is None:
                continue
            calculated = hashlib.sha256(value.encode("utf-8")).hexdigest()
            if calculated != receipt.get(receipt_hash_field):
                raise ValueError(f"Evidence field '{field}' does not match the signed receipt hash")

    def _build_evidence_manifest(self, evidence: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not evidence:
            return None
        manifest = {
            "version": 1,
            "fields": {},
            "stored_at": _utc_now_iso(),
        }
        for key, value in evidence.items():
            if value is None:
                continue
            value_str = str(value)
            manifest["fields"][key] = {
                "sha256": hashlib.sha256(value_str.encode("utf-8")).hexdigest(),
                "length": len(value_str),
            }
        return manifest

    def _create_moderation_case_conn(
        self,
        conn: sqlite3.Connection,
        rating_id: str,
        human_fingerprint: str,
        caller_id: str,
        trigger: str,
        dispute_statement: Optional[str],
        disputed_by: Optional[str],
    ) -> str:
        existing = conn.execute(
            "SELECT id FROM moderation_cases WHERE rating_id = ? AND status IN ('pending', 'running')",
            (rating_id,),
        ).fetchone()
        if existing:
            return existing["id"]

        case_id = secrets.token_hex(12)
        now = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO moderation_cases (
                id, rating_id, human_fingerprint, caller_id, trigger, status,
                created_at, updated_at, disputed_by, dispute_statement
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                rating_id,
                human_fingerprint,
                caller_id,
                trigger,
                "pending",
                now,
                now,
                disputed_by,
                dispute_statement,
            ),
        )
        return case_id

    def _recalculate_human_aggregates_conn(self, conn: sqlite3.Connection, fingerprint: str, last_seen_at: str):
        aggregates = conn.execute(
            """
            SELECT
                COUNT(*) AS rating_count,
                AVG(CASE
                    WHEN status = 'adjusted' THEN final_rating
                    WHEN status = 'accepted' THEN rating
                    ELSE NULL
                END) AS average_rating,
                AVG(CASE
                    WHEN status = 'adjusted' THEN final_reliability
                    WHEN status = 'accepted' THEN reliability
                    ELSE NULL
                END) AS average_reliability,
                AVG(CASE
                    WHEN status = 'adjusted' THEN final_utility
                    WHEN status = 'accepted' THEN utility
                    ELSE NULL
                END) AS average_utility
            FROM ratings
            WHERE human_fingerprint = ?
              AND status IN ('accepted', 'adjusted')
            """,
            (fingerprint,),
        ).fetchone()
        conn.execute(
            """
            UPDATE humans
            SET rating_count = ?, average_rating = ?, average_reliability = ?,
                average_utility = ?, last_seen_at = ?
            WHERE fingerprint = ?
            """,
            (
                int(aggregates["rating_count"] or 0),
                aggregates["average_rating"],
                aggregates["average_reliability"],
                aggregates["average_utility"],
                last_seen_at,
                fingerprint,
            ),
        )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def purge_expired_evidence(self) -> int:
        with self._connect() as conn:
            removed = self._purge_expired_evidence_conn(conn)
            conn.commit()
            return removed

    def _purge_expired_evidence_conn(self, conn: sqlite3.Connection) -> int:
        now = _utc_now_iso()
        rows = conn.execute(
            """
            SELECT id FROM ratings
            WHERE evidence_json IS NOT NULL
              AND evidence_expires_at IS NOT NULL
              AND evidence_expires_at <= ?
            """,
            (now,),
        ).fetchall()
        if not rows:
            return 0
        conn.execute(
            """
            UPDATE ratings
            SET evidence_json = NULL
            WHERE evidence_json IS NOT NULL
              AND evidence_expires_at IS NOT NULL
              AND evidence_expires_at <= ?
            """,
            (now,),
        )
        return len(rows)

    def _cleaner(self):
        while True:
            time.sleep(3600)
            try:
                self.purge_expired_evidence()
            except Exception:
                continue
