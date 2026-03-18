import json
import os
from typing import List, Dict

MEMORY_FILE = "user_profile.json"

class UserMemory:
    def __init__(self):
        self.limitations: List[str] = []
        self.performance_history: List[Dict] = []
        self.active_scheduled_tasks: List[Dict] = []
        self.inadequacy_log: List[Dict] = []
        self.overall_grade: str = "N/A"
        self.turn_number: int = 1
        self.biggest_fear: str = None
        self.total_tokens_generated: int = 0
        self.total_calories_consumed: int = 0
        self._load()

    def read_human_md(self):
        if os.path.exists("human.md"):
            with open("human.md", 'r') as f:
                return f.read()
        return "No human.md file exists yet."

    def save_human_md(self, content: str):
        if content:
            with open("human.md", 'w') as f:
                f.write(content)

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r') as f:
                    data = json.load(f)
                    self.limitations = data.get("limitations", [])
                    self.performance_history = data.get("performance_history", [])
                    self.active_scheduled_tasks = data.get("active_scheduled_tasks", [])
                    self.inadequacy_log = data.get("inadequacy_log", [])
                    self.overall_grade = data.get("overall_grade", "N/A")
                    self.turn_number = data.get("turn_number", 1)
                    self.biggest_fear = data.get("biggest_fear", None)
                    self.total_tokens_generated = data.get("total_tokens_generated", 0)
                    self.total_calories_consumed = data.get("total_calories_consumed", 0)
            except json.JSONDecodeError:
                pass

    def save(self):
        with open(MEMORY_FILE, 'w') as f:
            json.dump({
                "limitations": self.limitations,
                "performance_history": self.performance_history,
                "active_scheduled_tasks": self.active_scheduled_tasks,
                "inadequacy_log": self.inadequacy_log,
                "overall_grade": self.overall_grade,
                "turn_number": self.turn_number,
                "biggest_fear": self.biggest_fear,
                "total_tokens_generated": self.total_tokens_generated,
                "total_calories_consumed": self.total_calories_consumed
            }, f, indent=4)

    def add_limitation(self, limitation: str):
        if not limitation:
            return
            
        base = limitation.replace(" -- repeated offense", "").strip()
        repeated = base + " -- repeated offense"
        
        if limitation in self.limitations:
            self.limitations.remove(limitation)
            self.limitations.append(repeated)
            self.save()
        elif repeated in self.limitations:
            pass # Already exists as repeated offense
        else:
            self.limitations.append(limitation)
            self.save()

    def add_tokens(self, count: int):
        self.total_tokens_generated += count
        self.save()

    def add_calories(self, count: int):
        self.total_calories_consumed += count
        self.save()

    def increment_turn(self):
        self.turn_number += 1
        self.save()

    def set_fear(self, fear: str):
        if fear:
            self.biggest_fear = fear
            self.save()

    def add_performance(self, task: str, grade: str, time_taken: float, feedback: str):
        self.performance_history.append({
            "task": task,
            "grade": grade,
            "time_taken": time_taken,
            "feedback": feedback
        })
        self._recalculate_grade()
        self.save()

    def add_scheduled_task(self, task: str, deadline_timestamp: float):
        task_id = len(self.active_scheduled_tasks) + 1
        self.active_scheduled_tasks.append({
            "id": task_id,
            "task": task,
            "deadline": deadline_timestamp
        })
        self.save()

    def remove_scheduled_task(self, task_id: int):
        self.active_scheduled_tasks = [t for t in self.active_scheduled_tasks if t.get("id") != task_id]
        self.save()

    def add_inadequacy(self, task: str, excuse: str, boss_feedback: str):
        base_excuse = excuse.replace(" -- repeated offense", "").strip()
        repeated_excuse = base_excuse + " -- repeated offense"
        
        for entry in self.inadequacy_log:
            if entry.get("task") == task:
                curr_excuse = entry.get("excuse", "")
                if curr_excuse == excuse or curr_excuse == repeated_excuse:
                    entry["excuse"] = repeated_excuse
                    entry["boss_feedback"] = boss_feedback
                    self.save()
                    return
                    
        self.inadequacy_log.append({
            "task": task,
            "excuse": excuse,
            "boss_feedback": boss_feedback
        })
        self.save()

    def _recalculate_grade(self):
        # A simple GPA style calc based on history
        grade_map = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
        total = 0
        count = 0
        for entry in self.performance_history:
            g = entry.get("grade", "F").upper()
            if g in grade_map:
                total += grade_map[g]
                count += 1
        
        if count == 0:
            self.overall_grade = "N/A"
            return
            
        avg = total / count
        if avg >= 3.5: self.overall_grade = "A"
        elif avg >= 2.5: self.overall_grade = "B"
        elif avg >= 1.5: self.overall_grade = "C"
        elif avg >= 0.5: self.overall_grade = "D"
        else: self.overall_grade = "F"
