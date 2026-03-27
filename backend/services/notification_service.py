import smtplib
from email.mime.text import MIMEText
import httpx
from core.config import settings


async def send_slack(message: str):
    if not settings.slack_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.slack_webhook_url, json={"text": message})
    except Exception:
        pass  # Notifications are best-effort — never let them break document processing


def send_email(subject: str, body: str):
    if not settings.smtp_host or not settings.notification_email_to:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.notification_email_to
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(
                settings.smtp_user, [settings.notification_email_to], msg.as_string()
            )
    except Exception:
        pass
