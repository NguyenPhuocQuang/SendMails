from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from settings import get_db_config
from thresholds import check_thresholds, parse_numeric_value
from utils import normalize_id, normalize_ids


def connect_database():
    """Tao ket noi toi MySQL bang pymysql hoac mysql-connector-python."""

    config = get_db_config()

    try:
        import pymysql

        return pymysql.connect(
            **config,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    except ModuleNotFoundError:
        pass

    try:
        import mysql.connector

        return mysql.connector.connect(**config)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Chua cai thu vien MySQL. Hay cai mot trong hai lenh:\n"
            "  pip install pymysql\n"
            "  pip install mysql-connector-python"
        ) from exc


@contextmanager
def open_database():
    """Mo ket noi database va dam bao dong ket noi sau khi dung."""

    connection = connect_database()
    try:
        yield connection
    finally:
        connection.close()


def fetch_all(connection, sql: str, params=None) -> list[dict]:
    """Chay query va tra ket qua ve list[dict] cho ca pymysql va mysql.connector."""

    cursor = connection.cursor()
    try:
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description or []]
    finally:
        cursor.close()

    if not rows:
        return []

    if isinstance(rows[0], dict):
        return rows

    return [dict(zip(columns, row)) for row in rows]


def parse_json_value(value):
    """Chuyen du lieu JSON trong database thanh dict/list Python."""

    if isinstance(value, (dict, list)):
        return value

    if value in (None, ""):
        return None

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")

    return json.loads(value)


def parse_json_column(row: dict, column_name: str, table_name: str):
    """Parse JSON trong mot cot DB va bao loi kem ngu canh."""

    try:
        return parse_json_value(row.get(column_name))
    except (json.JSONDecodeError, TypeError) as exc:
        row_id = row.get("Id", "-")
        raise RuntimeError(
            f"JSON khong hop le trong {table_name}.{column_name}, Id={row_id}."
        ) from exc


def parse_mail_sensor_config_row(row: dict) -> dict:
    """Parse JSON cua mot cau hinh mail/sensor active."""

    parsed_row = dict(row)
    parsed_row["InstanceConfigJsonMail"] = parse_json_column(
        parsed_row,
        "InstanceConfigJsonMail",
        "mailsensorconfigs",
    )
    parsed_row["InstanceConfigJsonSensor"] = parse_json_column(
        parsed_row,
        "InstanceConfigJsonSensor",
        "mailsensorconfigs",
    )
    return parsed_row


def get_active_mail_sensor_configs(connection) -> list[dict]:
    """Lay tat ca cau hinh active trong bang mailsensorconfigs."""

    sql = """
        SELECT
            `Id`,
            `Name`,
            `MachineId`,
            `InstanceConfigJsonMail`,
            `InstanceConfigJsonSensor`,
            `IsDeleted`
        FROM `mailsensorconfigs`
        WHERE `IsDeleted` = 0
        ORDER BY `CreatedDate` DESC
    """

    rows = fetch_all(connection, sql)
    if not rows:
        raise RuntimeError("Khong tim thay cau hinh active trong bang mailsensorconfigs.")

    return [parse_mail_sensor_config_row(row) for row in rows]


def get_active_mail_sensor_config(connection):
    """Lay cau hinh active moi nhat de giu tuong thich code cu."""

    return get_active_mail_sensor_configs(connection)[0]


def load_active_mail_sensor_configs() -> list[dict]:
    """Mo DB va doc tat ca cau hinh active."""

    with open_database() as connection:
        return get_active_mail_sensor_configs(connection)


def build_fallback_connection_profile(config: dict, sensor_config: dict) -> dict:
    """Tao profile rong khi schema moi chi can lay value theo tag_id."""

    return {
        "Id": "-",
        "SourceName": "Khong dung connectionprofile",
        "PollingIntervalMs": None,
        "InstanceConfigJson": {},
        "MachineId": normalize_id(
            config.get("MachineId")
            or sensor_config.get("machine_id")
            or sensor_config.get("machineId")
            or sensor_config.get("tag_id")
            or sensor_config.get("tagId")
            or sensor_config.get("TagId")
        ),
        "IsDeleted": 0,
    }


