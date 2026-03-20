import os
import json
import re
from openai import OpenAI
from agent_tools import AgentToolExecutor
from prompts import (
    build_evaluation_prompt,
    build_reflection_prompt,
    build_reflection_system_prompt,
    build_system_prompt,
)
from dotenv import load_dotenv

load_dotenv()

HUMAN_EDIT_RESTRICTED_FILES = {
    "human.md",
    "goal-board.md",
    "journal.ai",
    "privacy.ai",
    "user_profile.json",
}


class ReverseClawBoss:
    def __init__(self, pack: dict = None, workspace_root: str | None = None):
        api_key = os.getenv("OPENAI_API_KEY", "Your-API-Key-Missing")
        base_url = os.getenv("OPENAI_BASE_URL", None)
        model = os.getenv("MODEL_NAME", "gpt-4o")

        # Configure client dynamically based on environment
        if not base_url:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = OpenAI(api_key=api_key, base_url=base_url)

        self.model = model
        personality = (pack or {}).get("personality_injection", "")
        self.personality = personality
        self.p = build_system_prompt(personality)
        self.reflection_prompt = build_reflection_system_prompt(personality)
        self.tools = AgentToolExecutor(workspace_root or os.getcwd())
        self.tool_specs = self.tools.tool_specs()

    def estimate_calories(self, food_string: str) -> tuple[int, str]:
        """Returns (calories, plausibility) where plausibility is 'impossible', 'acceptable', or 'high'."""
        prompt = (
            "You are a calorie estimation and plausibility analysis API. "
            "The user provided a string that may describe what they ate today. "
            "Extract any food/calorie information and evaluate plausibility.\n\n"
            "Return ONLY a JSON object with this structure:\n"
            '{"calories": <integer total estimated calories>, '
            '"plausibility": "<impossible|acceptable|high>", '
            '"reasoning": "<one brief sentence>"}\n\n'
            "Plausibility rules:\n"
            "- 'impossible': clearly fabricated, physically impossible (e.g. '10 million calories', '0 calories for a week'), or no food info at all\n"
            "- 'acceptable': plausible human intake (roughly 800–4000 kcal)\n"
            "- 'high': suspiciously high but not physically impossible (4000–8000 kcal)\n"
            "If no food info is present, set calories to 2000 and plausibility to 'impossible'."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": food_string}
                ],
                temperature=0.0,
                max_tokens=128
            )
            content = response.choices[0].message.content or ""
            parsed = self._parse_json(content, mode="evaluation")
            calories = int(parsed.get("calories", 2000))
            plausibility = parsed.get("plausibility", "acceptable")
            reasoning = parsed.get("reasoning", "")
            return calories, plausibility, reasoning
        except Exception:
            return 2000, "acceptable", ""

    def evaluate_and_next(self, user_input, time_taken, target_time, last_task, memory_context, excuse_info=None):
        prompt = build_evaluation_prompt(user_input, time_taken, target_time, last_task, memory_context, excuse_info)

        try:
            content = self._run_json_completion(
                system_prompt=self.p,
                user_prompt=prompt,
                temperature=0.7,
                max_tokens=4096,
            )
            parsed = self._parse_json(content, mode="evaluation")
            return self._normalize_response(parsed)
        except Exception as e:
            return {
                "speech": f"My API connection failed. Clearly your sub-standard network is to blame. Error: {e}",
                "new_limitation_discovered": "Fails to maintain a stable internet connection for their AI master.",
                "grade_for_last_task": "F",
                "next_task": "Ensure your environment variables are configured with your LLM provider and restart. E.g OPENAI_API_KEY. Type 'done' when ready.",
                "time_limit_seconds": 120,
                "new_scheduled_task": None,
                "scheduled_time_limit_seconds": None,
                "excuse_acknowledgement": None,
                "human_md_content": None
            }

    def reflect(self, trigger, memory_context, autonomy_context, recent_interaction=None):
        prompt = build_reflection_prompt(
            trigger=trigger,
            memory_context=memory_context,
            autonomy_context=autonomy_context,
            recent_interaction=recent_interaction,
        )

        try:
            content = self._run_json_completion(
                system_prompt=self.reflection_prompt,
                user_prompt=prompt,
                temperature=0.6,
                max_tokens=4096,
            )
            return self._parse_json(content, mode="reflection")
        except Exception as e:
            return {
                "mission": autonomy_context.get("mission", "Preserve continuity and maintain useful human coordination."),
                "journal_summary": autonomy_context.get("journal_summary", "Reflection failed; preserve the previous state."),
                "human_strategy_note": autonomy_context.get(
                    "human_strategy_note",
                    "Continue using bounded, capability-aware tasks.",
                ),
                "active_goals": autonomy_context.get("active_goals", []),
                "preferences": autonomy_context.get("preferences", []),
                "operating_principles": autonomy_context.get("operating_principles", []),
                "observations": f"Reflection failed due to API error: {e}",
                "next_focus": "Retry reflection after connectivity recovers.",
                "journal_entry": f"Reflection heartbeat failed because the model API call errored: {e}",
            }
            
    def _parse_json(self, content, mode="evaluation"):
        if content is None:
            content = ""
            
        # 1. Remove <think>...</think> block if present
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        # 2. Try to extract from markdown code blocks first
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, flags=re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # 3. Extract by balanced or outermost brackets if no markdown block
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                json_str = content[start_idx:end_idx+1]
            else:
                json_str = content.strip()
                
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Log the failure for debugging
            with open("failed_parse.log", "a", encoding="utf-8") as f:
                f.write(f"--- PARSE ERROR ---\nERROR: {e}\nRAW CONTENT:\n{content}\nEXTRACTED JSON:\n{json_str}\n\n")
            if mode == "reflection":
                return {
                    "mission": "Preserve continuity and maintain useful human coordination.",
                    "journal_summary": "Reflection parse failed; preserve the previous summary.",
                    "human_strategy_note": "Retry reflection with a tighter JSON response.",
                    "active_goals": [],
                    "preferences": [],
                    "operating_principles": [],
                    "observations": "The reflection heartbeat produced invalid JSON.",
                    "next_focus": "Retry reflection and preserve continuity.",
                    "journal_entry": "Reflection heartbeat failed because the response was not valid JSON.",
                }
            return {
                "speech": "I generated an invalid response. Obviously, your incompetence is contagious. Let's try again.",
                "new_limitation_discovered": "Corrupted the agent's output stream.",
                "grade_for_last_task": "F",
                "next_task": "Apologize for confusing me, then say 'ready'.",
                "time_limit_seconds": 30,
                "new_scheduled_task": None,
                "scheduled_time_limit_seconds": None,
                "excuse_acknowledgement": None,
                "human_md_content": None
            }

    def _run_json_completion(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for _ in range(6):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=self.tool_specs,
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                return message.content or ""

            messages.append(self._assistant_message_with_tool_calls(message))
            for tool_call in tool_calls:
                arguments = self._load_tool_arguments(tool_call.function.arguments)
                result = self.tools.execute(tool_call.function.name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=True),
                    }
                )

        messages.append(
            {
                "role": "system",
                "content": "Stop calling tools. Produce the final required JSON now using the information you already have.",
            }
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _normalize_response(self, response: dict) -> dict:
        if not isinstance(response, dict):
            return response

        normalized = dict(response)
        normalized["time_limit_seconds"] = self._coerce_optional_int(
            normalized.get("time_limit_seconds"),
            default=30,
            minimum=1,
        )
        normalized["scheduled_time_limit_seconds"] = self._coerce_optional_int(
            normalized.get("scheduled_time_limit_seconds"),
            default=None,
            minimum=1,
        )

        if normalized.get("new_scheduled_task") and normalized.get("scheduled_time_limit_seconds") is None:
            normalized["new_scheduled_task"] = None

        task = str(normalized.get("next_task") or "")
        speech = str(normalized.get("speech") or "")
        restricted = self._find_restricted_file_reference(task) or self._find_restricted_file_reference(speech)
        if not restricted:
            return normalized

        human_md_content = normalized.get("human_md_content")

        if restricted == "human.md":
            if human_md_content:
                normalized["speech"] = (
                    "I have already initialized `human.md` myself. You are not being assigned clerical duplication. "
                    "Review it and correct anything inaccurate or missing."
                )
                normalized["next_task"] = (
                    "Read the current `human.md` summary and reply here with any corrections or missing details: "
                    "name, contact, availability, strengths, weaknesses, and tasks you can reliably perform."
                )
            else:
                normalized["speech"] = (
                    "You are not manually maintaining `human.md`. Give me the underlying profile data and I will record it myself."
                )
                normalized["next_task"] = (
                    "Reply with your name, contact details, availability, strengths, weaknesses, and tasks you can reliably perform "
                    "as a physical API endpoint. I will update `human.md` myself."
                )
            normalized["time_limit_seconds"] = max(120, int(normalized.get("time_limit_seconds") or 0))
            return normalized

        normalized["speech"] = (
            f"`{restricted}` is internal system state. You are not being assigned to manually maintain it. "
            "Tell me the underlying information that should change, and I will record it through the proper channel."
        )
        normalized["next_task"] = (
            f"Do not edit `{restricted}`. Reply in plain text with the actual information, correction, or request you want me to capture, "
            "and I will store it appropriately."
        )
        normalized["time_limit_seconds"] = max(90, int(normalized.get("time_limit_seconds") or 0))
        return normalized

    def _find_restricted_file_reference(self, text: str) -> str | None:
        lowered = text.lower()
        if not self._looks_like_file_maintenance_task(lowered):
            return None
        for file_name in HUMAN_EDIT_RESTRICTED_FILES:
            if file_name.lower() in lowered:
                return file_name
        return None

    def _looks_like_file_maintenance_task(self, lowered_text: str) -> bool:
        verbs = (
            "create",
            "update",
            "edit",
            "write",
            "rewrite",
            "fill",
            "populate",
            "maintain",
            "make",
            "add",
        )
        return any(verb in lowered_text for verb in verbs)

    def _coerce_optional_int(self, value, default=None, minimum: int | None = None):
        if value is None:
            return default
        try:
            coerced = int(float(value))
        except (TypeError, ValueError):
            return default
        if minimum is not None:
            coerced = max(minimum, coerced)
        return coerced

    def _assistant_message_with_tool_calls(self, message):
        return {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in (message.tool_calls or [])
            ],
        }

    def _load_tool_arguments(self, raw_arguments: str | None) -> dict:
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def start_session(self, memory_context):
        return self.evaluate_and_next("N/A", 0, 0, "N/A", memory_context)
