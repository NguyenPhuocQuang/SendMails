from __future__ import annotations

import json

from utils import normalize_tag_keys


def redact_secrets(value):
    """Che cac thong tin nhay cam truoc khi in ra console."""

    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered_key = key.lower()

            if any(secret_key in lowered_key for secret_key in ("password", "secret", "token")):
                redacted[key] = "***"
            else:
                redacted[key] = redact_secrets(item)

        return redacted

    if isinstance(value, list):
        return [redact_secrets(item) for item in value]

    return value


def print_json(title: str, value) -> None:
    """In JSON ra console dep hon va co che thong tin nhay cam."""

    print(f"\n{title}:")
    print(json.dumps(redact_secrets(value), ensure_ascii=False, indent=2, default=str))


def format_log_value(value) -> str:
    """Chuyen gia tri log ve chuoi ngan gon."""

    if value in (None, ""):
        return "-"

    return str(value)


def print_parameter_log(config: dict, connection_profile: dict, threshold_checks: list[dict]) -> None:
    """In log tom tat de kiem tra cac thong so dang dung hay khong."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    profile_config = connection_profile.get("InstanceConfigJson") or {}
    checked_tags = [tag for tag in threshold_checks if tag["Threshold"] is not None]
    exceeded_tags = [tag for tag in threshold_checks if tag["Exceeded"]]

    print("\n=== LOG KIEM TRA THONG SO ===")
    print(f"ConfigId: {config['Id']}")
    print(f"ConfigName: {config['Name']}")
    print(
        "Sensor: "
        f"ip_iolink={format_log_value(sensor_config.get('ip_iolink'))}, "
        f"port={format_log_value(sensor_config.get('port'))}, "
        f"time_threshold={format_log_value(sensor_config.get('time_threshold'))}, "
        f"tag_key={', '.join(normalize_tag_keys(sensor_config.get('tag_key', [])))}"
    )
    print(
        "ConnectionProfile: "
        f"id={connection_profile['Id']}, "
        f"name={connection_profile.get('SourceName')}, "
        f"machine_ip={format_log_value(profile_config.get('machine_ip'))}, "
        f"iolink_port={format_log_value(profile_config.get('iolink_port'))}"
    )
    print(
        "Tong ket: "
        f"tag_tim_duoc={len(threshold_checks)}, "
        f"tag_co_nguong={len(checked_tags)}, "
        f"tag_vuot_nguong={len(exceeded_tags)}"
    )

    print("\nChi tiet tag:")
    for tag in threshold_checks:
        unit = tag.get("Unit") or ""
        print(
            "- "
            f"{tag['Status']} | "
            f"TagKey={tag['TagKey']} | "
            f"TagId={tag['TagId']} | "
            f"Port={format_log_value(tag.get('Port'))} | "
            f"Value={format_log_value(tag.get('Value'))} {unit} | "
            f"Threshold={format_log_value(tag.get('Threshold'))} {unit} | "
            f"LastUpdated={format_log_value(tag.get('LastUpdated'))}"
        )


def print_cooldown_log(cooldown_tags: list[dict]) -> None:
    """In cac tag vuot nguong nhung dang trong cooldown."""

    if not cooldown_tags:
        return

    print("\nTag vuot nguong nhung dang trong cooldown:")
    for tag in cooldown_tags:
        unit = tag.get("Unit") or ""
        print(
            "- "
            f"TagKey={tag['TagKey']} | "
            f"Value={format_log_value(tag.get('Value'))} {unit} | "
            f"Threshold={format_log_value(tag.get('Threshold'))} {unit} | "
            f"con_lai={tag['CooldownRemainingSec']}s"
        )