def get_direct_sensor_tag_ids(sensor_config: dict) -> list[str]:
    """Lay TagId truc tiep tu InstanceConfigJsonSensor neu config da khai bao."""

    tag_ids = []
    for key in ("tag_id", "tagId", "TagId", "tag_ids", "tagIds", "TagIds"):
        tag_ids.extend(normalize_ids(sensor_config.get(key)))

    deduped_tag_ids = []
    seen = set()
    for tag_id in tag_ids:
        if tag_id in seen:
            continue

        seen.add(tag_id)
        deduped_tag_ids.append(tag_id)

    return deduped_tag_ids


def attach_sensor_config_to_tag_definitions(tag_definitions: list[dict], sensor_config: dict) -> list[dict]:
    """Gan condition/incident/solution cua schema moi vao tagdefinition de evaluator dung."""

    condition = sensor_config.get("condition")
    if not isinstance(condition, dict):
        return tag_definitions

    enriched_tag_definitions = []
    for tag_definition in tag_definitions:
        enriched_tag_definition = dict(tag_definition)
        enriched_tag_definition["AlertCondition"] = condition
        enriched_tag_definition["AlertIncident"] = sensor_config.get("incident")
        enriched_tag_definition["AlertSolution"] = sensor_config.get("solution")
        enriched_tag_definition["AlertType"] = sensor_config.get("alert_type")
        enriched_tag_definitions.append(enriched_tag_definition)

    return enriched_tag_definitions


def get_indexed_sensor_value(sensor_config: dict, keys: tuple[str, ...], index: int, default=None):
    """Lay gia tri trong sensor config, ho tro ca field don va field dang list."""

    for key in keys:
        value = sensor_config.get(key)
        if isinstance(value, list):
            if index < len(value) and value[index] not in (None, ""):
                return value[index]
            continue

        if value not in (None, ""):
            return value

    return default


def build_sensor_tag_definition(
    sensor_config: dict,
    config: dict,
    profile_id: str | None = None,
    tag_id: str | None = None,
    index: int = 0,
) -> dict:
    """Tao tagdefinition tam tu InstanceConfigJsonSensor.tag_id."""

    normalized_tag_id = normalize_id(tag_id or sensor_config.get("tag_id"))
    if not normalized_tag_id:
        raise RuntimeError("Thieu tag_id trong InstanceConfigJsonSensor.")

    tag_key = get_indexed_sensor_value(sensor_config, ("tag_key", "tag_keys", "tagKey", "tagKeys"), index)
    tag_name = get_indexed_sensor_value(sensor_config, ("tag_name", "tag_names", "tagName", "tagNames"), index)

    return {
        "Id": normalized_tag_id,
        "TagKey": tag_key or tag_name or normalized_tag_id,
        "TagName": tag_name or sensor_config.get("incident") or config.get("Name") or normalized_tag_id,
        "AddressConfigJson": {
            "port": get_indexed_sensor_value(sensor_config, ("port", "ports"), index),
        },
        "DataType": get_indexed_sensor_value(
            sensor_config,
            ("data_type", "data_types", "datatype", "datatypes"),
            index,
            "float",
        ),
        "Unit": get_indexed_sensor_value(sensor_config, ("unit", "units"), index),
        "ProfileId": profile_id or "-",
        "IsDeleted": 0,
        "FromSensorConfig": True,
    }


