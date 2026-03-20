"""
WhatsApp channel for ReverseClaw via Twilio.

The Boss sends tasks to your WhatsApp number.
You reply on WhatsApp to submit your work.

Setup:
  1. Create a Twilio account at https://www.twilio.com
  2. Enable the WhatsApp Sandbox (or a production WhatsApp number)
  3. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM,
     and WHATSAPP_TO_NUMBER in your .env
  4. For inbound messages, Twilio needs a public webhook URL.
     In development, use ngrok: ngrok http 5001
     Then set your Twilio sandbox webhook to: https://<ngrok-id>.ngrok.io/whatsapp

Outbound messages use the Twilio REST API directly.
Inbound messages arrive via a Flask webhook server on port 5001.
"""

import re
import threading
import queue
from typing import Optional

from .base import BaseChannel

try:
    from twilio.rest import Client as TwilioClient
    from twilio.request_validator import RequestValidator
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    RequestValidator = None

try:
    from flask import Flask, request, Response
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


def _strip_rich(text: str) -> str:
    return re.sub(r"\[/?[^\]]+\]", "", text)


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel via Twilio.
    Outbound: Twilio REST API.
    Inbound: Flask webhook server listening on WHATSAPP_WEBHOOK_PORT (default 5001).
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_number: str,
        webhook_port: int = 5001,
    ):
        if not TWILIO_AVAILABLE:
            raise ImportError(
                "twilio is not installed. Run: pip install twilio"
            )
        if not FLASK_AVAILABLE:
            raise ImportError(
                "flask is not installed. Run: pip install flask"
            )

        self._client = TwilioClient(account_sid, auth_token)
        self._validator = RequestValidator(auth_token)
        self._from = f"whatsapp:{from_number}"
        self._to = f"whatsapp:{to_number}"
        self._response_queue: queue.Queue = queue.Queue()
        self._webhook_port = webhook_port

        self._flask_thread = threading.Thread(
            target=self._run_webhook, daemon=True
        )
        self._flask_thread.start()

        # Announce startup
        self.send(
            "🦞 *ReverseClaw* is online. Your employer has arrived. "
            "Reply to this chat to submit your work."
        )

    def _run_webhook(self):
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)

        app = Flask(__name__)

        @app.route("/whatsapp", methods=["POST"])
        def whatsapp_webhook():
            body = request.form.get("Body", "")
            sender = request.form.get("From", "")
            signature = request.headers.get("X-Twilio-Signature", "")
            form_data = request.form.to_dict(flat=True)
            scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
            host = request.headers.get("X-Forwarded-Host", request.host)
            request_url = f"{scheme}://{host}{request.path}"
            if request.query_string:
                request_url = f"{request_url}?{request.query_string.decode('utf-8')}"
            if not signature or not self._validator.validate(request_url, form_data, signature):
                return Response(
                    '<?xml version="1.0"?><Response></Response>',
                    mimetype="text/xml",
                    status=403,
                )

            if sender == self._to:
                self._response_queue.put(body)
            return Response(
                '<?xml version="1.0"?><Response></Response>',
                mimetype="text/xml",
            )

        app.run(port=self._webhook_port, debug=False, use_reloader=False)

    def send(self, plain_text: str):
        text = _strip_rich(plain_text).strip()
        if not text:
            return
        try:
            self._client.messages.create(
                body=text[:1600],
                from_=self._from,
                to=self._to,
            )
        except Exception as e:
            print(f"[WhatsApp] Send error: {e}")

    def receive(self, timeout: Optional[int] = None) -> Optional[str]:
        try:
            return self._response_queue.get(timeout=timeout)
        except queue.Empty:
            return None
