import os
import tempfile
import unittest

from memory import UserMemory


class MemoryTests(unittest.TestCase):
    def test_uploaded_proof_persists_until_reviewed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                os.makedirs("human-work", exist_ok=True)
                with open(os.path.join("human-work", "research.md"), "w", encoding="utf-8") as f:
                    f.write("# Research\n")

                memory = UserMemory()
                snapshot = {"research.md": os.stat(os.path.join("human-work", "research.md")).st_mtime}
                memory.register_uploaded_files(
                    "Review backup options",
                    snapshot,
                    ["research.md"],
                    seen_at=123.0,
                )

                pending = memory.get_reviewable_proof_entries("Review backup options")
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["status"], "pending_review")

                memory.mark_proof_reviewed(
                    "Review backup options",
                    ["research.md"],
                    "A",
                    "2026-03-20 19:20:00 | grade A | Accepted as useful evidence.",
                    reviewed_at=456.0,
                )

                self.assertEqual(memory.get_reviewable_proof_entries("Review backup options"), [])
                self.assertEqual(memory.proof_artifacts[0]["status"], "reviewed")
                self.assertEqual(memory.proof_artifacts[0]["grade"], "A")
                self.assertIn("Accepted as useful evidence", memory.proof_artifacts[0]["review_summary"])
            finally:
                os.chdir(old_cwd)

    def test_duplicate_scheduled_tasks_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                memory = UserMemory()
                first_id = memory.add_scheduled_task("Create local backup", 100.0)
                second_id = memory.add_scheduled_task("Create local backup", 200.0)

                self.assertEqual(first_id, second_id)
                self.assertEqual(len(memory.active_scheduled_tasks), 1)
                self.assertEqual(memory.active_scheduled_tasks[0]["deadline"], 200.0)
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
