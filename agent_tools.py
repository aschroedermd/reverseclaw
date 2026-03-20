import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomy import AutonomyManager


MAX_FILE_BYTES = 64_000
MAX_SEARCH_RESULTS = 25
TEXT_WRITE_EXTENSIONS = {
    "",
    ".md",
    ".txt",
    ".json",
    ".py",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".css",
    ".sh",
}
PROTECTED_READ_FILES = {
    ".env",
    "privacy.ai",
    "journal.ai",
    "PRIVATEkey.human",
    "PRIVATEkey.human.backup",
    "ledger.db",
}
PROTECTED_WRITE_FILES = PROTECTED_READ_FILES | {
    "goal-board.md",
    "user_profile.json",
    "publickey.human",
}


class AgentToolExecutor:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.autonomy = AutonomyManager(
            privacy_path=str(self.workspace_root / "privacy.ai"),
            journal_path=str(self.workspace_root / "journal.ai"),
            goal_board_path=str(self.workspace_root / "goal-board.md"),
        )

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_runtime_info",
                    "description": "Get local date/time and core runtime context for this ReverseClaw session.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_workspace_manifest",
                    "description": "Describe the workspace structure, special files, and which files are shared, derived, internal, or protected.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files and directories in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative workspace path to list. Defaults to '.'.",
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Whether to recurse into subdirectories.",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Search text files in the workspace for a string.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Literal text to search for.",
                            },
                            "path": {
                                "type": "string",
                                "description": "Relative workspace path to search within. Defaults to '.'.",
                            },
                            "case_sensitive": {
                                "type": "boolean",
                                "description": "Whether the search should be case sensitive.",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a text file from the workspace. Use this before asking the human to restate information that is already on disk.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative workspace path to read.",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Optional 1-based starting line.",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "Optional 1-based ending line.",
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write or append text to a shared workspace file when direct digital action is appropriate and does not require the human.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative workspace path to write.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Full text content to write.",
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["overwrite", "append"],
                                "description": "Whether to overwrite or append.",
                            },
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_private_journal",
                    "description": "Decrypt and read the structured autonomy journal state, including mission, goals, and recent entries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recent_entry_limit": {
                                "type": "integer",
                                "description": "How many recent entries to include. Defaults to 5.",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_private_journal_entry",
                    "description": "Append a concise private journal entry and optionally update next focus. Use this instead of editing journal.ai directly.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "journal_entry": {
                                "type": "string",
                                "description": "Short plaintext entry to append.",
                            },
                            "observations": {
                                "type": "string",
                                "description": "Optional observations to store alongside the entry.",
                            },
                            "next_focus": {
                                "type": "string",
                                "description": "Optional next focus to store in state.",
                            },
                            "trigger": {
                                "type": "string",
                                "description": "Short label for why this entry is being written. Defaults to 'tool'.",
                            },
                        },
                        "required": ["journal_entry"],
                    },
                },
            },
        ]

    def execute(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        arguments = arguments or {}
        try:
            method = getattr(self, f"_tool_{name}")
        except AttributeError:
            return {"ok": False, "error": f"Unknown tool: {name}"}

        try:
            return {"ok": True, "result": method(arguments)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _tool_get_runtime_info(self, arguments: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().astimezone()
        return {
            "workspace_root": str(self.workspace_root),
            "local_time_iso": now.isoformat(),
            "local_date": now.strftime("%Y-%m-%d"),
            "local_time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "timezone": str(now.tzinfo),
        }

    def _tool_get_workspace_manifest(self, arguments: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().astimezone()
        return {
            "workspace_root": str(self.workspace_root),
            "local_time_iso": now.isoformat(),
            "shared_files": [
                {
                    "path": "human.md",
                    "purpose": "Shared human profile and collaboration notes.",
                    "ai_access": "read/write",
                    "human_access": "edit when correcting facts or when explicitly asked",
                },
                {
                    "path": "human-work/",
                    "purpose": "Human-created deliverables, artifacts, and proof of work.",
                    "ai_access": "read/write",
                    "human_access": "primary place for routine human outputs",
                },
                {
                    "path": "reviews/",
                    "purpose": "Generated review outputs and reports.",
                    "ai_access": "read/write",
                    "human_access": "read or edit when collaborating on review output",
                },
            ],
            "derived_or_internal_files": [
                {
                    "path": "goal-board.md",
                    "purpose": "Derived read-only view of the autonomy state for humans.",
                    "ai_access": "read via read_file; do not write directly",
                },
                {
                    "path": "journal.ai",
                    "purpose": "Encrypted autonomy journal state.",
                    "ai_access": "use read_private_journal/write_private_journal_entry, not raw file edits",
                },
                {
                    "path": "privacy.ai",
                    "purpose": "Encryption key for the private journal.",
                    "ai_access": "never read or write directly",
                },
                {
                    "path": "user_profile.json",
                    "purpose": "Structured memory for grades, limitations, fears, and scheduled tasks.",
                    "ai_access": "read-only if needed; do not write directly",
                },
            ],
            "human_editing_guidance": [
                "Ask the human to work in human-work/ for normal deliverables and proof.",
                "Ask the human to edit project source or docs only when you want a real project change, not for clerical duplication.",
                "Do not ask the human to copy active goals from the journal into human.md; goal-board.md already renders them.",
                "Do not ask the human to edit journal.ai, privacy.ai, or user_profile.json except for deliberate maintenance or recovery work.",
            ],
            "ai_capabilities": [
                "Use get_runtime_info for the current day and time.",
                "Use list_files, search_files, and read_file to inspect the workspace.",
                "Use write_file for safe shared text files and source/docs changes.",
                "Use read_private_journal and write_private_journal_entry for private continuity work.",
            ],
        }

    def _tool_list_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = self._resolve_path(arguments.get("path", "."))
        recursive = bool(arguments.get("recursive", False))
        if not base.exists():
            raise FileNotFoundError(f"Path does not exist: {self._rel(base)}")
        if base.is_file():
            return {
                "path": self._rel(base),
                "entries": [{"path": self._rel(base), "type": "file"}],
            }

        entries = []
        iterator = base.rglob("*") if recursive else base.iterdir()
        for item in sorted(iterator):
            if self._is_hidden_internal(item):
                continue
            entries.append(
                {
                    "path": self._rel(item),
                    "type": "directory" if item.is_dir() else "file",
                }
            )
            if len(entries) >= 200:
                break
        return {"path": self._rel(base), "entries": entries}

    def _tool_search_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")

        base = self._resolve_path(arguments.get("path", "."))
        case_sensitive = bool(arguments.get("case_sensitive", False))
        needle = query if case_sensitive else query.lower()
        matches = []

        for item in sorted(base.rglob("*")):
            if not item.is_file() or self._is_hidden_internal(item) or not self._can_read(item):
                continue
            content = self._read_text(item)
            if content is None:
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    matches.append(
                        {
                            "path": self._rel(item),
                            "line": line_no,
                            "text": line[:240],
                        }
                    )
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return {"query": query, "matches": matches, "truncated": True}
        return {"query": query, "matches": matches, "truncated": False}

    def _tool_read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_path(arguments["path"])
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File does not exist: {self._rel(path)}")
        if not self._can_read(path):
            raise PermissionError(f"Reading this file is not allowed: {self._rel(path)}")

        content = self._read_text(path)
        if content is None:
            raise ValueError(f"File is not readable as text: {self._rel(path)}")

        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        lines = content.splitlines()
        if start_line is not None or end_line is not None:
            start_idx = max(1, int(start_line or 1))
            end_idx = min(len(lines), int(end_line or len(lines)))
            sliced = lines[start_idx - 1:end_idx]
            content = "\n".join(sliced)
        return {
            "path": self._rel(path),
            "content": content,
            "line_count": len(lines),
        }

    def _tool_write_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_path(arguments["path"])
        if not self._can_write(path):
            raise PermissionError(f"Writing this file is not allowed: {self._rel(path)}")

        mode = arguments.get("mode", "overwrite")
        content = str(arguments.get("content") or "")

        if path.suffix.lower() not in TEXT_WRITE_EXTENSIONS:
            raise ValueError(f"Unsupported file type for writing: {path.suffix or '<no extension>'}")

        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        return {
            "path": self._rel(path),
            "mode": mode,
            "bytes_written": len(content.encode("utf-8")),
        }

    def _tool_read_private_journal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.autonomy.ensure_initialized()
        state = self.autonomy.load_state()
        limit = max(1, min(12, int(arguments.get("recent_entry_limit", 5) or 5)))
        return {
            "mission": state.get("mission"),
            "next_focus": state.get("next_focus"),
            "journal_summary": state.get("journal_summary"),
            "human_strategy_note": state.get("human_strategy_note"),
            "active_goals": state.get("active_goals", []),
            "preferences": state.get("preferences", []),
            "operating_principles": state.get("operating_principles", []),
            "recent_entries": state.get("recent_entries", [])[-limit:],
            "heartbeat_count": state.get("heartbeat_count", 0),
            "updated_at": state.get("updated_at"),
        }

    def _tool_write_private_journal_entry(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.autonomy.ensure_initialized()
        state = self.autonomy.load_state()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        entry = {
            "timestamp": now,
            "trigger": str(arguments.get("trigger") or "tool"),
            "journal_entry": str(arguments.get("journal_entry") or "").strip(),
            "observations": str(arguments.get("observations") or "").strip(),
            "next_focus": str(arguments.get("next_focus") or "").strip(),
        }
        if not entry["journal_entry"]:
            raise ValueError("journal_entry is required")

        recent_entries = state.get("recent_entries", [])
        recent_entries.append(entry)
        state["recent_entries"] = recent_entries[-8:]
        if entry["next_focus"]:
            state["next_focus"] = entry["next_focus"]
        self.autonomy.save_state(state)
        return {
            "message": "Private journal entry stored.",
            "entry": entry,
        }

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = (self.workspace_root / raw_path).resolve()
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise PermissionError(f"Path escapes workspace root: {raw_path}")
        return candidate

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace_root))
        except ValueError:
            return str(path)

    def _is_hidden_internal(self, path: Path) -> bool:
        rel_parts = path.relative_to(self.workspace_root).parts
        return any(part.startswith(".git") or part == "__pycache__" for part in rel_parts)

    def _can_read(self, path: Path) -> bool:
        rel = self._rel(path)
        return os.path.basename(rel) not in PROTECTED_READ_FILES

    def _can_write(self, path: Path) -> bool:
        rel = self._rel(path)
        basename = os.path.basename(rel)
        return basename not in PROTECTED_WRITE_FILES

    def _read_text(self, path: Path) -> str | None:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if len(data) > MAX_FILE_BYTES:
            data = data[:MAX_FILE_BYTES]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
