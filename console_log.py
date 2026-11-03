from __future__ import annotations

import json
import logging

from utils import normalize_tag_keys


logger = logging.getLogger(__name__)


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

    logger.info("\n%s:", title)
    logger.info(json.dumps(redact_secrets(value), ensure_ascii=False, indent=2, default=str))


def format_log_value(value) -> str:
    """Chuyen gia tri log ve chuoi ngan gon."""

    if value in (None, ""):
        return "-"

    return str(value)


def format_condition(sensor_config: dict) -> str:
    """Dinh dang condition trong InstanceConfigJsonSensor schema moi."""

    condition = sensor_config.get("condition") or {}
    if not isinstance(condition, dict):
        return "-"

    condition_type = format_log_value(condition.get("type"))
    operator = format_log_value(condition.get("operator"))
    params = condition.get("params") or {}
    return f"type={condition_type}, operator={operator}, params={format_log_value(params)}"


def get_sensor_tag_id_text(sensor_config: dict):
    """Lay tag id tu sensor config de hien thi trong log."""

    for key in ("tag_id", "tagId", "TagId", "tag_ids", "tagIds", "TagIds"):
        value = sensor_config.get(key)
        if isinstance(value, list):
            tag_ids = [str(item).strip() for item in value if str(item).strip()]
            if tag_ids:
                return ", ".join(tag_ids)
            continue

        if value not in (None, ""):
            return value

    return None


def print_parameter_log(config: dict, connection_profile: dict, threshold_checks: list[dict]) -> None:
    """In log tom tat de kiem tra cac thong so dang dung hay khong."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    profile_config = connection_profile.get("InstanceConfigJson") or {}
    checked_tags = [tag for tag in threshold_checks if tag["Threshold"] is not None]
    exceeded_tags = [tag for tag in threshold_checks if tag["Exceeded"]]

    logger.info("\n=== LOG KIEM TRA THONG SO ===")
    logger.info("ConfigId: %s", config["Id"])
    logger.info("ConfigName: %s", config["Name"])
    if sensor_config.get("condition") or sensor_config.get("alert_type") or get_sensor_tag_id_text(sensor_config):
        logger.info(
            "Sensor: "
            f"machine_id={format_log_value(config.get('MachineId'))}, "
            f"tag_id={format_log_value(get_sensor_tag_id_text(sensor_config))}, "
            f"alert_type={format_log_value(sensor_config.get('alert_type'))}, "
            f"condition=({format_condition(sensor_config)}), "
            f"incident={format_log_value(sensor_config.get('incident'))}, "
            f"solution={format_log_value(sensor_config.get('solution'))}"
        )
    else:
        logger.info(
            "Sensor: "
            f"ip_iolink={format_log_value(sensor_config.get('ip_iolink'))}, "
            f"port={format_log_value(sensor_config.get('port'))}, "
            f"time_threshold={format_log_value(sensor_config.get('time_threshold'))}, "
            f"tag_key={', '.join(normalize_tag_keys(sensor_config.get('tag_key', [])))}"
        )
    logger.info(
        "ConnectionProfile: "
        f"id={connection_profile['Id']}, "
        f"name={connection_profile.get('SourceName')}, "
        f"machine_id={format_log_value(connection_profile.get('MachineId'))}, "
        f"machine_ip={format_log_value(profile_config.get('machine_ip'))}, "
        f"iolink_ip={format_log_value(profile_config.get('iolink_ip'))}, "
        f"broker={format_log_value(profile_config.get('broker_host'))}:"
        f"{format_log_value(profile_config.get('broker_port'))}"
    )
    logger.info(
        "Tong ket: "
        f"tag_tim_duoc={len(threshold_checks)}, "
        f"tag_co_nguong={len(checked_tags)}, "
        f"tag_vuot_nguong={len(exceeded_tags)}"
    )

    logger.info("\nChi tiet tag:")
    for tag in threshold_checks:
        unit = tag.get("Unit") or ""
        current_unit = tag.get("CurrentUnit") or ""
        current_text = ""
        average_text = ""
        if tag.get("ConditionType") == "change" and (
            tag.get("TodayAverage") is not None or tag.get("YesterdayAverage") is not None
        ):
            average_text = (
                f" | AvgToday={format_log_value(tag.get('TodayAverage'))} {current_unit}"
                f" | AvgYesterday={format_log_value(tag.get('YesterdayAverage'))} {current_unit}"
                f" | Samples={format_log_value(tag.get('TodaySampleCount'))}/"
                f"{format_log_value(tag.get('YesterdaySampleCount'))}"
            )
        if tag.get("CurrentValue") != tag.get("Value") or current_unit != unit:
            current_text = (
                f" | Current={format_log_value(tag.get('CurrentValue'))} {current_unit}"
            )
        logger.info(
            "- "
            f"{tag['Status']} | "
            f"Condition={format_log_value(tag.get('ConditionType'))}/"
            f"{format_log_value(tag.get('Operator'))} | "
            f"TagKey={tag['TagKey']} | "
            f"TagId={tag['TagId']} | "
            f"Port={format_log_value(tag.get('Port'))} | "
            f"Value={format_log_value(tag.get('Value'))} {unit} | "
            f"Threshold={format_log_value(tag.get('Threshold'))} {unit} | "
            f"LastUpdated={format_log_value(tag.get('LastUpdated'))}"
            f"{current_text}"
            f"{average_text}"
        )


def print_cooldown_log(cooldown_tags: list[dict]) -> None:
    """In cac tag vuot nguong nhung dang trong cooldown."""

    if not cooldown_tags:
        return

    logger.info("\nTag vuot nguong nhung dang trong cooldown:")
    for tag in cooldown_tags:
        unit = tag.get("Unit") or ""
        logger.info(
            "- "
            f"TagKey={tag['TagKey']} | "
            f"Value={format_log_value(tag.get('Value'))} {unit} | "
            f"Threshold={format_log_value(tag.get('Threshold'))} {unit} | "
            f"con_lai={tag['CooldownRemainingSec']}s"
        )


def print_alerting_log(alerting_tags: list[dict]) -> None:
    """In cac tag dang o trang thai alerting nen khong gui lap lai."""

    if not alerting_tags:
        return

    logger.info("\nTag vuot nguong nhung da o trang thai alerting:")
    for tag in alerting_tags:
        unit = tag.get("Unit") or ""
        logger.info(
            "- "
            f"TagKey={tag['TagKey']} | "
            f"Value={format_log_value(tag.get('Value'))} {unit} | "
            f"Threshold={format_log_value(tag.get('Threshold'))} {unit}"
        )
