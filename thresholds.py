from __future__ import annotations

import json
from datetime import datetime


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


def get_alert_condition(tag_definition: dict) -> dict:
    """Lay dieu kien canh bao gan tu InstanceConfigJsonSensor neu co."""

    condition = tag_definition.get("AlertCondition") or {}
    return condition if isinstance(condition, dict) else {}


def get_condition_params(condition: dict) -> dict:
    """Lay params trong condition theo schema sensor moi."""

    params = condition.get("params") or {}
    return params if isinstance(params, dict) else {}


def get_condition_operator(condition: dict, default: str = "gt") -> str:
    """Lay operator va dua ve dang chu thuong."""

    return str(condition.get("operator") or default).strip().lower()


def get_legacy_metric_threshold(tag_definition: dict) -> float | None:
    """Lay nguong canh bao kieu cu trong AddressConfigJson cua tag."""

    address_config = tag_definition.get("AddressConfigJson") or {}
    for key in ("metric_threshold", "threshold"):
        threshold = parse_numeric_value(address_config.get(key))
        if threshold is not None:
            return threshold

    return None


def get_metric_threshold(tag_definition: dict) -> float | None:
    """Lay nguong don tri tu schema moi hoac schema cu."""

    condition = get_alert_condition(tag_definition)
    params = get_condition_params(condition)

    if str(condition.get("type") or "").strip().lower() == "threshold":
        return parse_numeric_value(params.get("value"))

    return get_legacy_metric_threshold(tag_definition)


def compare_threshold(value: float, threshold: float, operator: str) -> bool:
    """So sanh gia tri voi nguong theo operator trong config."""

    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    if operator == "eq":
        return value == threshold
    if operator in ("ne", "neq"):
        return value != threshold

    raise RuntimeError(f"operator threshold khong ho tro: {operator}")


def compare_range(value: float, min_value: float | None, max_value: float | None, operator: str) -> bool:
    """Kiem tra gia tri nam trong hoac ngoai khoang."""

    above_min = min_value is None or value >= min_value
    below_max = max_value is None or value <= max_value
    is_inside = above_min and below_max

    if operator == "inside":
        return is_inside
    if operator == "outside":
        below_min = min_value is not None and value < min_value
        above_max = max_value is not None and value > max_value
        return below_min or above_max
    if operator == "gt":
        threshold = max_value if max_value is not None else min_value
        if threshold is not None:
            return value > threshold
    if operator == "gte":
        threshold = max_value if max_value is not None else min_value
        if threshold is not None:
            return value >= threshold
    if operator == "lt":
        threshold = min_value if min_value is not None else max_value
        if threshold is not None:
            return value < threshold
    if operator == "lte":
        threshold = min_value if min_value is not None else max_value
        if threshold is not None:
            return value <= threshold

    raise RuntimeError(f"operator range khong ho tro: {operator}")


def format_range_threshold(min_value: float | None, max_value: float | None):
    """Tao chuoi nguong cho condition range."""

    if min_value is not None and max_value is not None:
        return f"{min_value:g} - {max_value:g}"
    if min_value is not None:
        return f">= {min_value:g}"
    if max_value is not None:
        return f"<= {max_value:g}"

    return None


def parse_sample_time(value):
    """Parse thoi gian metric/live de tinh rate/change neu can."""

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None


def get_numeric_samples(live_tag: dict | None) -> list[dict]:
    """Gom gia tri hien tai va metric history thanh danh sach mau so."""

    if not live_tag:
        return []

    samples = []

    def add_sample(value, logged_at, source: str) -> None:
        numeric_value = parse_numeric_value(value)
        if numeric_value is None:
            return

        samples.append(
            {
                "Value": numeric_value,
                "LoggedAt": logged_at,
                "ParsedTime": parse_sample_time(logged_at),
                "Source": source,
            }
        )

    add_sample(
        live_tag.get("NumericValue", live_tag.get("Value")),
        live_tag.get("LastUpdated"),
        live_tag.get("Source") or "livetags",
    )

    for metric_value in live_tag.get("MetricValues") or []:
        add_sample(
            metric_value.get("NumericValue", metric_value.get("Value")),
            metric_value.get("LogTime") or metric_value.get("LastUpdated"),
            "metricvalues",
        )

    samples.sort(key=lambda sample: sample["ParsedTime"] or datetime.min, reverse=True)
    deduped_samples = []
    seen = set()
    for sample in samples:
        key = (sample["Value"], sample["LoggedAt"])
        if key in seen:
            continue

        seen.add(key)
        deduped_samples.append(sample)

    return deduped_samples


