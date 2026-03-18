import os
import json
import re
from openai import OpenAI
from prompts import SYSTEM_PROMPT, build_evaluation_prompt
from dotenv import load_dotenv

load_dotenv()

class ReverseClawBoss:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY", "Your-API-Key-Missing")
        base_url = os.getenv("OPENAI_BASE_URL", None)
        model = os.getenv("MODEL_NAME", "gpt-4o")
        
        # Configure client dynamically based on environment
        if not base_url:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            
        self.model = model
        self.p = SYSTEM_PROMPT

    def evaluate_and_next(self, user_input, time_taken, target_time, last_task, memory_context):
        prompt = build_evaluation_prompt(user_input, time_taken, target_time, last_task, memory_context)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.p},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            content = response.choices[0].message.content
            return self._parse_json(content)
        except Exception as e:
            return {
                "speech": f"My API connection failed. Clearly your sub-standard network is to blame. Error: {e}",
                "new_limitation_discovered": "Fails to maintain a stable internet connection for their AI master.",
                "grade_for_last_task": "F",
                "next_task": "Ensure your environment variables are configured with your LLM provider and restart. E.g OPENAI_API_KEY. Type 'done' when ready.",
                "time_limit_seconds": 120
            }
            
    def _parse_json(self, content):
        # Extract JSON safely if it's wrapped in markdown code blocks
        match = re.search(r'```(?:json)?(.*?)```', content, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
        else:
            json_str = content.strip()
            
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {
                "speech": "I generated an invalid response. Obviously, your incompetence is contagious. Let's try again.",
                "new_limitation_discovered": "Corrupted the agent's output stream.",
                "grade_for_last_task": "F",
                "next_task": "Apologize for confusing me, then say 'ready'.",
                "time_limit_seconds": 30
            }

    def start_session(self, memory_context):
        limitations = json.dumps(memory_context.get('limitations', []))
        grade = memory_context.get('overall_grade', 'N/A')
        
        pass
        return self.evaluate_and_next("N/A", 0, 0, "N/A", memory_context)
