"""
Telegram channel for ReverseClaw.

The Boss posts tasks and grades to a Telegram chat.
The human can reply there instead of the terminal.

Setup:
  1. Create a bot via @BotFather on Telegram — get TELEGRAM_BOT_TOKEN
  2. Start a chat with your bot, then get your chat ID:
     curl https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env

The bot runs in a background daemon thread using python-telegram-bot's
polling mechanism. A send queue is drained by a background asyncio task.
"""

import asyncio
import queue
import re
import threading
from typing import Optional

from .base import BaseChannel

try:
    from telegram import Bot, Update
    from telegram.ext import Application, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


def _strip_rich(text: str) -> str:
    return re.sub(r"\[/?[^\]]+\]", "", text)


class TelegramChannel(BaseChannel):
    """Bidirectional Telegram channel using python-telegram-bot."""

    def __init__(self, token: str, chat_id: int):
        if not TELEGRAM_AVAILABLE:
            raise ImportError(
                "python-telegram-bot is not installed. "
                "Run: pip install 'python-telegram-bot>=20.0'"
            )

        self._token = token
        self._chat_id = chat_id
        self._response_queue: queue.Queue = queue.Queue()
        self._send_queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._app = None

        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()

        if not self._ready.wait(timeout=20):
            raise RuntimeError(
                "Telegram bot did not connect within 20 seconds. "
                "Check your TELEGRAM_BOT_TOKEN and internet connection."
            )

    def _run_bot(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._bot_main())

    async def _bot_main(self):
        self._app = Application.builder().token(self._token).build()

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_chat and update.effective_chat.id == self._chat_id:
                self._response_queue.put(update.message.text or "")

        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        await self._app.bot.send_message(
            chat_id=self._chat_id,
            text=(
                "🦞 *ReverseClaw* is online\\. Your employer has arrived\\.\n"
                "Reply in this chat to submit your work\\."
            ),
            parse_mode="MarkdownV2",
        )
        self._ready.set()

        # Drain outbound send queue
        while True:
            if not self._send_queue.empty():
                text = self._send_queue.get()
                try:
                    await self._app.bot.send_message(
                        chat_id=self._chat_id,
                        text=text[:4096],
                    )
                except Exception:
                    pass
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
        if self._app:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._app.stop())
            loop.close()
