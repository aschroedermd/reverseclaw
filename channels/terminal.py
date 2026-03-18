"""Terminal channel — the default. Input/output stays in the Rich console."""

from typing import Optional

from rich.console import Console
from rich.prompt import Prompt

from .base import BaseChannel


class TerminalChannel(BaseChannel):
    """
    The default channel. send() is a no-op because the main loop handles
    all rich-formatted output directly via console.print(). receive() wraps
    Prompt.ask() so the main loop is channel-agnostic.
    """

    def __init__(self, console: Console):
        self.console = console

    def send(self, plain_text: str):
        # Terminal output is handled directly by main.py via console.print().
        # This channel does not duplicate it.
        pass

    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        return Prompt.ask("\n[bold green]Your Input[/bold green]")
