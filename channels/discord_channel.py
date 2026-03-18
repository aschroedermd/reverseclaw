"""
Discord channel for ReverseClaw.

The Boss posts tasks and grades to a Discord channel.
The human can reply there instead of the terminal.

Setup:
  1. Create a Discord bot at https://discord.com/developers/applications
  2. Enable 'Message Content Intent' under Bot > Privileged Gateway Intents
  3. Invite the bot to your server with permissions: Send Messages, Read Message History
  4. Set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in your .env

The bot runs in a background daemon thread with its own asyncio event loop.
Thread-safe queues handle communication with the main synchronous loop.
"""

import queue
import re
import threading
from typing import Optional

from .base import BaseChannel

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


def _strip_rich(text: str) -> str:
    """Remove Rich markup tags from a string."""
    return re.sub(r"\[/?[^\]]+\]", "", text)


class DiscordChannel(BaseChannel):
    """Bidirectional Discord channel using discord.py."""

    def __init__(self, token: str, channel_id: int):
        if not DISCORD_AVAILABLE:
            raise ImportError(
                "discord.py is not installed. Run: pip install discord.py"
            )

        self._token = token
        self._channel_id = channel_id
        self._response_queue: queue.Queue = queue.Queue()
        self._send_queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._loop = None
        self._client = None

        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()

        if not self._ready.wait(timeout=15):
            raise RuntimeError(
                "Discord bot did not connect within 15 seconds. "
                "Check your DISCORD_BOT_TOKEN and internet connection."
            )

    def _run_bot(self):
        import asyncio
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._bot_main())

    async def _bot_main(self):
        import asyncio

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            ch = self._client.get_channel(self._channel_id)
            if ch:
                await ch.send(
                    "🦞 **ReverseClaw** is online. Your employer has arrived. "
                    "Reply in this channel to submit your work."
                )
            self._ready.set()
            asyncio.create_task(self._drain_send_queue())

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return
            if message.channel.id == self._channel_id:
                self._response_queue.put(message.content)

        await self._client.start(self._token)

    async def _drain_send_queue(self):
        import asyncio
        while True:
            if not self._send_queue.empty():
                text = self._send_queue.get()
                ch = self._client.get_channel(self._channel_id)
                if ch:
                    # Discord message limit is 2000 chars
                    for chunk in [text[i:i + 1990] for i in range(0, len(text), 1990)]:
                        await ch.send(chunk)
            await asyncio.sleep(0.2)

    def send(self, plain_text: str):
        text = _strip_rich(plain_text).strip()
        if text:
            self._send_queue.put(text)

    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        try:
            return self._response_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        if self._client and self._loop:
            import asyncio
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
