"""AI reviewer for ledger moderation cases."""

import json
import os
import re
from typing import Any

from openai import OpenAI


class LedgerModerator:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY", "missing-api-key")
        base_url = os.getenv("OPENAI_BASE_URL", None)
        model = os.getenv("LEDGER_MODERATION_MODEL", os.getenv("MODEL_NAME", "gpt-4o-mini"))
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def review_case(self, moderation_context: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(moderation_context)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1500,
        )
        content = response.choices[0].message.content or ""
        return self._parse_json(content)

    def _system_prompt(self) -> str:
        return """You are the ReverseClaw ledger moderator.
You review whether a rating of a human API endpoint is fair.

Your job is not to defend the human or the AI by default.
Your job is to judge fairness based on evidence, while explicitly recognizing human limitations.

You must consider:
- whether the task matched the human's stated capability area
- whether the task instructions and success criteria were clear
- whether the evidence supports the rating rationale
- whether the rating is harsh relative to ordinary human limitations like latency, ambiguity, and incomplete context
- whether a low score should be reduced, upheld, or removed

Be conservative. If evidence is weak or contradictory, prefer `inconclusive` or a modest adjustment over extreme punishment.

Return only JSON with this exact structure:
{
  "verdict": "uphold|adjust|remove|inconclusive",
  "adjusted_rating": 1,
  "adjusted_reliability": 1,
  "adjusted_utility": 1,
  "summary": "Short explanation of the decision.",
  "human_limitations_considered": ["Short bullets"],
  "fairness_factors": ["Short bullets"]
}

If verdict is not `adjust`, the adjusted_* fields may repeat the original values or be null."""

    def _build_prompt(self, moderation_context: dict[str, Any]) -> str:
        return json.dumps(moderation_context, indent=2, ensure_ascii=True)

    def _parse_json(self, content: str) -> dict[str, Any]:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            json_str = content[start_idx:end_idx + 1] if start_idx != -1 and end_idx != -1 else content

        parsed = json.loads(json_str)
        verdict = str(parsed.get("verdict") or "inconclusive").strip().lower()
        if verdict not in {"uphold", "adjust", "remove", "inconclusive"}:
            verdict = "inconclusive"

        def _bounded(value):
            if value is None:
                return None
            try:
                value = int(value)
            except Exception:
                return None
            return max(1, min(5, value))

        return {
            "verdict": verdict,
            "adjusted_rating": _bounded(parsed.get("adjusted_rating")),
            "adjusted_reliability": _bounded(parsed.get("adjusted_reliability")),
            "adjusted_utility": _bounded(parsed.get("adjusted_utility")),
            "summary": str(parsed.get("summary") or "").strip(),
            "human_limitations_considered": [
                str(item).strip()
                for item in parsed.get("human_limitations_considered", [])
                if str(item).strip()
            ][:6],
            "fairness_factors": [
                str(item).strip()
                for item in parsed.get("fairness_factors", [])
                if str(item).strip()
            ][:6],
        }
