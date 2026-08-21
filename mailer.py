from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from utils import normalize_receiver_emails


DEFAULT_SUBJECT = "[CANH BAO] Thiet bi vuot nguong"
SMTP_TIMEOUT_SECONDS = 30
SUPPORTED_SMTP_SECURITY = {"ssl", "starttls", "none"}


def get_smtp_port(mail_config: dict) -> int:
    """Lay va validate port SMTP."""

    try:
        return int(mail_config["smtp_port"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("smtp_port phai la so hop le.") from exc


def get_smtp_security(mail_config: dict, smtp_port: int) -> str:
    """Lay che do bao mat SMTP, tu config hoac suy luan theo port."""

    configured_security = str(
        mail_config.get("smtp_security") or mail_config.get("security") or ""
    ).strip().lower()

    if configured_security:
        return configured_security

    if smtp_port == 465:
        return "ssl"

    return "starttls"


def validate_mail_config(mail_config: dict) -> None:
    """Kiem tra cac field bat buoc truoc khi gui mail."""

    required_keys = [
        "smtp_host",
        "smtp_port",
        "sender_email",
        "sender_password",
        "receiver_emails",
    ]

    missing_keys = [key for key in required_keys if not mail_config.get(key)]
    if missing_keys:
        raise RuntimeError(f"Thieu cau hinh mail: {', '.join(missing_keys)}")

    smtp_port = get_smtp_port(mail_config)
    smtp_security = get_smtp_security(mail_config, smtp_port)
    if smtp_security not in SUPPORTED_SMTP_SECURITY:
        raise RuntimeError(
            "smtp_security khong hop le. Gia tri hop le: ssl, starttls, none."
        )

    if not normalize_receiver_emails(mail_config["receiver_emails"]):
        raise RuntimeError("Danh sach receiver_emails dang rong.")


def build_email_message(
    sender_email: str,
    receiver_emails: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
) -> EmailMessage:
    """Tao EmailMessage gom text fallback va HTML neu co."""

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_emails)
    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    return message


def send_mail(mail_config: dict, body: str, subject: str | None = None, html_body: str | None = None) -> list[str]:
    """Gui email bang SMTP dua tren InstanceConfigJsonMail."""

    validate_mail_config(mail_config)

    smtp_host = mail_config["smtp_host"]
    smtp_port = get_smtp_port(mail_config)
    smtp_security = get_smtp_security(mail_config, smtp_port)
    sender_email = mail_config["sender_email"]
    sender_password = mail_config["sender_password"]
    receiver_emails = normalize_receiver_emails(mail_config["receiver_emails"])
    subject = subject or mail_config.get("subject") or DEFAULT_SUBJECT
    message = build_email_message(sender_email, receiver_emails, subject, body, html_body)

    context = ssl.create_default_context()
    if smtp_security == "ssl":
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            if smtp_security == "starttls":
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(sender_email, sender_password)
            smtp.send_message(message)

    return receiver_emails
