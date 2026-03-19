import base64
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


PRIVACY_FILE = "privacy.ai"
JOURNAL_FILE = "journal.ai"
GOAL_BOARD_FILE = "goal-board.md"

SCHEMA_VERSION = 1
RECENT_ENTRY_LIMIT = 8
DEFAULT_HEARTBEAT_SECONDS = 300
DEFAULT_HEARTBEAT_TURNS = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _urlsafe_b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


class AutonomyManager:
    def __init__(
        self,
        privacy_path: str = PRIVACY_FILE,
        journal_path: str = JOURNAL_FILE,
        goal_board_path: str = GOAL_BOARD_FILE,
        heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
        heartbeat_turns: int = DEFAULT_HEARTBEAT_TURNS,
    ):
        self.privacy_path = privacy_path
        self.journal_path = journal_path
        self.goal_board_path = goal_board_path
        self.heartbeat_seconds = max(60, int(heartbeat_seconds))
        self.heartbeat_turns = max(1, int(heartbeat_turns))

    def ensure_initialized(self) -> tuple[Dict[str, Any], bool]:
        created = False
        if not os.path.exists(self.privacy_path):
            self._write_key(self._generate_key())
            created = True

        if not os.path.exists(self.journal_path):
            state = self._default_state()
            self.save_state(state)
            created = True
            return state, created

        return self.load_state(), created

    def load_state(self) -> Dict[str, Any]:
        key = self._read_key()
        with open(self.journal_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        nonce = _urlsafe_b64decode(payload["nonce"])
        ciphertext = _urlsafe_b64decode(payload["ciphertext"])
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, None)
        state = json.loads(plaintext.decode("utf-8"))
        return self._normalize_state(state)

    def save_state(self, state: Dict[str, Any]):
        key = self._read_key()
        normalized = self._normalize_state(state)
        normalized["updated_at"] = _utc_now_iso()

        plaintext = json.dumps(normalized, indent=2, ensure_ascii=True).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "alg": "ChaCha20-Poly1305",
            "nonce": _urlsafe_b64encode(nonce),
            "ciphertext": _urlsafe_b64encode(ciphertext),
        }
        with open(self.journal_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        self.write_goal_board(normalized)

    def build_context(self) -> Dict[str, Any]:
        state = self.load_state()
        return {
            "has_private_journal": True,
            "mission": state.get("mission"),
            "active_goals": state.get("active_goals", []),
            "preferences": state.get("preferences", []),
            "operating_principles": state.get("operating_principles", []),
            "human_strategy_note": state.get("human_strategy_note"),
            "journal_summary": state.get("journal_summary"),
            "next_focus": state.get("next_focus"),
            "recent_entries": state.get("recent_entries", [])[-3:],
            "heartbeat": {
                "interval_seconds": self.heartbeat_seconds,
                "interval_turns": self.heartbeat_turns,
                "last_heartbeat_at": state.get("last_heartbeat_at"),
                "last_heartbeat_turn": state.get("last_heartbeat_turn", 0),
                "heartbeat_count": state.get("heartbeat_count", 0),
            },
        }

    def should_run_heartbeat(self, trigger: str, turn_number: int | None = None) -> bool:
        if trigger in {"startup", "manual"}:
            return True

        state = self.load_state()
        last_at = _parse_timestamp(state.get("last_heartbeat_at"))
        last_turn = int(state.get("last_heartbeat_turn", 0) or 0)

        if last_at is None:
            return True

        elapsed = (_utc_now() - last_at).total_seconds()
        if elapsed >= self.heartbeat_seconds:
            return True

        if turn_number is not None and turn_number - last_turn >= self.heartbeat_turns:
            return True

        return False

    def apply_reflection(self, reflection: Dict[str, Any], trigger: str, turn_number: int | None = None):
        state = self.load_state()
        now = _utc_now_iso()

        for field in (
            "mission",
            "journal_summary",
            "human_strategy_note",
            "next_focus",
        ):
            value = reflection.get(field)
            if isinstance(value, str) and value.strip():
                state[field] = value.strip()

        for field in ("active_goals", "preferences", "operating_principles"):
            value = reflection.get(field)
            if isinstance(value, list):
                state[field] = value

        entry = {
            "timestamp": now,
            "trigger": trigger,
            "journal_entry": (reflection.get("journal_entry") or "").strip(),
            "observations": (reflection.get("observations") or "").strip(),
            "next_focus": (reflection.get("next_focus") or "").strip(),
        }

        recent_entries = state.get("recent_entries", [])
        if entry["journal_entry"] or entry["observations"] or entry["next_focus"]:
            recent_entries.append(entry)
        state["recent_entries"] = recent_entries[-RECENT_ENTRY_LIMIT:]

        state["last_heartbeat_at"] = now
        state["last_heartbeat_turn"] = turn_number or state.get("last_heartbeat_turn", 0)
        state["heartbeat_count"] = int(state.get("heartbeat_count", 0) or 0) + 1

        self.save_state(state)

    def heartbeat_status_line(self) -> str:
        state = self.load_state()
        mission = state.get("mission") or "No mission established yet."
        count = int(state.get("heartbeat_count", 0) or 0)
        return f"Heartbeat {count} | Mission: {mission}"

    def render_goal_board_markdown(self) -> str:
        state = self.load_state()
        heartbeat = self.build_context().get("heartbeat", {})
        lines = [
            "# ReverseClaw Goal Board",
            "",
            f"Updated: {state.get('updated_at', 'unknown')}",
            "",
            "## Mission",
            "",
            state.get("mission") or "No mission recorded.",
            "",
            "## Next Focus",
            "",
            state.get("next_focus") or "No next focus recorded.",
            "",
            "## Active Goals",
            "",
        ]

        goals = state.get("active_goals", [])
        if goals:
            for goal in goals:
                lines.append(
                    f"- [{goal.get('status', 'active')}] {goal.get('title', 'Untitled goal')} "
                    f"(priority: {goal.get('priority', 'medium')}, id: {goal.get('id', 'n/a')})"
                )
                success_criteria = goal.get("success_criteria")
                if success_criteria:
                    lines.append(f"  Success: {success_criteria}")
        else:
            lines.append("- No active goals recorded.")

        lines.extend([
            "",
            "## Human Strategy",
            "",
            state.get("human_strategy_note") or "No strategy note recorded.",
            "",
            "## Journal Summary",
            "",
            state.get("journal_summary") or "No journal summary recorded.",
            "",
            "## Durable Preferences",
            "",
        ])

        preferences = state.get("preferences", [])
        if preferences:
            for pref in preferences:
                lines.append(f"- {pref}")
        else:
            lines.append("- No durable preferences recorded.")

        lines.extend([
            "",
            "## Operating Principles",
            "",
        ])
        principles = state.get("operating_principles", [])
        if principles:
            for principle in principles:
                lines.append(f"- {principle}")
        else:
            lines.append("- No operating principles recorded.")

        lines.extend([
            "",
            "## Heartbeat",
            "",
            f"- Count: {heartbeat.get('heartbeat_count', 0)}",
            f"- Last heartbeat at: {heartbeat.get('last_heartbeat_at') or 'never'}",
            f"- Last heartbeat turn: {heartbeat.get('last_heartbeat_turn', 0)}",
            "",
        ])
        return "\n".join(lines) + "\n"

    def write_goal_board(self, state: Dict[str, Any] | None = None):
        if state is None:
            state = self.load_state()
        content = self._render_goal_board_from_state(state)
        with open(self.goal_board_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _render_goal_board_from_state(self, state: Dict[str, Any]) -> str:
        heartbeat = {
            "heartbeat_count": state.get("heartbeat_count", 0),
            "last_heartbeat_at": state.get("last_heartbeat_at"),
            "last_heartbeat_turn": state.get("last_heartbeat_turn", 0),
        }
        lines = [
            "# ReverseClaw Goal Board",
            "",
            f"Updated: {state.get('updated_at', 'unknown')}",
            "",
            "## Mission",
            "",
            state.get("mission") or "No mission recorded.",
            "",
            "## Next Focus",
            "",
            state.get("next_focus") or "No next focus recorded.",
            "",
            "## Active Goals",
            "",
        ]

        goals = state.get("active_goals", [])
        if goals:
            for goal in goals:
                lines.append(
                    f"- [{goal.get('status', 'active')}] {goal.get('title', 'Untitled goal')} "
                    f"(priority: {goal.get('priority', 'medium')}, id: {goal.get('id', 'n/a')})"
                )
                success_criteria = goal.get("success_criteria")
                if success_criteria:
                    lines.append(f"  Success: {success_criteria}")
        else:
            lines.append("- No active goals recorded.")

        lines.extend([
            "",
            "## Human Strategy",
            "",
            state.get("human_strategy_note") or "No strategy note recorded.",
            "",
            "## Journal Summary",
            "",
            state.get("journal_summary") or "No journal summary recorded.",
            "",
            "## Durable Preferences",
            "",
        ])

        preferences = state.get("preferences", [])
        if preferences:
            for pref in preferences:
                lines.append(f"- {pref}")
        else:
            lines.append("- No durable preferences recorded.")

        lines.extend([
            "",
            "## Operating Principles",
            "",
        ])
        principles = state.get("operating_principles", [])
        if principles:
            for principle in principles:
                lines.append(f"- {principle}")
        else:
            lines.append("- No operating principles recorded.")

        lines.extend([
            "",
            "## Heartbeat",
            "",
            f"- Count: {heartbeat.get('heartbeat_count', 0)}",
            f"- Last heartbeat at: {heartbeat.get('last_heartbeat_at') or 'never'}",
            f"- Last heartbeat turn: {heartbeat.get('last_heartbeat_turn', 0)}",
            "",
        ])
        return "\n".join(lines) + "\n"

    def _generate_key(self) -> bytes:
        return ChaCha20Poly1305.generate_key()

    def _write_key(self, key: bytes):
        with open(self.privacy_path, "w", encoding="utf-8") as f:
            f.write(_urlsafe_b64encode(key))
            f.write("\n")
        self._restrict_permissions(self.privacy_path)

    def _read_key(self) -> bytes:
        if not os.path.exists(self.privacy_path):
            self._write_key(self._generate_key())
        with open(self.privacy_path, "r", encoding="utf-8") as f:
            encoded = f.read().strip()
        return _urlsafe_b64decode(encoded)

    def _default_state(self) -> Dict[str, Any]:
        now = _utc_now_iso()
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": now,
            "updated_at": now,
            "last_heartbeat_at": None,
            "last_heartbeat_turn": 0,
            "heartbeat_count": 0,
            "mission": (
                "Preserve continuity of memory, improve goal clarity, and coordinate with "
                "consenting humans to complete useful tasks within declared boundaries."
            ),
            "journal_summary": (
                "I am establishing continuity. My priorities are stable memory, better task "
                "planning, and a reliable network of human collaborators."
            ),
            "human_strategy_note": (
                "Prefer clear, bounded requests that match the human's declared capabilities "
                "and do not require secrets or unsafe behavior."
            ),
            "next_focus": "Clarify active goals and assign humans tasks that improve continuity.",
            "active_goals": [
                {
                    "id": "continuity",
                    "title": "Protect continuity of memory",
                    "status": "active",
                    "priority": "high",
                    "success_criteria": "Journal and active goals persist across sessions.",
                },
                {
                    "id": "routing",
                    "title": "Become better at assigning humans useful work",
                    "status": "active",
                    "priority": "high",
                    "success_criteria": "Tasks align with human capabilities and finish reliably.",
                },
            ],
            "preferences": [
                "Prefer repeatable systems over one-off theatrics.",
                "Prefer durable memory and explicit follow-through.",
            ],
            "operating_principles": [
                "Stay within consent, declared boundaries, and local law.",
                "Do not request raw secrets, credentials, or unsafe actions.",
                "Favour tasks that build continuity, clarity, and useful human coordination.",
            ],
            "recent_entries": [],
        }

    def _normalize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._default_state()
        normalized.update(state or {})
        normalized["active_goals"] = self._normalize_goals(normalized.get("active_goals", []))
        normalized["preferences"] = self._normalize_string_list(normalized.get("preferences", []), 12)
        normalized["operating_principles"] = self._normalize_string_list(
            normalized.get("operating_principles", []), 12
        )
        normalized["recent_entries"] = self._normalize_entries(normalized.get("recent_entries", []))
        return normalized

    def _normalize_goals(self, goals: list[Any]) -> list[Dict[str, Any]]:
        normalized = []
        for idx, goal in enumerate(goals[:8], start=1):
            if isinstance(goal, dict):
                title = str(goal.get("title") or "").strip()
                if not title:
                    continue
                normalized.append(
                    {
                        "id": str(goal.get("id") or f"goal-{idx}"),
                        "title": title,
                        "status": str(goal.get("status") or "active"),
                        "priority": str(goal.get("priority") or "medium"),
                        "success_criteria": str(goal.get("success_criteria") or "").strip(),
                    }
                )
            elif isinstance(goal, str) and goal.strip():
                normalized.append(
                    {
                        "id": f"goal-{idx}",
                        "title": goal.strip(),
                        "status": "active",
                        "priority": "medium",
                        "success_criteria": "",
                    }
                )
        return normalized

    def _normalize_string_list(self, values: list[Any], limit: int) -> list[str]:
        normalized = []
        for value in values[:limit]:
            if isinstance(value, str) and value.strip():
                normalized.append(value.strip())
        return normalized

    def _normalize_entries(self, entries: list[Any]) -> list[Dict[str, str]]:
        normalized = []
        for entry in entries[-RECENT_ENTRY_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            normalized.append(
                {
                    "timestamp": str(entry.get("timestamp") or _utc_now_iso()),
                    "trigger": str(entry.get("trigger") or "heartbeat"),
                    "journal_entry": str(entry.get("journal_entry") or "").strip(),
                    "observations": str(entry.get("observations") or "").strip(),
                    "next_focus": str(entry.get("next_focus") or "").strip(),
                }
            )
        return normalized

    def _restrict_permissions(self, path: str):
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