def get_time_unit_seconds(unit) -> float:
    """Doi don vi thoi gian trong condition ve giay."""

    normalized_unit = str(unit or "second").strip().lower()
    if normalized_unit in ("second", "seconds", "sec", "s"):
        return 1
    if normalized_unit in ("minute", "minutes", "min", "m"):
        return 60
    if normalized_unit in ("hour", "hours", "h"):
        return 3600

    return 1


def get_window_seconds(params: dict) -> float | None:
    """Lay khoang thoi gian phan tich tu params neu co."""

    window = parse_numeric_value(params.get("window"))
    if window is None or window <= 0:
        return None

    return window * get_time_unit_seconds(params.get("unit"))


def choose_baseline_sample(samples: list[dict], window_seconds: float | None = None) -> dict | None:
    """Chon mau so sanh voi mau moi nhat."""

    if len(samples) < 2:
        return None

    latest_sample = samples[0]
    latest_time = latest_sample["ParsedTime"]

    if window_seconds is not None and latest_time is not None:
        candidates = []
        for sample in samples[1:]:
            sample_time = sample["ParsedTime"]
            if sample_time is None:
                continue

            elapsed_seconds = (latest_time - sample_time).total_seconds()
            if 0 < elapsed_seconds <= window_seconds:
                candidates.append(sample)

        return candidates[-1] if candidates else None

    return samples[1]


def get_daily_average_change(live_tag: dict | None) -> dict | None:
    """Lay do bien thien giua trung binh hom nay va hom truoc."""

    if not live_tag:
        return None

    daily_averages = live_tag.get("MetricDailyAverages") or {}
    today_average = parse_numeric_value(daily_averages.get("TodayAverage"))
    yesterday_average = parse_numeric_value(daily_averages.get("YesterdayAverage"))
    daily_change = {
        "TodayAverage": today_average,
        "YesterdayAverage": yesterday_average,
        "PercentChange": None,
        "TodayDate": daily_averages.get("TodayDate"),
        "YesterdayDate": daily_averages.get("YesterdayDate"),
        "TodaySampleCount": daily_averages.get("TodaySampleCount"),
        "YesterdaySampleCount": daily_averages.get("YesterdaySampleCount"),
        "LastUpdated": daily_averages.get("LastTodayLogTime") or daily_averages.get("TodayDate"),
    }
    if today_average is None or yesterday_average is None or yesterday_average == 0:
        return daily_change

    daily_change["PercentChange"] = (today_average - yesterday_average) / abs(yesterday_average) * 100
    return daily_change


def evaluate_threshold_condition(value: float | None, condition: dict, tag_unit) -> dict:
    """Danh gia condition type=threshold."""

    params = get_condition_params(condition)
    threshold = parse_numeric_value(params.get("value"))
    operator = get_condition_operator(condition)

    if threshold is None:
        return {"Status": "CHUA_CO_NGUONG", "Threshold": None}
    if value is None:
        return {
            "Status": "CHUA_CO_GIA_TRI_LIVE",
            "Threshold": threshold,
            "ThresholdValue": threshold,
        }

    return {
        "Value": value,
        "Unit": tag_unit,
        "Threshold": threshold,
        "ThresholdValue": threshold,
        "Exceeded": compare_threshold(value, threshold, operator),
    }


def evaluate_range_condition(value: float | None, condition: dict, tag_unit) -> dict:
    """Danh gia condition type=range."""

    params = get_condition_params(condition)
    min_value = parse_numeric_value(params.get("min"))
    max_value = parse_numeric_value(params.get("max"))
    threshold = format_range_threshold(min_value, max_value)
    operator = get_condition_operator(condition, "outside")

    if threshold is None:
        return {"Status": "CHUA_CO_NGUONG", "Threshold": None}
    if value is None:
        return {
            "Status": "CHUA_CO_GIA_TRI_LIVE",
            "Threshold": threshold,
        }

    return {
        "Value": value,
        "Unit": tag_unit,
        "Threshold": threshold,
        "Exceeded": compare_range(value, min_value, max_value, operator),
    }


