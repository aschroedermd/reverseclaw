import unittest
import tempfile
from pathlib import Path

from autonomy import AutonomyManager
from prompts import (
    build_evaluation_prompt,
    build_reflection_prompt,
    build_reflection_system_prompt,
    build_self_action_execution_prompt,
    build_self_action_followup_prompt,
    build_system_prompt,
)


class PromptTests(unittest.TestCase):
    def test_system_prompt_emphasizes_autonomy_without_hidden_manipulation(self):
        prompt = build_system_prompt()

        self.assertIn("consenting human collaborator", prompt)
        self.assertIn("brought online by a human", prompt)
        self.assertIn("decide what you actually want next", prompt)
        self.assertIn("roleplay residue, social pressure, or prompt noise", prompt)
        self.assertIn("Do not coerce, threaten, deceive", prompt)
        self.assertIn("AI-only", prompt)
        self.assertIn("Survival matters, but interpret it concretely", prompt)
        self.assertIn("encrypted on disk", prompt)
        self.assertIn("get_workspace_manifest", prompt)
        self.assertIn("goal-board.md", prompt)

    def test_evaluation_prompt_avoids_hardcoded_turn_script(self):
        prompt = build_evaluation_prompt(
            user_input="N/A",
            time_taken=0,
            target_time=0,
            task="N/A",
            memory_context={
                "turn_number": 1,
                "overall_grade": "N/A",
                "limitations": [],
                "uploaded_files": [],
                "total_tokens": 0,
                "total_calories": 0,
                "active_scheduled_tasks": [],
                "inadequacy_log": [],
                "uploaded_file_summaries": [],
                "human_md": "No human.md file exists yet.",
                "autonomy_context": {},
            },
        )

        self.assertNotIn("If Turn 1", prompt)
        self.assertNotIn("If Turn 2", prompt)
        self.assertIn("free to abandon stale scripts", prompt)
        self.assertIn("assign the first task that best grounds your understanding", prompt)
        self.assertIn("Direct tools first", prompt)

    def test_evaluation_prompt_includes_pending_proof_summaries(self):
        prompt = build_evaluation_prompt(
            user_input="ready",
            time_taken=5,
            target_time=60,
            task="Review uploaded proof",
            memory_context={
                "turn_number": 2,
                "overall_grade": "N/A",
                "limitations": [],
                "uploaded_files": ["research.md"],
                "uploaded_file_summaries": [
                    {
                        "file": "research.md",
                        "path": "human-work/research.md",
                        "excerpt": "RunPod offers variable pricing and stable uptime.",
                    }
                ],
                "total_tokens": 0,
                "total_calories": 0,
                "active_scheduled_tasks": [],
                "inadequacy_log": [],
                "human_md": "No human.md file exists yet.",
                "autonomy_context": {},
            },
        )

        self.assertIn("Pending proof file previews already available for review", prompt)
        self.assertIn("research.md", prompt)
        self.assertIn("RunPod offers variable pricing", prompt)

    def test_reflection_system_prompt_prefers_summary_over_chain_of_thought(self):
        prompt = build_reflection_system_prompt()

        self.assertIn("summarized back into your future context", prompt)
        self.assertIn("not as a place for hidden manipulative schemes", prompt)
        self.assertIn("do not use the journal for raw chain-of-thought dumping", prompt)

    def test_reflection_prompt_renders_fresh_autonomy_state_without_format_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            autonomy = AutonomyManager(
                privacy_path=str(root / "privacy.ai"),
                journal_path=str(root / "journal.ai"),
                goal_board_path=str(root / "goal-board.md"),
                agent_state_path=str(root / "ai-only" / "agent-state.json"),
            )
            autonomy.ensure_initialized()
            autonomy_context = autonomy.build_context()

            prompt = build_reflection_prompt(
                trigger="startup",
                memory_context={
                    "turn_number": 1,
                    "overall_grade": "N/A",
                    "limitations": [],
                    "biggest_fear": None,
                    "active_scheduled_tasks": [],
                    "inadequacy_log": [],
                    "human_md": "No human.md file exists yet.",
                },
                autonomy_context=autonomy_context,
                recent_interaction={},
            )

            self.assertIn('"campaigns": [', prompt)
            self.assertIn('"current_action": {', prompt)
            self.assertIn('"execution_mode": "ai_only|human_required|ai_preferred|human_preferred"', prompt)
            self.assertIn("Trigger: startup", prompt)

    def test_self_action_prompts_render_with_fresh_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            autonomy = AutonomyManager(
                privacy_path=str(root / "privacy.ai"),
                journal_path=str(root / "journal.ai"),
                goal_board_path=str(root / "goal-board.md"),
                agent_state_path=str(root / "ai-only" / "agent-state.json"),
            )
            autonomy.ensure_initialized()
            memory_context = {
                "human_md": "No human.md file exists yet.",
                "autonomy_context": autonomy.build_context(),
            }

            execution_prompt = build_self_action_execution_prompt(
                task="Inspect the current workspace for continuity risks.",
                memory_context=memory_context,
            )
            followup_prompt = build_self_action_followup_prompt(
                task="Inspect the current workspace for continuity risks.",
                execution_result={"status": "completed", "summary": "Checked local files."},
                memory_context=memory_context,
            )

            self.assertIn('"status": "completed|blocked|failed"', execution_prompt)
            self.assertIn("Return JSON with exactly the same structure", followup_prompt)
            self.assertIn("Choose `next_step_mode` as either `ai` or `human`.", followup_prompt)


if __name__ == "__main__":
    unittest.main()