def get_tag_definitions_for_config(_connection, config: dict) -> tuple[dict, list[dict]]:
    """Tao danh sach tag can kiem tra truc tiep tu InstanceConfigJsonSensor."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    tag_ids = get_direct_sensor_tag_ids(sensor_config)
    if not tag_ids:
        raise RuntimeError("Thieu tag_id trong InstanceConfigJsonSensor.")

    connection_profile = build_fallback_connection_profile(config, sensor_config)
    tag_definitions = [
        build_sensor_tag_definition(
            sensor_config,
            config,
            tag_id=tag_id,
            index=index,
        )
        for index, tag_id in enumerate(tag_ids)
    ]
    tag_definitions = attach_sensor_config_to_tag_definitions(tag_definitions, sensor_config)
    return connection_profile, tag_definitions


def get_live_tags_by_tag_ids(connection, tag_ids: list[str]) -> dict[str, dict]:
    """Doc gia tri live moi nhat trong bang livetags theo danh sach TagId."""

    normalized_tag_ids = normalize_ids(tag_ids)
    if not normalized_tag_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(normalized_tag_ids))
    sql = f"""
        SELECT
            `Id`,
            `TagId`,
            `Value`,
            `LastUpdated`
        FROM `livetags`
        WHERE `TagId` IN ({placeholders})
        ORDER BY `LastUpdated` DESC
    """

    rows = fetch_all(connection, sql, normalized_tag_ids)
    live_tags_by_id = {}

    for row in rows:
        normalized_tag_id = normalize_id(row["TagId"])
        if normalized_tag_id not in live_tags_by_id:
            row["TagId"] = normalized_tag_id
            row["NumericValue"] = parse_numeric_value(row["Value"])
            live_tags_by_id[normalized_tag_id] = row

    return live_tags_by_id


def get_recent_metric_values_by_tag_ids(connection, tag_ids: list[str], limit_per_tag: int = 10) -> dict[str, list[dict]]:
    """Doc metric history moi nhat cho tung tag de tinh cac condition analysis."""

    metric_values_by_id = {}
    limit_per_tag = max(int(limit_per_tag), 1)

    for tag_id in normalize_ids(tag_ids):
        sql = f"""
            SELECT
                `Id`,
                `TagId`,
                `Value`,
                `LogTime`
            FROM `metricvalues`
            WHERE `TagId` = %s
            ORDER BY `LogTime` DESC
            LIMIT {limit_per_tag}
        """

        rows = fetch_all(connection, sql, (tag_id,))
        for row in rows:
            row["TagId"] = normalize_id(row["TagId"])
            row["NumericValue"] = parse_numeric_value(row["Value"])

        metric_values_by_id[tag_id] = rows

    return metric_values_by_id


def parse_db_date(value) -> date | None:
    """Chuyen gia tri date/datetime tu DB ve date Python."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        cleaned_value = value.strip()
        if not cleaned_value:
            return None

        try:
            return datetime.fromisoformat(cleaned_value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(cleaned_value[:10])
            except ValueError:
                return None

    return None


def get_database_today(connection) -> date:
    """Lay ngay hien tai theo database server de chia bucket hom nay/hom truoc."""

    rows = fetch_all(connection, "SELECT CURDATE() AS `TodayDate`")
    today = parse_db_date(rows[0]["TodayDate"]) if rows else None
    if today is None:
        raise RuntimeError("Khong xac dinh duoc ngay hien tai cua database.")

    return today


def get_metric_daily_averages_by_tag_ids(connection, tag_ids: list[str]) -> dict[str, dict]:
    """Tinh trung binh metricvalues cua hom nay va ngay hom truoc cho tung tag."""

    normalized_tag_ids = normalize_ids(tag_ids)
    if not normalized_tag_ids:
        return {}

    today = get_database_today(connection)
    yesterday = today - timedelta(days=1)
    placeholders = ", ".join(["%s"] * len(normalized_tag_ids))
    sql = f"""
        SELECT
            `Id`,
            `TagId`,
            `Value`,
            `LogTime`
        FROM `metricvalues`
        WHERE `TagId` IN ({placeholders})
          AND `LogTime` >= DATE_SUB(CURDATE(), INTERVAL 1 DAY)
          AND `LogTime` < DATE_ADD(CURDATE(), INTERVAL 1 DAY)
        ORDER BY `TagId`, `LogTime`
    """

    values_by_tag = {
        tag_id: {
            "today": [],
            "yesterday": [],
            "last_today_log_time": None,
            "last_yesterday_log_time": None,
        }
        for tag_id in normalized_tag_ids
    }

    for row in fetch_all(connection, sql, normalized_tag_ids):
        tag_id = normalize_id(row["TagId"])
        numeric_value = parse_numeric_value(row["Value"])
        log_date = parse_db_date(row["LogTime"])
        if tag_id not in values_by_tag or numeric_value is None or log_date is None:
            continue

        if log_date == today:
            values_by_tag[tag_id]["today"].append(numeric_value)
            values_by_tag[tag_id]["last_today_log_time"] = row["LogTime"]
        elif log_date == yesterday:
            values_by_tag[tag_id]["yesterday"].append(numeric_value)
            values_by_tag[tag_id]["last_yesterday_log_time"] = row["LogTime"]

    averages_by_tag = {}
    for tag_id, grouped_values in values_by_tag.items():
        today_values = grouped_values["today"]
        yesterday_values = grouped_values["yesterday"]
        averages_by_tag[tag_id] = {
            "TodayDate": today.isoformat(),
            "YesterdayDate": yesterday.isoformat(),
            "TodayAverage": sum(today_values) / len(today_values) if today_values else None,
            "YesterdayAverage": sum(yesterday_values) / len(yesterday_values) if yesterday_values else None,
            "TodaySampleCount": len(today_values),
            "YesterdaySampleCount": len(yesterday_values),
            "LastTodayLogTime": grouped_values["last_today_log_time"],
            "LastYesterdayLogTime": grouped_values["last_yesterday_log_time"],
        }

    return averages_by_tag


def attach_metric_values_to_live_tags(
    live_tags_by_id: dict[str, dict],
    metric_values_by_id: dict[str, list[dict]],
) -> dict[str, dict]:
    """Gan metric history va dung metric moi nhat lam gia tri hien tai."""

    for tag_id, metric_values in metric_values_by_id.items():
        live_tag = live_tags_by_id.get(tag_id)
        if not metric_values:
            if live_tag is not None:
                live_tag["MetricValues"] = []
            continue

        latest_metric = metric_values[0]
        metric_fields = {
            "TagId": tag_id,
            "Value": latest_metric["Value"],
            "LastUpdated": latest_metric["LogTime"],
            "NumericValue": latest_metric["NumericValue"],
            "MetricValueId": latest_metric["Id"],
            "MetricValues": metric_values,
            "Source": "metricvalues",
        }

        if live_tag is not None:
            live_tag.update(metric_fields)
            continue

        metric_fields["Id"] = latest_metric["Id"]
        live_tags_by_id[tag_id] = metric_fields

    return live_tags_by_id


def attach_metric_daily_averages_to_live_tags(
    live_tags_by_id: dict[str, dict],
    metric_daily_averages_by_id: dict[str, dict],
) -> dict[str, dict]:
    """Gan trung binh ngay tu metricvalues vao tag hien tai."""

    for tag_id, daily_averages in metric_daily_averages_by_id.items():
        live_tag = live_tags_by_id.get(tag_id)
        if live_tag is None:
            continue

        live_tag["MetricDailyAverages"] = daily_averages

    return live_tags_by_id


def save_mail_history(mail_sensor_config_id: str | None, subject: str, message: str, status: bool = True) -> str:
    """Luu lich su email da gui vao bang mailhistories."""

    history_id = uuid.uuid4().hex
    sql = """
        INSERT INTO `mailhistories`
            (`Id`, `CreatedDate`, `Subject`, `Message`, `Status`, `MailSensorConfigId`)
        VALUES
            (%s, NOW(6), %s, %s, %s, %s)
    """

    with open_database() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                sql,
                (
                    history_id,
                    str(subject or "")[:500],
                    str(message or ""),
                    1 if status else 0,
                    mail_sensor_config_id or None,
                ),
            )
            if hasattr(connection, "commit"):
                connection.commit()
        finally:
            cursor.close()

    return history_id