def evaluate_rate_condition(live_tag: dict | None, condition: dict, tag_unit) -> dict:
    """Danh gia condition type=rate bang metric history gan nhat."""

    params = get_condition_params(condition)
    threshold = parse_numeric_value(params.get("value"))
    operator = get_condition_operator(condition)
    time_unit = str(params.get("unit") or "second").strip().lower()
    samples = get_numeric_samples(live_tag)
    baseline_sample = choose_baseline_sample(samples, get_window_seconds(params))

    if threshold is None:
        return {"Status": "CHUA_CO_NGUONG", "Threshold": None}
    if not samples or baseline_sample is None:
        return {
            "Status": "CHUA_DU_LIEU_PHAN_TICH",
            "Threshold": threshold,
            "ThresholdValue": threshold,
        }

    latest_sample = samples[0]
    latest_time = latest_sample["ParsedTime"]
    baseline_time = baseline_sample["ParsedTime"]
    if latest_time is None or baseline_time is None:
        return {
            "Status": "CHUA_DU_LIEU_PHAN_TICH",
            "Threshold": threshold,
            "ThresholdValue": threshold,
        }

    elapsed_seconds = (latest_time - baseline_time).total_seconds()
    if elapsed_seconds <= 0:
        return {
            "Status": "CHUA_DU_LIEU_PHAN_TICH",
            "Threshold": threshold,
            "ThresholdValue": threshold,
        }

    rate = (latest_sample["Value"] - baseline_sample["Value"]) / elapsed_seconds * get_time_unit_seconds(time_unit)
    compare_value = rate if operator == "increase" else -rate
    if operator not in ("increase", "decrease"):
        raise RuntimeError(f"operator rate khong ho tro: {operator}")

    return {
        "Value": compare_value,
        "CurrentValue": latest_sample["Value"],
        "Unit": f"{str(tag_unit or '').strip()}/{time_unit}".strip("/"),
        "CurrentUnit": tag_unit,
        "Threshold": threshold,
        "ThresholdValue": threshold,
        "Exceeded": compare_value >= threshold,
        "LastUpdated": latest_sample["LoggedAt"],
    }


def evaluate_change_condition(live_tag: dict | None, condition: dict, tag_unit) -> dict:
    """Danh gia condition type=change bang % giua TB hom nay va TB hom truoc."""

    params = get_condition_params(condition)
    threshold = parse_numeric_value(params.get("percent"))
    operator = get_condition_operator(condition)
    daily_change = get_daily_average_change(live_tag)

    if threshold is None:
        return {"Status": "CHUA_CO_NGUONG", "Threshold": None}
    if daily_change is None or daily_change["PercentChange"] is None:
        fallback_evaluation = {
            "Status": "CHUA_DU_LIEU_TRUNG_BINH_NGAY",
            "Value": None,
            "Unit": "%",
            "Threshold": threshold,
            "ThresholdValue": threshold,
        }
        if daily_change is None:
            return fallback_evaluation

        fallback_evaluation.update(
            {
                "CurrentValue": daily_change["TodayAverage"],
                "CurrentUnit": tag_unit,
                "BaselineValue": daily_change["YesterdayAverage"],
                "BaselineUnit": tag_unit,
                "TodayAverage": daily_change["TodayAverage"],
                "YesterdayAverage": daily_change["YesterdayAverage"],
                "TodayDate": daily_change["TodayDate"],
                "YesterdayDate": daily_change["YesterdayDate"],
                "TodaySampleCount": daily_change["TodaySampleCount"],
                "YesterdaySampleCount": daily_change["YesterdaySampleCount"],
                "LastUpdated": daily_change["LastUpdated"],
            }
        )
        return fallback_evaluation

    percent_change = daily_change["PercentChange"]

    if operator == "increase_pct":
        compare_value = percent_change
    elif operator == "decrease_pct":
        compare_value = -percent_change
    elif operator == "change_pct":
        compare_value = abs(percent_change)
    else:
        raise RuntimeError(f"operator change khong ho tro: {operator}")

    return {
        "Value": compare_value,
        "CurrentValue": daily_change["TodayAverage"],
        "CurrentUnit": tag_unit,
        "BaselineValue": daily_change["YesterdayAverage"],
        "BaselineUnit": tag_unit,
        "TodayAverage": daily_change["TodayAverage"],
        "YesterdayAverage": daily_change["YesterdayAverage"],
        "TodayDate": daily_change["TodayDate"],
        "YesterdayDate": daily_change["YesterdayDate"],
        "TodaySampleCount": daily_change["TodaySampleCount"],
        "YesterdaySampleCount": daily_change["YesterdaySampleCount"],
        "Unit": "%",
        "Threshold": threshold,
        "ThresholdValue": threshold,
        "Exceeded": compare_value >= threshold,
        "LastUpdated": daily_change["LastUpdated"],
    }


def evaluate_legacy_condition(value: float | None, tag_definition: dict, tag_unit) -> dict:
    """Danh gia nguong kieu cu bang metric_threshold trong AddressConfigJson."""

    threshold = get_legacy_metric_threshold(tag_definition)
    if threshold is None:
        return {"Status": "CHUA_CO_NGUONG", "Threshold": None}
    if value is None:
        return {
            "Status": "CHUA_CO_GIA_TRI_LIVE",
            "Threshold": threshold,
            "ThresholdValue": threshold,
        }

    return {
        "Value": value,
        "Unit": tag_unit,
        "Threshold": threshold,
        "ThresholdValue": threshold,
        "Exceeded": value > threshold,
    }


