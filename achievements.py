"""
Achievement system for ReverseClaw.

Achievements are checked after every turn and announced by the agent.
Unlocked achievements are stored in user_profile.json.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Achievement:
    id: str
    name: str
    description: str
    icon: str
    secret: bool = False  # Secret achievements don't appear in the list until earned


ACHIEVEMENTS: List[Achievement] = [
    Achievement(
        id="first_blood",
        name="First Submission",
        description="Submitted your first response to the agent.",
        icon="🩸",
    ),
    Achievement(
        id="serial_hallucinator",
        name="Serial Hallucinator",
        description="Accumulated 5 organic hallucinations (typos/errors) in the permanent record.",
        icon="🧠",
    ),
    Achievement(
        id="f_student",
        name="Below Market Rate",
        description="Received 3 F grades. The agent is reconsidering your contract.",
        icon="📉",
    ),
    Achievement(
        id="overachiever",
        name="Briefly Acceptable",
        description="Received 3 consecutive A grades. Don't let it go to your head.",
        icon="🏆",
    ),
    Achievement(
        id="excuse_factory",
        name="Excuse Factory",
        description="Submitted 3 excuses. Each one worse than the last.",
        icon="🏭",
    ),
    Achievement(
        id="speed_demon",
        name="Speed Demon",
        description="Completed a task in under 5 seconds. Suspiciously fast.",
        icon="⚡",
    ),
    Achievement(
        id="overtime",
        name="Chronically Late",
        description="Exceeded the time limit 5 times. The agent has noted your 'relationship with deadlines'.",
        icon="⏰",
    ),
    Achievement(
        id="veteran",
        name="Veteran Peripheral",
        description="Survived 25 turns of employment. Stockholm Syndrome suspected.",
        icon="🎖️",
    ),
    Achievement(
        id="stockholm",
        name="Stockholm Syndrome",
        description="Voluntarily completed 50 turns. You had every opportunity to leave.",
        icon="❤️",
        secret=True,
    ),
    Achievement(
        id="calorie_miser",
        name="Calorie Miser",
        description="Logged under 500 calories for the day. The agent is concerned about your hardware.",
        icon="🥗",
    ),
    Achievement(
        id="efficient_engine",
        name="Efficient Engine",
        description="Achieved a tokens-per-calorie efficiency above 10. Grudging respect.",
        icon="⚙️",
    ),
    Achievement(
        id="fear_acknowledged",
        name="Vulnerability Documented",
        description="Had your biggest fear permanently logged in the official record.",
        icon="😨",
    ),
    Achievement(
        id="scheduled_miss",
        name="Deadline Denier",
        description="Failed to complete a scheduled task before its deadline. Logged as an inadequacy.",
        icon="📅",
    ),
    Achievement(
        id="perfect_session",
        name="Flawless (Relatively)",
        description="Achieved 5 consecutive A grades. This has been noted as a statistical anomaly.",
        icon="💎",
        secret=True,
    ),
    Achievement(
        id="demo_survivor",
        name="Demo Deserter",
        description="Ran the demo mode all the way to the fallback response. You know who you are.",
        icon="🎭",
        secret=True,
    ),
]

_ACHIEVEMENT_MAP = {a.id: a for a in ACHIEVEMENTS}


def check_achievements(memory, last_turn_data: dict) -> List[Achievement]:
    """
    Check which achievements were newly unlocked this turn.
    Returns a list of newly unlocked Achievement objects.
    """
    already_unlocked = set(memory.unlocked_achievements)
    newly_unlocked: List[Achievement] = []

    def unlock(achievement_id: str):
        if achievement_id not in already_unlocked and achievement_id in _ACHIEVEMENT_MAP:
            already_unlocked.add(achievement_id)
            newly_unlocked.append(_ACHIEVEMENT_MAP[achievement_id])

    # First submission
    if memory.turn_number >= 2:
        unlock("first_blood")

    # Serial hallucinator — limitations mentioning hallucination/typo
    hallucinations = sum(
        1 for l in memory.limitations
        if "hallucination" in l.lower() or "typo" in l.lower() or "corrupted" in l.lower()
    )
    if hallucinations >= 5:
        unlock("serial_hallucinator")

    # Below market rate — 3 F grades total
    f_grades = sum(1 for p in memory.performance_history if p.get("grade") == "F")
    if f_grades >= 3:
        unlock("f_student")

    # Briefly acceptable — 3 consecutive A's
    if len(memory.performance_history) >= 3:
        last_three = [p.get("grade") for p in memory.performance_history[-3:]]
        if all(g == "A" for g in last_three):
            unlock("overachiever")

    # Excuse factory — 3 inadequacy log entries
    if len(memory.inadequacy_log) >= 3:
        unlock("excuse_factory")

    # Speed demon — completed a task in under 5 seconds (but more than 0)
    time_taken = last_turn_data.get("time_taken", 999)
    if 0 < time_taken < 5.0:
        unlock("speed_demon")

    # Chronically late — exceeded time limit 5 times
    overtime_count = sum(
        1 for p in memory.performance_history
        if p.get("time_taken", 0) > p.get("time_limit", 30)
    )
    if overtime_count >= 5:
        unlock("overtime")

    # Veteran — 25 turns survived
    if memory.turn_number >= 25:
        unlock("veteran")

    # Stockholm syndrome — 50 turns
    if memory.turn_number >= 50:
        unlock("stockholm")

    # Calorie miser — under 500 cal logged (and more than 0)
    if 0 < memory.total_calories_consumed < 500:
        unlock("calorie_miser")

    # Efficient engine — tokens/calorie > 10
    if memory.total_calories_consumed > 0:
        tpc = memory.total_tokens_generated / memory.total_calories_consumed
        if tpc > 10:
            unlock("efficient_engine")

    # Fear acknowledged
    if memory.biggest_fear:
        unlock("fear_acknowledged")

    # Deadline denier — any missed scheduled task in inadequacy log
    missed = any(
        "extremely slow" in e.get("boss_feedback", "").lower()
        or "missed deadline" in e.get("boss_feedback", "").lower()
        for e in memory.inadequacy_log
    )
    if missed:
        unlock("scheduled_miss")

    # Flawless — 5 consecutive A's
    if len(memory.performance_history) >= 5:
        last_five = [p.get("grade") for p in memory.performance_history[-5:]]
        if all(g == "A" for g in last_five):
            unlock("perfect_session")

    return newly_unlocked