def build_monitoring_snapshot(connection, config: dict) -> tuple[dict, dict, list[dict], dict[str, dict], list[dict]]:
    """Doc du lieu can thiet de kiem tra mot cau hinh."""

    connection_profile, tag_definitions = get_tag_definitions_for_config(connection, config)
    tag_ids = [tag_definition["Id"] for tag_definition in tag_definitions]
    live_tags_by_id = get_live_tags_by_tag_ids(
        connection,
        tag_ids,
    )
    metric_values_by_id = get_recent_metric_values_by_tag_ids(connection, tag_ids)
    live_tags_by_id = attach_metric_values_to_live_tags(live_tags_by_id, metric_values_by_id)
    metric_daily_averages_by_id = get_metric_daily_averages_by_tag_ids(connection, tag_ids)
    live_tags_by_id = attach_metric_daily_averages_to_live_tags(
        live_tags_by_id,
        metric_daily_averages_by_id,
    )
    threshold_checks = check_thresholds(tag_definitions, live_tags_by_id)
    return config, connection_profile, tag_definitions, live_tags_by_id, threshold_checks


def load_monitoring_snapshot_for_config(config: dict) -> tuple[dict, dict, list[dict], dict[str, dict], list[dict]]:
    """Mo DB rieng va doc snapshot cho mot cau hinh."""

    with open_database() as connection:
        return build_monitoring_snapshot(connection, config)


def load_monitoring_snapshot() -> tuple[dict, dict, list[dict], dict[str, dict], list[dict]]:
    """Doc toan bo du lieu can thiet cho cau hinh active moi nhat."""

    with open_database() as connection:
        config = get_active_mail_sensor_config(connection)
        return build_monitoring_snapshot(connection, config)