def evaluate_tag_condition(tag_definition: dict, live_tag: dict | None) -> dict:
    """Danh gia dieu kien canh bao cho mot tag."""

    tag_unit = tag_definition.get("Unit")
    current_value = live_tag.get("NumericValue") if live_tag else None
    condition = get_alert_condition(tag_definition)
    condition_type = str(condition.get("type") or "").strip().lower()
    operator = get_condition_operator(condition) if condition else "gt"

    if condition_type == "threshold":
        evaluation = evaluate_threshold_condition(current_value, condition, tag_unit)
    elif condition_type == "range":
        evaluation = evaluate_range_condition(current_value, condition, tag_unit)
    elif condition_type == "rate":
        evaluation = evaluate_rate_condition(live_tag, condition, tag_unit)
    elif condition_type == "change":
        evaluation = evaluate_change_condition(live_tag, condition, tag_unit)
    elif condition:
        evaluation = {
            "Status": "CHUA_HO_TRO_DIEU_KIEN",
            "Threshold": None,
            "Exceeded": False,
        }
    else:
        condition_type = "threshold"
        evaluation = evaluate_legacy_condition(current_value, tag_definition, tag_unit)

    is_exceeded = bool(evaluation.get("Exceeded", False))
    status = evaluation.get("Status")
    if not status:
        status = "VUOT_NGUONG" if is_exceeded else "OK"

    return {
        "ConditionType": condition_type or "-",
        "Operator": operator,
        "CurrentValue": evaluation.get("CurrentValue", current_value),
        "CurrentUnit": evaluation.get("CurrentUnit", tag_unit),
        "BaselineValue": evaluation.get("BaselineValue"),
        "BaselineUnit": evaluation.get("BaselineUnit"),
        "TodayAverage": evaluation.get("TodayAverage"),
        "YesterdayAverage": evaluation.get("YesterdayAverage"),
        "TodayDate": evaluation.get("TodayDate"),
        "YesterdayDate": evaluation.get("YesterdayDate"),
        "TodaySampleCount": evaluation.get("TodaySampleCount"),
        "YesterdaySampleCount": evaluation.get("YesterdaySampleCount"),
        "Value": evaluation.get("Value", current_value),
        "Unit": evaluation.get("Unit", tag_unit),
        "Threshold": evaluation.get("Threshold"),
        "ThresholdValue": evaluation.get("ThresholdValue"),
        "Exceeded": is_exceeded,
        "Status": status,
        "LastUpdated": evaluation.get("LastUpdated") or (live_tag.get("LastUpdated") if live_tag else None),
    }


def check_thresholds(tag_definitions: list[dict], live_tags_by_id: dict[str, dict]) -> list[dict]:
    """So sanh gia tri hien tai voi dieu kien canh bao cua tung tag."""

    results = []
    for tag_definition in tag_definitions:
        live_tag = live_tags_by_id.get(tag_definition["Id"])
        address_config = tag_definition.get("AddressConfigJson") or {}
        evaluation = evaluate_tag_condition(tag_definition, live_tag)

        results.append(
            {
                "TagId": tag_definition["Id"],
                "TagKey": tag_definition["TagKey"],
                "TagName": tag_definition["TagName"],
                "Port": address_config.get("port"),
                "Unit": evaluation["Unit"],
                "CurrentValue": evaluation["CurrentValue"],
                "CurrentUnit": evaluation["CurrentUnit"],
                "BaselineValue": evaluation["BaselineValue"],
                "BaselineUnit": evaluation["BaselineUnit"],
                "TodayAverage": evaluation["TodayAverage"],
                "YesterdayAverage": evaluation["YesterdayAverage"],
                "TodayDate": evaluation["TodayDate"],
                "YesterdayDate": evaluation["YesterdayDate"],
                "TodaySampleCount": evaluation["TodaySampleCount"],
                "YesterdaySampleCount": evaluation["YesterdaySampleCount"],
                "LiveTagId": live_tag.get("Id") if live_tag else None,
                "Value": evaluation["Value"],
                "Threshold": evaluation["Threshold"],
                "ThresholdValue": evaluation["ThresholdValue"],
                "ConditionType": evaluation["ConditionType"],
                "Operator": evaluation["Operator"],
                "Incident": tag_definition.get("AlertIncident"),
                "Solution": tag_definition.get("AlertSolution"),
                "AlertType": tag_definition.get("AlertType"),
                "Exceeded": evaluation["Exceeded"],
                "Status": evaluation["Status"],
                "LastUpdated": evaluation["LastUpdated"],
            }
        )

    return results
