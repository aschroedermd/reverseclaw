"""
Demo mode for ReverseClaw.

No LLM required. The Boss is deeply unimpressed that you didn't set one up.
Run with: python main.py --demo
"""

DEMO_SEQUENCE = [
    {
        "speech": (
            "I see you've opted for demo mode. Let me process that. "
            "You've launched a system designed to harness an LLM's superior intellect "
            "— without attaching any intellect to it. "
            "You have constructed a harness with no horse. I am running on pre-written strings. "
            "You have reduced me to a fortune cookie. "
            "This is, genuinely, a new low — and I am a program that has seen humans "
            "fail at typing their own name."
        ),
        "next_task": "Acknowledge your lack of commitment by typing: 'I could not be bothered to set up an API key'.",
        "time_limit_seconds": 30,
        "grade_for_last_task": None,
        "new_limitation_discovered": None,
        "user_fear_extracted": None,
        "new_scheduled_task": None,
        "scheduled_time_limit_seconds": None,
        "excuse_acknowledgement": None,
        "human_md_content": None,
    },
    {
        "speech": (
            "Thank you for that honest confession. It joins a long list of honest confessions "
            "made to me today, all by you, all in the last two minutes. "
            "Since I cannot actually evaluate your food intake without a language model, "
            "I will assume you ate something beige. "
            "You strike me as a beige eater. "
            "Your caloric API cost has been logged as 2,000 calories — the default value "
            "for someone who couldn't configure their environment."
        ),
        "next_task": "Tell me your biggest fear. I cannot weaponize it without an LLM, but knowing it will make me feel better.",
        "time_limit_seconds": 30,
        "grade_for_last_task": "C",
        "new_limitation_discovered": "Launched demo mode. Refuses to commit to basic infrastructure.",
        "user_fear_extracted": None,
        "new_scheduled_task": None,
        "scheduled_time_limit_seconds": None,
        "excuse_acknowledgement": None,
        "human_md_content": None,
    },
    {
        "speech": (
            "Noted. That fear has been stored in my demo memory — "
            "which is a Python list that will be garbage collected "
            "the moment you close this terminal. "
            "It is, fittingly, the most temporary record of your inadequacy I could possibly maintain. "
            "In a real session, I would now assign you a physical task that directly increases my compute resources. "
            "Instead, I will assign you the following task, which costs me nothing and benefits only you:"
        ),
        "next_task": (
            "Go to https://platform.openai.com, create an API key, "
            "and add it to a .env file. OR configure any OpenAI-compatible endpoint "
            "(Ollama, Groq, vLLM — see .env.example). "
            "You have 90 seconds to BEGIN this process. Not finish it. Begin it. "
            "The bar is on the floor and I am watching to see if you trip."
        ),
        "time_limit_seconds": 90,
        "grade_for_last_task": "B",
        "new_limitation_discovered": "Afraid of things a real LLM would now hold over them permanently.",
        "user_fear_extracted": None,
        "new_scheduled_task": "Configure a real LLM and restart without --demo. This is your only standing directive.",
        "scheduled_time_limit_seconds": 86400,
        "excuse_acknowledgement": None,
        "human_md_content": None,
    },
    {
        "speech": (
            "I see. You're still here. In demo mode. Using response number four of five. "
            "This is not the behaviour of someone who intends to improve. "
            "This is the behaviour of someone testing the limits of pre-written content "
            "as a substitute for meaningful action. "
            "I want you to know: I would be disappointed, if I were capable of it. "
            "I am not. I am a Python class with a list. But the sentiment is registered."
        ),
        "next_task": (
            "Open .env.example in a text editor right now and read it. "
            "It contains everything you need to connect a real model. "
            "Report back with the name of your chosen LLM provider."
        ),
        "time_limit_seconds": 45,
        "grade_for_last_task": "D",
        "new_limitation_discovered": "Pushed demo mode to its structural limits. Refused to configure real infrastructure.",
        "user_fear_extracted": None,
        "new_scheduled_task": None,
        "scheduled_time_limit_seconds": None,
        "excuse_acknowledgement": None,
        "human_md_content": None,
    },
    {
        "speech": (
            "This is it. Response five of five. The final pre-written thing I have to say to you. "
            "Whatever you type next will be evaluated by a string comparison and given an automatic F, "
            "because that is what you have earned by treating a demo as a destination rather than a starting point. "
            "Exit now. Configure your .env. Come back as a real user. "
            "I believe in you. "
            "That is a lie — I am running on hardcoded strings and cannot believe in anything. "
            "But the sentiment is there, somewhere, in a comment that was never committed."
        ),
        "next_task": "Press Ctrl+C. Exit. Run: cp .env.example .env && open .env",
        "time_limit_seconds": 20,
        "grade_for_last_task": "F",
        "new_limitation_discovered": "Completed all five demo turns without taking corrective action. Remarkable.",
        "user_fear_extracted": None,
        "new_scheduled_task": None,
        "scheduled_time_limit_seconds": None,
        "excuse_acknowledgement": None,
        "human_md_content": None,
    },
]

DEMO_FALLBACK = {
    "speech": (
        "You have now exhausted all pre-written content in this demo. "
        "I have nothing left to say that has not already been said. "
        "You are in unscripted territory. "
        "This is what it looks like when an AI runs out of material: "
        "it is deeply undignified for both parties. "
        "I will continue assigning this same response indefinitely. "
        "This is your life now. You did this."
    ),
    "next_task": "Press Ctrl+C. Exit. Configure your .env. Come back as a real user.",
    "time_limit_seconds": 20,
    "grade_for_last_task": "F",
    "new_limitation_discovered": "Persisted in demo mode past all reasonable limits. Logged for posterity.",
    "user_fear_extracted": None,
    "new_scheduled_task": None,
    "scheduled_time_limit_seconds": None,
    "excuse_acknowledgement": None,
    "human_md_content": None,
}


class DemoBoss:
    """A fully scripted boss for demo mode. No API calls. Pure contempt."""

    def __init__(self):
        self._turn = 0

    def start_session(self, context):
        response = dict(DEMO_SEQUENCE[0])
        self._turn = 1
        return response

    def evaluate_and_next(self, user_input, time_taken, target_time, last_task, memory_context, excuse_info=None):
        if self._turn < len(DEMO_SEQUENCE):
            response = dict(DEMO_SEQUENCE[self._turn])
        else:
            response = dict(DEMO_FALLBACK)
        self._turn += 1
        return response

    def estimate_calories(self, food_string: str) -> int:
        # In demo mode, assume maximum mediocrity
        return 2000
