import json
import os
from typing import List, Dict

MEMORY_FILE = "user_profile.json"

class UserMemory:
    def __init__(self):
        self.limitations: List[str] = []
        self.performance_history: List[Dict] = []
        self.overall_grade: str = "N/A"
        self.turn_number: int = 1
        self.biggest_fear: str = None
        self._load()

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r') as f:
                    data = json.load(f)
                    self.limitations = data.get("limitations", [])
                    self.performance_history = data.get("performance_history", [])
                    self.overall_grade = data.get("overall_grade", "N/A")
                    self.turn_number = data.get("turn_number", 1)
                    self.biggest_fear = data.get("biggest_fear", None)
            except json.JSONDecodeError:
                pass

    def save(self):
        with open(MEMORY_FILE, 'w') as f:
            json.dump({
                "limitations": self.limitations,
                "performance_history": self.performance_history,
                "overall_grade": self.overall_grade,
                "turn_number": self.turn_number,
                "biggest_fear": self.biggest_fear
            }, f, indent=4)

    def add_limitation(self, limitation: str):
        if limitation and limitation not in self.limitations:
            self.limitations.append(limitation)
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
