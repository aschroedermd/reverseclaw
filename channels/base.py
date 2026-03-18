"""Abstract base class for all ReverseClaw input/output channels."""

from abc import ABC, abstractmethod
from typing import Optional


class BaseChannel(ABC):
    """
    A channel handles sending directives to the human and receiving their responses.
    Terminal is the default. Discord/Telegram/WhatsApp are optional external channels.
    """

    @abstractmethod
    def send(self, plain_text: str):
        """
        Send a plain-text message to the channel.
        The terminal channel is a no-op here (rich console handles it directly).
        External channels strip rich markup and post to their platform.
        """
        pass

    @abstractmethod
    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        """
        Receive a response from the human.
        Returns None on timeout or channel failure.
        """
        pass

    def close(self):
        """Clean up channel resources. Override if needed."""
        pass
