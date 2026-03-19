import os
import json
import re
from openai import OpenAI
from prompts import (
    build_evaluation_prompt,
    build_reflection_prompt,
    build_reflection_system_prompt,
    build_system_prompt,
)
from dotenv import load_dotenv

load_dotenv()

class ReverseClawBoss:
    def __init__(self, pack: dict = None):
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

    def estimate_calories(self, food_string: str) -> int:
        prompt = "You are a calorie estimation API. The user provided a string describing what they ate today. Estimate the total calories. Return ONLY a raw integer with no other text, e.g. '1200' or '2500'. If you can't determine it, return '2000' as a safe default."
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": food_string}
                ],
                temperature=0.0,
                max_tokens=64
            )
            content = response.choices[0].message.content
            if content is None:
                content = ""
            content = content.strip()
            digits = ''.join(filter(str.isdigit, content))
            if digits: return int(digits)
            return 2000
        except Exception:
            return 2000

    def evaluate_and_next(self, user_input, time_taken, target_time, last_task, memory_context, excuse_info=None):
        prompt = build_evaluation_prompt(user_input, time_taken, target_time, last_task, memory_context, excuse_info)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.p},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4096
            )
            content = response.choices[0].message.content
            return self._parse_json(content, mode="evaluation")
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.reflection_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=4096
            )
            content = response.choices[0].message.content
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

    def start_session(self, memory_context):
        return self.evaluate_and_next("N/A", 0, 0, "N/A", memory_context)
