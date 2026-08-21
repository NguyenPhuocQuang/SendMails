from __future__ import annotations

import json


def parse_numeric_value(value) -> float | None:
    """Chuyen gia tri live/threshold ve so de so sanh."""

    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")

    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return None

        try:
            return float(stripped_value)
        except ValueError:
            pass

        try:
            parsed_value = json.loads(stripped_value)
        except json.JSONDecodeError:
            return None

        return parse_numeric_value(parsed_value)

    if isinstance(value, dict):
        for key in ("value", "Value", "current_value", "CurrentValue", "data"):
            if key in value:
                return parse_numeric_value(value[key])

    return None


def get_metric_threshold(tag_definition: dict) -> float | None:
    """Lay nguong canh bao trong AddressConfigJson cua tag."""

    address_config = tag_definition.get("AddressConfigJson") or {}
    for key in ("metric_threshold", "threshold"):
        threshold = parse_numeric_value(address_config.get(key))
        if threshold is not None:
            return threshold

    return None


def check_thresholds(tag_definitions: list[dict], live_tags_by_id: dict[str, dict]) -> list[dict]:
    """So sanh gia tri livetags voi metric_threshold cua tung tag."""

    results = []
    for tag_definition in tag_definitions:
        live_tag = live_tags_by_id.get(tag_definition["Id"])
        address_config = tag_definition.get("AddressConfigJson") or {}
        value = live_tag.get("NumericValue") if live_tag else None
        threshold = get_metric_threshold(tag_definition)
        is_exceeded = value is not None and threshold is not None and value > threshold

        if threshold is None:
            status = "CHUA_CO_NGUONG"
        elif value is None:
            status = "CHUA_CO_GIA_TRI_LIVE"
        elif is_exceeded:
            status = "VUOT_NGUONG"
        else:
            status = "OK"

        results.append(
            {
                "TagId": tag_definition["Id"],
                "TagKey": tag_definition["TagKey"],
                "TagName": tag_definition["TagName"],
                "Port": address_config.get("port"),
                "Unit": tag_definition["Unit"],
                "LiveTagId": live_tag.get("Id") if live_tag else None,
                "Value": value,
                "Threshold": threshold,
                "Exceeded": is_exceeded,
                "Status": status,
                "LastUpdated": live_tag.get("LastUpdated") if live_tag else None,
            }
        )

    return results
