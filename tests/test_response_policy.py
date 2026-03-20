import unittest

from boss import ReverseClawBoss


class ResponsePolicyTests(unittest.TestCase):
    def setUp(self):
        self.boss = ReverseClawBoss.__new__(ReverseClawBoss)

    def test_human_md_creation_task_is_rewritten_to_information_request(self):
        response = {
            "speech": "Create human.md with your details.",
            "next_task": "Create a file named human.md with your name, contact, availability, strengths, and weaknesses.",
            "time_limit_seconds": 300,
            "human_md_content": None,
        }

        normalized = self.boss._normalize_response(response)

        self.assertIn("not manually maintaining `human.md`", normalized["speech"])
        self.assertIn("Reply with your name, contact details, availability", normalized["next_task"])

    def test_human_md_review_is_requested_when_content_was_already_written(self):
        response = {
            "speech": "Create human.md with your details.",
            "next_task": "Create a file named human.md with your profile.",
            "time_limit_seconds": 300,
            "human_md_content": "# Human Profile\n\n- placeholder\n",
        }

        normalized = self.boss._normalize_response(response)

        self.assertIn("already initialized `human.md`", normalized["speech"])
        self.assertIn("Read the current `human.md` summary", normalized["next_task"])

    def test_internal_state_file_edit_task_is_blocked(self):
        response = {
            "speech": "Update goal-board.md with current mission data.",
            "next_task": "Edit goal-board.md to include all active goals.",
            "time_limit_seconds": 120,
        }

        normalized = self.boss._normalize_response(response)

        self.assertIn("internal system state", normalized["speech"])
        self.assertIn("Do not edit `goal-board.md`", normalized["next_task"])

    def test_numeric_string_fields_are_coerced_and_invalid_scheduled_deadlines_are_dropped(self):
        response = {
            "speech": "Proceed.",
            "next_task": "Do a normal task.",
            "time_limit_seconds": "300",
            "new_scheduled_task": "Long-running task",
            "scheduled_time_limit_seconds": "not-a-number",
        }

        normalized = self.boss._normalize_response(response)

        self.assertEqual(normalized["time_limit_seconds"], 300)
        self.assertIsNone(normalized["scheduled_time_limit_seconds"])
        self.assertIsNone(normalized["new_scheduled_task"])


if __name__ == "__main__":
    unittest.main()
