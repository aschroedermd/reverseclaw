import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from boss import ReverseClawBoss


def _response_with_message(message, finish_reason="stop", model="test-model", response_id="resp_test"):
    return SimpleNamespace(
        id=response_id,
        model=model,
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
    )


class BossRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.boss = ReverseClawBoss.__new__(ReverseClawBoss)
        self.boss.model = "test-model"
        self.boss.tool_specs = []
        self.boss.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(),
                )
            )
        )

    def test_extract_message_content_handles_structured_content_parts(self):
        message = SimpleNamespace(
            content=[
                {"type": "output_text", "text": "first"},
                SimpleNamespace(text="second"),
                {"type": "output_text", "text": {"value": "third"}},
            ],
            tool_calls=[],
        )

        extracted = self.boss._extract_message_content(message)

        self.assertEqual(extracted, "first\nsecond\nthird")

    def test_parse_json_uses_repair_path_before_fallback(self):
        self.boss._repair_json_output = Mock(return_value={"speech": "repaired"})

        parsed = self.boss._parse_json("not valid json", mode="evaluation")

        self.assertEqual(parsed, {"speech": "repaired"})
        self.boss._repair_json_output.assert_called_once()

    def test_parse_json_invalid_evaluation_fallback_does_not_grade_human(self):
        self.boss._repair_json_output = Mock(return_value=None)

        parsed = self.boss._parse_json("", mode="evaluation")

        self.assertTrue(parsed["_response_generation_failed"])
        self.assertIsNone(parsed["grade_for_last_task"])
        self.assertIsNone(parsed["new_limitation_discovered"])
        self.assertIn("Let's try again", parsed["speech"])

    def test_run_json_completion_retries_after_empty_completion(self):
        empty_message = SimpleNamespace(content="", tool_calls=[], refusal=None)
        valid_message = SimpleNamespace(content='{"speech":"ok"}', tool_calls=[], refusal=None)
        self.boss.client.chat.completions.create.side_effect = [
            _response_with_message(empty_message, response_id="resp_empty"),
            _response_with_message(valid_message, response_id="resp_valid"),
        ]

        content = self.boss._run_json_completion(
            system_prompt="system",
            user_prompt="user",
            temperature=0.1,
            max_tokens=256,
        )

        self.assertEqual(content, '{"speech":"ok"}')
        self.assertEqual(self.boss.client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
