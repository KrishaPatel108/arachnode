"""
mailer.py — Gmail SMTP sender for the Email Generator Service.

Sends plain-text emails via Gmail's SMTP_SSL endpoint.
Credentials come from environment variables only — never hardcoded.

Config required in environment:
  GMAIL_ADDRESS      your Gmail address (e.g. you@gmail.com)
  GMAIL_APP_PASSWORD 16-character App Password (not your login password)

Generate an App Password at:
  https://myaccount.google.com/apppasswords
  (requires 2-Step Verification to be enabled)
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465   # SMTP_SSL


def _send_sync(
    to_address: str,
    subject: str,
    body: str,
    from_address: str,
    app_password: str,
    your_name: str,
) -> None:
    """Blocking Gmail send — called via run_in_executor to stay async-safe."""
    msg = EmailMessage()
    msg["From"]    = f"{your_name} <{from_address}>"
    msg["To"]      = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT, context=ctx) as smtp:
        smtp.login(from_address, app_password)
        smtp.send_message(msg)

    logger.info("[Mailer] Email sent to %s — subject: %s", to_address, subject)


async def send_email(
    to_address: str,
    subject: str,
    body: str,
) -> None:
    """
    Async wrapper: reads credentials from environment, sends email via Gmail.

    Raises:
        RuntimeError if GMAIL_ADDRESS or GMAIL_APP_PASSWORD are not set.
        smtplib.SMTPAuthenticationError on bad credentials.
        smtplib.SMTPException on other sending failures.
    """
    from_address = os.environ.get("GMAIL_ADDRESS", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    your_name    = os.environ.get("YOUR_NAME", "Applicant").strip()

    if not from_address or not app_password:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set to send emails."
        )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        _send_sync,
        to_address,
        subject,
        body,
        from_address,
        app_password,
        your_name,
    )
