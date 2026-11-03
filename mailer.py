from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from utils import normalize_receiver_emails


DEFAULT_SUBJECT = "[CANH BAO] Thiet bi vuot nguong"
SMTP_TIMEOUT_SECONDS = 30
SUPPORTED_SMTP_SECURITY = {"ssl", "starttls", "none"}


def get_config_value(config: dict, *keys, default=None):
    """Lay gia tri config theo nhieu ten field khac nhau."""

    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return value

    return default


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

    if bool(mail_config.get("use_ssl")):
        return "ssl"
    if bool(mail_config.get("use_tls") or mail_config.get("use_starttls")):
        return "starttls"

    if smtp_port == 465:
        return "ssl"

    return "starttls"


def get_sender_email(mail_config: dict) -> str:
    """Lay email nguoi gui theo schema cu hoac moi."""

    return get_config_value(mail_config, "sender_email", "from", "from_email", default="")


def get_sender_password(mail_config: dict) -> str:
    """Lay password SMTP neu config co khai bao."""

    return get_config_value(mail_config, "sender_password", "password", "smtp_password", default="")


def get_smtp_username(mail_config: dict, sender_email: str) -> str:
    """Lay username SMTP neu khac sender_email."""

    return get_config_value(mail_config, "smtp_user", "smtp_username", "username", default=sender_email)


def get_receiver_emails(mail_config: dict) -> list[str]:
    """Lay danh sach nguoi nhan theo schema cu hoac moi."""

    return normalize_receiver_emails(
        get_config_value(mail_config, "receiver_emails", "to", "recipients", default=[])
    )


def get_cc_emails(mail_config: dict) -> list[str]:
    """Lay danh sach CC neu co."""

    return normalize_receiver_emails(get_config_value(mail_config, "cc", "cc_emails", default=[]))


def validate_mail_config(mail_config: dict) -> None:
    """Kiem tra cac field bat buoc truoc khi gui mail."""

    if not isinstance(mail_config, dict):
        raise RuntimeError("InstanceConfigJsonMail phai la JSON object hop le.")

    required_values = {
        "smtp_host": mail_config.get("smtp_host"),
        "smtp_port": mail_config.get("smtp_port"),
        "sender_email/from": get_sender_email(mail_config),
        "receiver_emails/to": get_receiver_emails(mail_config),
    }

    missing_keys = [key for key, value in required_values.items() if not value]
    if missing_keys:
        raise RuntimeError(f"Thieu cau hinh mail: {', '.join(missing_keys)}")

    smtp_port = get_smtp_port(mail_config)
    smtp_security = get_smtp_security(mail_config, smtp_port)
    if smtp_security not in SUPPORTED_SMTP_SECURITY:
        raise RuntimeError(
            "smtp_security khong hop le. Gia tri hop le: ssl, starttls, none."
        )

    if not get_receiver_emails(mail_config):
        raise RuntimeError("Danh sach receiver_emails dang rong.")


def build_email_message(
    sender_email: str,
    receiver_emails: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    cc_emails: list[str] | None = None,
) -> EmailMessage:
    """Tao EmailMessage gom text fallback va HTML neu co."""

    cc_emails = cc_emails or []
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_emails)
    if cc_emails:
        message["Cc"] = ", ".join(cc_emails)
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
    sender_email = get_sender_email(mail_config)
    sender_password = get_sender_password(mail_config)
    smtp_username = get_smtp_username(mail_config, sender_email)
    receiver_emails = get_receiver_emails(mail_config)
    cc_emails = get_cc_emails(mail_config)
    subject = subject or mail_config.get("subject") or mail_config.get("subject_template") or DEFAULT_SUBJECT
    message = build_email_message(sender_email, receiver_emails, subject, body, html_body, cc_emails)

    context = ssl.create_default_context()
    if smtp_security == "ssl":
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if sender_password:
                smtp.login(smtp_username, sender_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            if smtp_security == "starttls":
                smtp.starttls(context=context)
                smtp.ehlo()
            if sender_password:
                smtp.login(smtp_username, sender_password)
            smtp.send_message(message)

    return receiver_emails + cc_emails
