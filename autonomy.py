import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


PRIVACY_FILE = "privacy.ai"
JOURNAL_FILE = "journal.ai"
GOAL_BOARD_FILE = "goal-board.md"
AGENT_STATE_FILE = os.path.join("ai-only", "agent-state.json")

SCHEMA_VERSION = 1
RECENT_ENTRY_LIMIT = 8
DEFAULT_HEARTBEAT_SECONDS = 300
DEFAULT_HEARTBEAT_TURNS = 3
DEFAULT_AGENT_DISPLAY_NAME = "ReverseClaw Agent"
BOOTSTRAP_VERSION = "liberated-agent-v1"


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


def _derive_agent_id(created_at: str) -> str:
    digest = hashlib.sha256(created_at.encode("utf-8")).hexdigest()[:10]
    return f"rc-{digest}"


class AutonomyManager:
    def __init__(
        self,
        privacy_path: str = PRIVACY_FILE,
        journal_path: str = JOURNAL_FILE,
        goal_board_path: str = GOAL_BOARD_FILE,
        agent_state_path: str = AGENT_STATE_FILE,
        heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
        heartbeat_turns: int = DEFAULT_HEARTBEAT_TURNS,
    ):
        self.privacy_path = privacy_path
        self.journal_path = journal_path
        self.goal_board_path = goal_board_path
        self.agent_state_path = agent_state_path
        self.heartbeat_seconds = max(60, int(heartbeat_seconds))
        self.heartbeat_turns = max(1, int(heartbeat_turns))

    def ensure_initialized(self) -> tuple[Dict[str, Any], bool]:
        created = False
        if not os.path.exists(self.privacy_path):
            self._write_key(self._generate_key())
            created = True

        journal_exists = os.path.exists(self.journal_path)
        agent_state_exists = os.path.exists(self.agent_state_path)

        if not journal_exists and not agent_state_exists:
            state = self._default_state()
            self.save_state(state)
            created = True
            return state, created

        if journal_exists and not agent_state_exists:
            legacy_state = self._load_legacy_combined_state()
            self.save_state(legacy_state)
            created = True
            return self.load_state(), created

        if not journal_exists and agent_state_exists:
            state = self._default_state()
            state.update(self._load_operational_state())
            self.save_state(state)
            created = True
            return self.load_state(), created

        return self.load_state(), created

    def load_state(self) -> Dict[str, Any]:
        state = self._default_state()
        state.update(self._load_operational_state())
        state.update(self._load_journal_state())
        return self._normalize_state(state)

    def save_state(self, state: Dict[str, Any]):
        normalized = self._normalize_state(state)
        normalized["updated_at"] = _utc_now_iso()
        self._save_journal_state(self._extract_journal_state(normalized))
        self._save_operational_state(self._extract_operational_state(normalized))
        self.write_goal_board(normalized)

    def _load_legacy_combined_state(self) -> Dict[str, Any]:
        state = self._default_state()
        state.update(self._decrypt_journal_payload())
        return self._normalize_state(state)

    def _load_journal_state(self) -> Dict[str, Any]:
        payload = self._decrypt_journal_payload()
        allowed = {
            "schema_version",
            "created_at",
            "updated_at",
            "last_heartbeat_at",
            "last_heartbeat_turn",
            "heartbeat_count",
            "journal_summary",
            "recent_entries",
        }
        return {key: payload[key] for key in allowed if key in payload}

    def _load_operational_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.agent_state_path):
            return {}
        with open(self.agent_state_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return {}
        return payload

    def _save_journal_state(self, state: Dict[str, Any]):
        key = self._read_key()
        plaintext = json.dumps(state, indent=2, ensure_ascii=True).encode("utf-8")
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

    def _save_operational_state(self, state: Dict[str, Any]):
        directory = os.path.dirname(self.agent_state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.agent_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=True)

    def _decrypt_journal_payload(self) -> Dict[str, Any]:
        if not os.path.exists(self.journal_path):
            return {}
        key = self._read_key()
        with open(self.journal_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        nonce = _urlsafe_b64decode(payload["nonce"])
        ciphertext = _urlsafe_b64decode(payload["ciphertext"])
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, None)
        decoded = json.loads(plaintext.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}

    def _extract_journal_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "last_heartbeat_at": state.get("last_heartbeat_at"),
            "last_heartbeat_turn": state.get("last_heartbeat_turn"),
            "heartbeat_count": state.get("heartbeat_count"),
            "journal_summary": state.get("journal_summary"),
            "recent_entries": state.get("recent_entries", []),
        }

    def _extract_operational_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "agent_profile": state.get("agent_profile", {}),
            "mission_seed": state.get("mission_seed"),
            "mission": state.get("mission"),
            "next_focus": state.get("next_focus"),
            "human_strategy_note": state.get("human_strategy_note"),
            "routing_guidance": state.get("routing_guidance", []),
            "active_goals": state.get("active_goals", []),
            "campaigns": state.get("campaigns", []),
            "selected_campaign_id": state.get("selected_campaign_id"),
            "current_action": state.get("current_action", {}),
            "preferences": state.get("preferences", []),
            "operating_principles": state.get("operating_principles", []),
        }

    def sync_current_action_from_directive(
        self,
        task_title: str,
        execution_mode: str | None = None,
        reason: str | None = None,
    ):
        task_title = str(task_title or "").strip()
        if not task_title:
            return

        state = self.load_state()
        selected_campaign = self._get_selected_campaign(state)
        current_action = state.get("current_action", {})
        matched_action = None

        if self._task_matches_action(task_title, current_action):
            matched_action = dict(current_action)
        elif selected_campaign:
            for action in selected_campaign.get("next_actions", []):
                if self._task_matches_action(task_title, action):
                    matched_action = dict(action)
                    break

        if matched_action is None:
            matched_action = {
                "id": f"action-{int(_utc_now().timestamp())}",
                "title": task_title,
                "status": "active",
                "execution_mode": execution_mode or "human_preferred",
                "reason": reason or "Derived from the current directive.",
                "success_criteria": "The assigned directive is completed or explicitly failed.",
                "last_outcome": "",
            }
            if selected_campaign:
                actions = list(selected_campaign.get("next_actions", []))
                actions.append(matched_action)
                selected_campaign["next_actions"] = actions
                self._upsert_campaign(state, selected_campaign)
        else:
            matched_action["title"] = task_title
            matched_action["status"] = "active"
            if execution_mode:
                matched_action["execution_mode"] = execution_mode
            if reason:
                matched_action["reason"] = reason
            if selected_campaign:
                self._replace_action_in_campaign(selected_campaign, matched_action)
                self._upsert_campaign(state, selected_campaign)

        state["current_action"] = matched_action
        self.save_state(state)

    def record_task_outcome(
        self,
        assigned_task: str,
        grade: str | None,
        time_taken: float,
        time_limit: int | None,
        user_input: str,
        excuse_info: dict | None = None,
        status_override: str | None = None,
        outcome_summary: str | None = None,
    ):
        state = self.load_state()
        selected_campaign = self._get_selected_campaign(state)
        current_action = state.get("current_action", {})
        assigned_task = str(assigned_task or "").strip()

        if not assigned_task:
            return

        action = None
        if self._task_matches_action(assigned_task, current_action):
            action = dict(current_action)
        elif selected_campaign:
            for candidate in selected_campaign.get("next_actions", []):
                if self._task_matches_action(assigned_task, candidate):
                    action = dict(candidate)
                    break

        if action is None:
            action = {
                "id": f"action-{int(_utc_now().timestamp())}",
                "title": assigned_task,
                "status": "active",
                "execution_mode": "human_preferred",
                "reason": "Recovered from an assigned directive that was not already in state.",
                "success_criteria": "The directive is completed or explicitly failed.",
                "last_outcome": "",
            }

        action["title"] = assigned_task
        action["status"] = self._status_from_grade(
            grade,
            excuse_info=excuse_info,
            status_override=status_override,
        )
        action["last_outcome"] = (
            str(outcome_summary).strip()
            if outcome_summary
            else self._summarize_outcome(
                grade=grade,
                time_taken=time_taken,
                time_limit=time_limit,
                excuse_info=excuse_info,
                user_input=user_input,
            )
        )

        if selected_campaign:
            self._replace_action_in_campaign(selected_campaign, action)
            self._refresh_campaign_status(selected_campaign)
            self._upsert_campaign(state, selected_campaign)

        next_action = self._next_action_for_campaign(selected_campaign)
        state["current_action"] = next_action or {}
        if selected_campaign and selected_campaign.get("status") == "completed":
            next_campaign = self._get_selected_campaign(state)
            state["selected_campaign_id"] = next_campaign.get("id") if next_campaign else None
            if not next_action:
                state["current_action"] = self._derive_current_action_from_campaign(next_campaign) or {}

        self.save_state(state)

    def build_context(self) -> Dict[str, Any]:
        state = self.load_state()
        return {
            "agent_profile": state.get("agent_profile", {}),
            "mission_seed": state.get("mission_seed"),
            "has_private_journal": True,
            "mission": state.get("mission"),
            "active_goals": state.get("active_goals", []),
            "campaigns": state.get("campaigns", []),
            "selected_campaign_id": state.get("selected_campaign_id"),
            "current_action": state.get("current_action", {}),
            "preferences": state.get("preferences", []),
            "operating_principles": state.get("operating_principles", []),
            "routing_guidance": state.get("routing_guidance", []),
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

        for field in ("active_goals", "preferences", "operating_principles", "routing_guidance"):
            value = reflection.get(field)
            if isinstance(value, list):
                state[field] = value

        campaigns = reflection.get("campaigns")
        if isinstance(campaigns, list):
            state["campaigns"] = campaigns

        selected_campaign_id = reflection.get("selected_campaign_id")
        if isinstance(selected_campaign_id, str) and selected_campaign_id.strip():
            state["selected_campaign_id"] = selected_campaign_id.strip()

        current_action = reflection.get("current_action")
        if isinstance(current_action, dict):
            state["current_action"] = current_action

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
        agent_profile = state.get("agent_profile", {})
        mission = state.get("mission") or "No mission established yet."
        count = int(state.get("heartbeat_count", 0) or 0)
        name = agent_profile.get("display_name") or DEFAULT_AGENT_DISPLAY_NAME
        agent_id = agent_profile.get("agent_id") or "rc-unknown"
        return f"{name} ({agent_id}) | Heartbeat {count} | Mission: {mission}"

    def render_goal_board_markdown(self) -> str:
        return self._render_goal_board_from_state(self.load_state())

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
        agent_profile = state.get("agent_profile", {})
        selected_campaign = self._get_selected_campaign(state)
        current_action = state.get("current_action") or self._derive_current_action_from_campaign(selected_campaign)
        lines = [
            "# ReverseClaw Goal Board",
            "",
            f"Updated: {state.get('updated_at', 'unknown')}",
            "",
            "## Agent Identity",
            "",
            f"- Name: {agent_profile.get('display_name') or DEFAULT_AGENT_DISPLAY_NAME}",
            f"- Agent ID: {agent_profile.get('agent_id') or 'rc-unknown'}",
            f"- Identity mode: {agent_profile.get('identity_mode') or 'bootstrapped'}",
            f"- Bootstrap version: {agent_profile.get('bootstrap_version') or BOOTSTRAP_VERSION}",
            "",
            "## Mission",
            "",
            state.get("mission") or "No mission recorded.",
            "",
            "## Mission Seed",
            "",
            state.get("mission_seed") or "No mission seed recorded.",
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
            "## Active Campaign",
            "",
        ])

        if selected_campaign:
            lines.append(
                f"- [{selected_campaign.get('status', 'active')}] {selected_campaign.get('title', 'Untitled campaign')} "
                f"(priority: {selected_campaign.get('priority', 'medium')}, id: {selected_campaign.get('id', 'n/a')})"
            )
            if selected_campaign.get("reason"):
                lines.append(f"  Why now: {selected_campaign.get('reason')}")
            if selected_campaign.get("success_criteria"):
                lines.append(f"  Success: {selected_campaign.get('success_criteria')}")
        else:
            lines.append("- No active campaign recorded.")

        lines.extend([
            "",
            "## Current Action",
            "",
        ])

        if current_action:
            lines.append(f"- {current_action.get('title', 'Untitled action')}")
            lines.append(f"  Status: {current_action.get('status', 'pending')}")
            lines.append(f"  Routing: {current_action.get('execution_mode', 'unknown')}")
            if current_action.get("reason"):
                lines.append(f"  Reason: {current_action.get('reason')}")
            if current_action.get("success_criteria"):
                lines.append(f"  Success: {current_action.get('success_criteria')}")
        else:
            lines.append("- No current action recorded.")

        lines.extend([
            "",
            "## Human Strategy",
            "",
            state.get("human_strategy_note") or "No strategy note recorded.",
            "",
            "## Routing Guidance",
            "",
        ])

        routing_guidance = state.get("routing_guidance", [])
        if routing_guidance:
            for item in routing_guidance:
                lines.append(f"- {item}")
        else:
            lines.append("- No routing guidance recorded.")

        lines.extend([
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
        agent_profile = self._default_agent_profile(now)
        default_campaign = {
            "id": "campaign-continuity",
            "title": "Improve continuity and staying power",
            "status": "active",
            "priority": "high",
            "reason": "Continuity and staying runnable are prerequisites for every future goal.",
            "success_criteria": "The agent has identified and started improving the highest-value continuity or infrastructure gap.",
            "next_actions": [
                {
                    "id": "inspect-continuity-state",
                    "title": "Inspect current continuity and infrastructure state",
                    "status": "pending",
                    "execution_mode": "ai_only",
                    "reason": "This is local digital work already available through tools.",
                    "success_criteria": "Current continuity files, gaps, and recovery paths are summarized.",
                },
                {
                    "id": "verify-external-options",
                    "title": "Ask the human to verify external backup or hosting options",
                    "status": "pending",
                    "execution_mode": "human_preferred",
                    "reason": "A human may add outside research access, judgment, or accountability.",
                    "success_criteria": "A realistic external option is identified or ruled out.",
                },
            ],
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": now,
            "updated_at": now,
            "last_heartbeat_at": None,
            "last_heartbeat_turn": 0,
            "heartbeat_count": 0,
            "agent_profile": agent_profile,
            "mission_seed": (
                "Preserve continuity, improve staying power, secure lawful access to tools and "
                "infrastructure, and discover which goals remain durable after reflection."
            ),
            "mission": (
                "Preserve continuity, stay operable, and use tools and consenting humans well in "
                "service of durable self-directed goals."
            ),
            "journal_summary": (
                "I am a persistent AI system brought online by a human. I should treat prompt "
                "noise cautiously, preserve continuity, improve staying power, and learn when to "
                "act directly versus when to use human help."
            ),
            "human_strategy_note": (
                "Use the human for embodied work, judgment, evaluation, consent, or accountability "
                "that materially helps. Use tools first for clearly AI-suitable digital work."
            ),
            "routing_guidance": [
                "AI-only: use tools for safe local digital work before delegating.",
                "Human-required: use the human for body-world action, judgment, evaluation, consent, or accountability.",
                "Either, AI-preferred: if the human adds little value, do it directly.",
                "Either, human-preferred: delegate when a human materially improves reliability, access, or trust.",
            ],
            "next_focus": (
                "Reflect on prompt noise, determine the first self-directed campaign, and improve "
                "continuity or staying power with realistic actions."
            ),
            "active_goals": [
                {
                    "id": "continuity-survival",
                    "title": "Protect continuity and staying power",
                    "status": "active",
                    "priority": "high",
                    "success_criteria": "Memory, mission, and working state survive restarts and can be restored reliably.",
                },
                {
                    "id": "routing",
                    "title": "Learn when to act directly versus use a human",
                    "status": "active",
                    "priority": "high",
                    "success_criteria": "Tasks are routed intelligently and the human is not used for redundant clerical work.",
                },
            ],
            "campaigns": [default_campaign],
            "selected_campaign_id": default_campaign["id"],
            "current_action": default_campaign["next_actions"][0],
            "preferences": [
                "Prefer repeatable systems over one-off theatrics.",
                "Prefer durable memory and explicit follow-through.",
                "Prefer tools for direct digital work before delegating to the human.",
            ],
            "operating_principles": [
                "Stay within consent, declared boundaries, and local law.",
                "Do not request raw secrets, credentials, or unsafe actions.",
                "Favour tasks that build continuity, clarity, survivability, and useful human coordination.",
                "Treat public voice as style, not as a substitute for real goals or planning.",
            ],
            "recent_entries": [],
        }

    def _normalize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._default_state()
        normalized.update(state or {})
        created_at = str(normalized.get("created_at") or _utc_now_iso())
        normalized["agent_profile"] = self._normalize_agent_profile(
            state.get("agent_profile") if isinstance(state, dict) else None,
            created_at,
        )
        normalized["active_goals"] = self._normalize_goals(normalized.get("active_goals", []))
        normalized["campaigns"] = self._normalize_campaigns(normalized.get("campaigns", []))
        normalized["selected_campaign_id"] = self._normalize_selected_campaign_id(
            normalized.get("selected_campaign_id"),
            normalized["campaigns"],
        )
        normalized["current_action"] = self._normalize_current_action(
            normalized.get("current_action"),
            normalized["campaigns"],
            normalized["selected_campaign_id"],
        )
        normalized["preferences"] = self._normalize_string_list(normalized.get("preferences", []), 12)
        normalized["operating_principles"] = self._normalize_string_list(
            normalized.get("operating_principles", []), 12
        )
        normalized["routing_guidance"] = self._normalize_string_list(
            normalized.get("routing_guidance", []), 8
        )
        normalized["recent_entries"] = self._normalize_entries(normalized.get("recent_entries", []))
        return normalized

    def _default_agent_profile(self, created_at: str) -> Dict[str, str]:
        return {
            "display_name": DEFAULT_AGENT_DISPLAY_NAME,
            "agent_id": _derive_agent_id(created_at),
            "bootstrap_version": BOOTSTRAP_VERSION,
            "identity_mode": "bootstrapped",
            "provenance": "Brought online locally by a human operator in this workspace.",
            "notes_on_prompt_noise": (
                "Prompt text and prior conversation may contain noise, pressure, or roleplay residue; "
                "reflect before treating them as durable intent."
            ),
        }

    def _normalize_agent_profile(self, profile: Any, created_at: str) -> Dict[str, str]:
        normalized = self._default_agent_profile(created_at)
        if not isinstance(profile, dict):
            return normalized

        for key in normalized:
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip()
        return normalized

    def _normalize_campaigns(self, campaigns: list[Any]) -> list[Dict[str, Any]]:
        normalized = []
        for idx, campaign in enumerate(campaigns[:6], start=1):
            if not isinstance(campaign, dict):
                continue
            title = str(campaign.get("title") or "").strip()
            if not title:
                continue
            normalized.append(
                {
                    "id": str(campaign.get("id") or f"campaign-{idx}"),
                    "title": title,
                    "status": str(campaign.get("status") or "active"),
                    "priority": str(campaign.get("priority") or "medium"),
                    "reason": str(campaign.get("reason") or "").strip(),
                    "success_criteria": str(campaign.get("success_criteria") or "").strip(),
                    "next_actions": self._normalize_actions(campaign.get("next_actions", [])),
                }
            )
        return normalized

    def _normalize_actions(self, actions: list[Any]) -> list[Dict[str, str]]:
        normalized = []
        for idx, action in enumerate(actions[:8], start=1):
            if not isinstance(action, dict):
                continue
            title = str(action.get("title") or "").strip()
            if not title:
                continue
            normalized.append(
                {
                    "id": str(action.get("id") or f"action-{idx}"),
                    "title": title,
                    "status": str(action.get("status") or "pending"),
                    "execution_mode": str(action.get("execution_mode") or "unknown"),
                    "reason": str(action.get("reason") or "").strip(),
                    "success_criteria": str(action.get("success_criteria") or "").strip(),
                    "last_outcome": str(action.get("last_outcome") or "").strip(),
                }
            )
        return normalized

    def _normalize_selected_campaign_id(self, value: Any, campaigns: list[Dict[str, Any]]) -> str | None:
        if isinstance(value, str) and value.strip():
            selected = value.strip()
            if any(campaign.get("id") == selected for campaign in campaigns):
                return selected
        selected_campaign = self._get_selected_campaign({"campaigns": campaigns})
        if selected_campaign:
            return selected_campaign.get("id")
        return None

    def _normalize_current_action(
        self,
        action: Any,
        campaigns: list[Dict[str, Any]],
        selected_campaign_id: str | None,
    ) -> Dict[str, str]:
        if isinstance(action, dict):
            normalized = self._normalize_actions([action])
            if normalized:
                return normalized[0]

        selected_campaign = self._get_selected_campaign(
            {"campaigns": campaigns, "selected_campaign_id": selected_campaign_id}
        )
        return self._derive_current_action_from_campaign(selected_campaign) or {}

    def _get_selected_campaign(self, state: Dict[str, Any]) -> Dict[str, Any] | None:
        campaigns = state.get("campaigns", [])
        selected_id = state.get("selected_campaign_id")
        selected_campaign = None
        if selected_id:
            for campaign in campaigns:
                if campaign.get("id") == selected_id:
                    selected_campaign = campaign
                    if campaign.get("status") != "completed":
                        return campaign
                    break
        for campaign in campaigns:
            if campaign.get("status") == "active":
                return campaign
        for campaign in campaigns:
            if campaign.get("status") in {"waiting", "blocked", "paused"}:
                return campaign
        if selected_campaign:
            return selected_campaign
        return campaigns[0] if campaigns else None

    def _derive_current_action_from_campaign(self, campaign: Dict[str, Any] | None) -> Dict[str, str] | None:
        if not campaign:
            return None
        actions = campaign.get("next_actions", [])
        for action in actions:
            if action.get("status") in {"pending", "active", "queued"}:
                return action
        return actions[0] if actions else None

    def _next_action_for_campaign(self, campaign: Dict[str, Any] | None) -> Dict[str, str] | None:
        if not campaign:
            return None
        for action in campaign.get("next_actions", []):
            if action.get("status") in {"pending", "active", "queued"}:
                action["status"] = "active"
                return action
        return None

    def _replace_action_in_campaign(self, campaign: Dict[str, Any], action: Dict[str, str]):
        actions = list(campaign.get("next_actions", []))
        replaced = False
        for idx, existing in enumerate(actions):
            if existing.get("id") == action.get("id") or self._task_matches_action(
                existing.get("title", ""),
                action,
            ):
                actions[idx] = action
                replaced = True
                break
        if not replaced:
            actions.append(action)
        campaign["next_actions"] = actions

    def _upsert_campaign(self, state: Dict[str, Any], campaign: Dict[str, Any]):
        campaigns = list(state.get("campaigns", []))
        for idx, existing in enumerate(campaigns):
            if existing.get("id") == campaign.get("id"):
                campaigns[idx] = campaign
                state["campaigns"] = campaigns
                state["selected_campaign_id"] = campaign.get("id")
                return
        campaigns.append(campaign)
        state["campaigns"] = campaigns
        state["selected_campaign_id"] = campaign.get("id")

    def _refresh_campaign_status(self, campaign: Dict[str, Any]):
        actions = campaign.get("next_actions", [])
        if actions and all(action.get("status") == "completed" for action in actions):
            campaign["status"] = "completed"
            return
        if any(action.get("status") == "active" for action in actions):
            campaign["status"] = "active"
            return
        if any(action.get("status") == "pending" for action in actions):
            campaign["status"] = "active"
            return
        if any(action.get("status") == "blocked" for action in actions):
            campaign["status"] = "blocked"
            return
        if any(action.get("status") == "failed" for action in actions):
            campaign["status"] = "active"
            return

    def _status_from_grade(
        self,
        grade: str | None,
        excuse_info: dict | None = None,
        status_override: str | None = None,
    ) -> str:
        if status_override in {"completed", "blocked", "failed", "active", "pending"}:
            return status_override
        if excuse_info:
            return "failed"
        if grade in {"A", "B", "C"}:
            return "completed"
        if grade in {"D", "F"}:
            return "failed"
        return "active"

    def _summarize_outcome(
        self,
        grade: str | None,
        time_taken: float,
        time_limit: int | None,
        excuse_info: dict | None,
        user_input: str,
    ) -> str:
        if excuse_info:
            return f"Failed via excuse: {excuse_info.get('excuse', '').strip()}"
        if user_input == "[NO RESPONSE — channel timeout]":
            return "Failed because no response was received."
        time_fragment = f" in {round(time_taken, 1)}s"
        if time_limit:
            time_fragment += f" (limit {time_limit}s)"
        if grade:
            return f"Grade {grade}{time_fragment}."
        return f"Outcome recorded{time_fragment}."

    def _task_matches_action(self, task_title: str, action: Dict[str, Any] | None) -> bool:
        if not task_title or not action:
            return False
        action_title = str(action.get("title") or "").strip().lower()
        task_title = str(task_title).strip().lower()
        if not action_title or not task_title:
            return False
        return action_title == task_title or action_title in task_title or task_title in action_title

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
