import tempfile
import unittest
from pathlib import Path

from autonomy import AutonomyManager


class AutonomyTests(unittest.TestCase):
    def test_default_state_includes_bootstrap_identity_and_routing_guidance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            autonomy = AutonomyManager(
                privacy_path=str(root / "privacy.ai"),
                journal_path=str(root / "journal.ai"),
                goal_board_path=str(root / "goal-board.md"),
                agent_state_path=str(root / "ai-only" / "agent-state.json"),
            )

            state, created = autonomy.ensure_initialized()
            self.assertTrue(created)
            self.assertIn("agent_profile", state)
            self.assertEqual(state["agent_profile"]["display_name"], "ReverseClaw Agent")
            self.assertTrue(state["agent_profile"]["agent_id"].startswith("rc-"))
            self.assertIn("routing_guidance", state)
            self.assertTrue(state["routing_guidance"])
            self.assertIn("campaigns", state)
            self.assertTrue(state["campaigns"])
            self.assertIn("current_action", state)

            reloaded = autonomy.load_state()
            self.assertEqual(
                reloaded["agent_profile"]["agent_id"],
                state["agent_profile"]["agent_id"],
            )

            context = autonomy.build_context()
            self.assertEqual(
                context["agent_profile"]["agent_id"],
                state["agent_profile"]["agent_id"],
            )
            self.assertIn("mission_seed", context)
            self.assertIn("routing_guidance", context)

            goal_board = (root / "goal-board.md").read_text(encoding="utf-8")
            agent_state = (root / "ai-only" / "agent-state.json").read_text(encoding="utf-8")
            self.assertIn("campaign-continuity", agent_state)
            self.assertIn("## Agent Identity", goal_board)
            self.assertIn("## Active Campaign", goal_board)
            self.assertIn("## Current Action", goal_board)
            self.assertIn("## Routing Guidance", goal_board)

    def test_task_outcome_advances_current_action_and_updates_campaign(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            autonomy = AutonomyManager(
                privacy_path=str(root / "privacy.ai"),
                journal_path=str(root / "journal.ai"),
                goal_board_path=str(root / "goal-board.md"),
                agent_state_path=str(root / "ai-only" / "agent-state.json"),
            )

            autonomy.ensure_initialized()
            state = autonomy.load_state()
            campaign = state["campaigns"][0]
            first_action = campaign["next_actions"][0]
            second_action = campaign["next_actions"][1]

            autonomy.sync_current_action_from_directive(first_action["title"])
            autonomy.record_task_outcome(
                assigned_task=first_action["title"],
                grade="A",
                time_taken=42.0,
                time_limit=120,
                user_input="done",
                excuse_info=None,
            )

            updated = autonomy.load_state()
            updated_campaign = updated["campaigns"][0]
            updated_first = updated_campaign["next_actions"][0]
            updated_second = updated_campaign["next_actions"][1]

            self.assertEqual(updated_first["status"], "completed")
            self.assertIn("Grade A", updated_first["last_outcome"])
            self.assertEqual(updated["current_action"]["id"], second_action["id"])
            self.assertEqual(updated_second["status"], "active")


if __name__ == "__main__":
    unittest.main()
