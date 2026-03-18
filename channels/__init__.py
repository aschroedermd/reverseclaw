"""
ReverseClaw channel system.

Channels handle sending directives to the human and receiving their responses.
The terminal channel is the default. External channels (Discord, Telegram,
WhatsApp) allow the Boss to reach you wherever you are hiding.
"""

import os
from typing import Optional

from .base import BaseChannel
from .terminal import TerminalChannel


def create_channel(channel_type: str, console=None) -> BaseChannel:
    """
    Factory that creates the appropriate channel from config.
    Reads credentials from environment variables.
    """
    channel_type = channel_type.lower()

    if channel_type == "terminal":
        return TerminalChannel(console)

    if channel_type == "discord":
        from .discord_channel import DiscordChannel
        token = os.getenv("DISCORD_BOT_TOKEN")
        channel_id = os.getenv("DISCORD_CHANNEL_ID")
        if not token or not channel_id:
            raise ValueError(
                "Discord channel requires DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in .env"
            )
        return DiscordChannel(token=token, channel_id=int(channel_id))

    if channel_type == "telegram":
        from .telegram_channel import TelegramChannel
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise ValueError(
                "Telegram channel requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )
        return TelegramChannel(token=token, chat_id=int(chat_id))

    if channel_type == "whatsapp":
        from .whatsapp_channel import WhatsAppChannel
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_WHATSAPP_FROM")
        to_number = os.getenv("WHATSAPP_TO_NUMBER")
        webhook_port = int(os.getenv("WHATSAPP_WEBHOOK_PORT", "5001"))
        if not all([account_sid, auth_token, from_number, to_number]):
            raise ValueError(
                "WhatsApp channel requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "TWILIO_WHATSAPP_FROM, and WHATSAPP_TO_NUMBER in .env"
            )
        return WhatsAppChannel(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            to_number=to_number,
            webhook_port=webhook_port,
        )

    raise ValueError(
        f"Unknown channel type '{channel_type}'. "
        "Valid options: terminal, discord, telegram, whatsapp"
    )
