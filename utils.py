from __future__ import annotations


def normalize_id(value) -> str:
    """Chuan hoa UUID/id ve dang char(32) trong database."""

    if value in (None, ""):
        return ""

    return str(value).strip().replace("-", "").lower()


def normalize_ids(values) -> list[str]:
    """Chuan hoa mot id hoac danh sach id ve list char(32)."""

    if isinstance(values, list):
        normalized_ids = []
        for value in values:
            normalized_id = normalize_id(value)
            if normalized_id:
                normalized_ids.append(normalized_id)

        return normalized_ids

    if isinstance(values, str):
        return [normalize_id(value) for value in values.split(",") if normalize_id(value)]

    normalized_id = normalize_id(values)
    return [normalized_id] if normalized_id else []


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
