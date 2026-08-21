from __future__ import annotations

import json
import uuid
from contextlib import contextmanager

from settings import get_db_config
from thresholds import check_thresholds, parse_numeric_value
from utils import normalize_tag_keys


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


def get_mail_sensor_configs(connection):
    """Doc 2 cot InstanceConfigJsonMail va InstanceConfigJsonSensor tu bang mailsensorconfigs."""

    sql = """
        SELECT
            `Id`,
            `Name`,
            `InstanceConfigJsonMail`,
            `InstanceConfigJsonSensor`,
            `IsDeleted`
        FROM `mailsensorconfigs`
        ORDER BY `CreatedDate` DESC
    """

    rows = fetch_all(connection, sql)
    for row in rows:
        row["InstanceConfigJsonMail"] = parse_json_column(
            row,
            "InstanceConfigJsonMail",
            "mailsensorconfigs",
        )
        row["InstanceConfigJsonSensor"] = parse_json_column(
            row,
            "InstanceConfigJsonSensor",
            "mailsensorconfigs",
        )

    return rows


def get_active_mail_sensor_config(connection):
    """Lay dong cau hinh dang duoc su dung trong bang mailsensorconfigs."""

    configs = get_mail_sensor_configs(connection)

    for config in configs:
        if int(config["IsDeleted"]) == 0:
            return config

    raise RuntimeError("Khong tim thay cau hinh active trong bang mailsensorconfigs.")


def get_connection_profile_by_iolink_ip(connection, ip_iolink: str) -> dict:
    """Tim connectionprofiles.Id dua tren IP IO-Link trong InstanceConfigJson."""

    if not ip_iolink:
        raise RuntimeError("Thieu ip_iolink trong InstanceConfigJsonSensor.")

    sql = """
        SELECT
            `Id`,
            `SourceName`,
            `InstanceConfigJson`,
            `IsDeleted`
        FROM `connectionprofiles`
        WHERE `IsDeleted` = 0
          AND CAST(`InstanceConfigJson` AS CHAR) LIKE %s
        ORDER BY `CreatedDate` DESC
    """

    rows = fetch_all(connection, sql, (f"%{ip_iolink}%",))
    ip_keys = ("machine_ip", "ip_iolink", "iolink_ip", "ip", "host")

    for row in rows:
        profile_config = parse_json_column(row, "InstanceConfigJson", "connectionprofiles") or {}
        row["InstanceConfigJson"] = profile_config

        if any(str(profile_config.get(key, "")).strip() == str(ip_iolink) for key in ip_keys):
            return row

    raise RuntimeError(f"Khong tim thay connectionprofile active cho IP IO-Link: {ip_iolink}")


def get_tag_definitions_by_profile_and_port(connection, profile_id: str, port) -> list[dict]:
    """Tim tagdefinitions theo connectionprofiles.Id va port trong AddressConfigJson."""

    if not profile_id:
        raise RuntimeError("Thieu connection profile id.")
    if port in (None, ""):
        raise RuntimeError("Thieu port trong InstanceConfigJsonSensor.")

    sql = """
        SELECT
            `Id`,
            `TagKey`,
            `TagName`,
            `AddressConfigJson`,
            `DataType`,
            `Unit`,
            `ProfileId`,
            `IsDeleted`
        FROM `tagdefinitions`
        WHERE `IsDeleted` = 0
          AND `ProfileId` = %s
        ORDER BY `CreatedDate`, `TagKey`
    """

    rows = fetch_all(connection, sql, (profile_id,))
    tag_definitions = []

    for row in rows:
        address_config = parse_json_column(row, "AddressConfigJson", "tagdefinitions") or {}
        row["AddressConfigJson"] = address_config

        if str(address_config.get("port", "")).strip() == str(port):
            tag_definitions.append(row)

    return tag_definitions


def get_tag_definitions_for_config(connection, config: dict) -> tuple[dict, list[dict]]:
    """Tim profile theo ip_iolink, sau do tim tag_key can canh bao theo port."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    connection_profile = get_connection_profile_by_iolink_ip(
        connection,
        sensor_config.get("ip_iolink", ""),
    )
    tag_definitions = get_tag_definitions_by_profile_and_port(
        connection,
        connection_profile["Id"],
        sensor_config.get("port"),
    )
    configured_tag_keys = normalize_tag_keys(sensor_config.get("tag_key", []))

    if not tag_definitions:
        raise RuntimeError(
            "Khong tim thay tagdefinition active cho "
            f"ProfileId={connection_profile['Id']} va port={sensor_config.get('port')}."
        )

    if configured_tag_keys:
        rows_by_key = {tag_definition["TagKey"]: tag_definition for tag_definition in tag_definitions}
        missing_tag_keys = [tag_key for tag_key in configured_tag_keys if tag_key not in rows_by_key]
        if missing_tag_keys:
            raise RuntimeError(f"Khong tim thay tag_key trong tagdefinitions: {', '.join(missing_tag_keys)}")

        tag_definitions = [rows_by_key[tag_key] for tag_key in configured_tag_keys]

    return connection_profile, tag_definitions


def get_live_tags_by_tag_ids(connection, tag_ids: list[str]) -> dict[str, dict]:
    """Doc gia tri live moi nhat trong bang livetags theo danh sach TagId."""

    if not tag_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(tag_ids))
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

    rows = fetch_all(connection, sql, tag_ids)
    live_tags_by_id = {}

    for row in rows:
        if row["TagId"] not in live_tags_by_id:
            row["NumericValue"] = parse_numeric_value(row["Value"])
            live_tags_by_id[row["TagId"]] = row

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


def load_monitoring_snapshot() -> tuple[dict, dict, list[dict], dict[str, dict], list[dict]]:
    """Doc toan bo du lieu can thiet cho mot chu ky kiem tra."""

    with open_database() as connection:
        config = get_active_mail_sensor_config(connection)
        connection_profile, tag_definitions = get_tag_definitions_for_config(connection, config)
        live_tags_by_id = get_live_tags_by_tag_ids(
            connection,
            [tag_definition["Id"] for tag_definition in tag_definitions],
        )
        threshold_checks = check_thresholds(tag_definitions, live_tags_by_id)

    return config, connection_profile, tag_definitions, live_tags_by_id, threshold_checks
