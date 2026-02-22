from __future__ import annotations

import asyncio
import json
import smtplib
from email.message import EmailMessage
from typing import Any

from .config import Settings


async def send_exception_report(settings: Settings, report: dict[str, Any]) -> None:
    payload = json.dumps(report, indent=2, ensure_ascii=True)
    subject = f"[Ghost] Unhandled exception on {report.get('endpoint', 'unknown')}"

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = "danggiaminhmicrosoft@gmail.com"
    message["Subject"] = subject
    message.set_content(payload)

    await asyncio.to_thread(_send_mail_sync, settings, message)


def _send_mail_sync(settings: Settings, message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_use_tls:
            server.starttls()
        server.login(settings.smtp_user, settings.smtp_pass)
        server.send_message(message)
