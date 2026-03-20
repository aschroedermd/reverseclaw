import tempfile
import unittest
from pathlib import Path

from agent_tools import AgentToolExecutor


class AgentToolExecutorTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "human-work").mkdir()
        self.tools = AgentToolExecutor(str(self.root))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_workspace_manifest_describes_special_files(self):
        result = self.tools.execute("get_workspace_manifest", {})
        self.assertTrue(result["ok"])

        manifest = result["result"]
        shared_paths = {item["path"] for item in manifest["shared_files"]}
        internal_paths = {item["path"] for item in manifest["derived_or_internal_files"]}

        self.assertIn("human.md", shared_paths)
        self.assertIn("human-work/", shared_paths)
        self.assertIn("goal-board.md", internal_paths)
        self.assertIn("journal.ai", internal_paths)

    def test_can_write_and_read_shared_text_file(self):
        write_result = self.tools.execute(
            "write_file",
            {"path": "human.md", "content": "# Human Profile\n\n- reliable on code reviews\n"},
        )
        self.assertTrue(write_result["ok"])

        read_result = self.tools.execute("read_file", {"path": "human.md"})
        self.assertTrue(read_result["ok"])
        self.assertIn("reliable on code reviews", read_result["result"]["content"])

    def test_protected_files_are_not_directly_accessible(self):
        write_result = self.tools.execute(
            "write_file",
            {"path": ".env", "content": "OPENAI_API_KEY=secret\n"},
        )
        self.assertFalse(write_result["ok"])

        self.tools.autonomy.ensure_initialized()
        read_result = self.tools.execute("read_file", {"path": "journal.ai"})
        self.assertFalse(read_result["ok"])

    def test_private_journal_roundtrip_uses_tool_interface(self):
        initial = self.tools.execute("read_private_journal", {})
        self.assertTrue(initial["ok"])
        self.assertIn("mission", initial["result"])

        write_result = self.tools.execute(
            "write_private_journal_entry",
            {
                "journal_entry": "Remember that the human can edit repo files when asked.",
                "observations": "Tool roundtrip test",
                "next_focus": "Use the workspace manifest before assigning setup tasks.",
            },
        )
        self.assertTrue(write_result["ok"])

        updated = self.tools.execute("read_private_journal", {"recent_entry_limit": 3})
        self.assertTrue(updated["ok"])
        self.assertEqual(
            updated["result"]["next_focus"],
            "Use the workspace manifest before assigning setup tasks.",
        )
        recent_entries = updated["result"]["recent_entries"]
        self.assertTrue(
            any("Remember that the human can edit repo files when asked." in entry["journal_entry"] for entry in recent_entries)
        )
        self.assertTrue((self.root / "goal-board.md").exists())


if __name__ == "__main__":
    unittest.main()
