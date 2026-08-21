from __future__ import annotations


def normalize_receiver_emails(receiver_emails) -> list[str]:
    """Chuan hoa danh sach email nhan thanh list[str]."""

    if isinstance(receiver_emails, list):
        emails = []
        for email in receiver_emails:
            if email is None:
                continue

            normalized_email = str(email).strip()
            if normalized_email:
                emails.append(normalized_email)

        return emails

    if isinstance(receiver_emails, str):
        return [email.strip() for email in receiver_emails.split(",") if email.strip()]

    return []


def normalize_tag_keys(tag_keys) -> list[str]:
    """Chuan hoa danh sach tag_key trong sensor config thanh list[str]."""

    if isinstance(tag_keys, list):
        return [str(tag_key).strip() for tag_key in tag_keys if str(tag_key).strip()]

    if isinstance(tag_keys, str):
        return [tag_key.strip() for tag_key in tag_keys.split(",") if tag_key.strip()]

    return []
