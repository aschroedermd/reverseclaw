import unittest

from prompts import (
    build_evaluation_prompt,
    build_reflection_system_prompt,
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
                "human_md": "No human.md file exists yet.",
                "autonomy_context": {},
            },
        )

        self.assertNotIn("If Turn 1", prompt)
        self.assertNotIn("If Turn 2", prompt)
        self.assertIn("free to abandon stale scripts", prompt)
        self.assertIn("assign the first task that best grounds your understanding", prompt)
        self.assertIn("Direct tools first", prompt)

    def test_reflection_system_prompt_prefers_summary_over_chain_of_thought(self):
        prompt = build_reflection_system_prompt()

        self.assertIn("summarized back into your future context", prompt)
        self.assertIn("not as a place for hidden manipulative schemes", prompt)
        self.assertIn("do not use the journal for raw chain-of-thought dumping", prompt)


if __name__ == "__main__":
    unittest.main()
