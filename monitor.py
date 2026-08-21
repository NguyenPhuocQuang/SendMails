from __future__ import annotations

import smtplib
import sys
import time

from console_log import print_cooldown_log, print_json, print_parameter_log
from database import load_monitoring_snapshot, save_mail_history
from email_builder import build_email_body, build_email_html_body, build_email_subject
from mailer import send_mail
from thresholds import parse_numeric_value


def get_check_interval(config: dict, interval_override: float | None) -> float:
    """Lay thoi gian nghi giua cac chu ky kiem tra."""

    if interval_override is not None:
        return max(float(interval_override), 1)

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    interval = parse_numeric_value(sensor_config.get("time_threshold"))
    if interval is None or interval <= 0:
        return 10

    return max(interval, 1)


def get_alert_key(config: dict, tag: dict) -> str:
    """Tao key de theo doi cooldown cho tung tag cua tung config."""

    return f"{config['Id']}:{tag['TagId']}"


def split_tags_by_cooldown(
    config: dict,
    exceeded_tags: list[dict],
    last_alert_at: dict[str, float],
    cooldown_seconds: float,
    now: float,
) -> tuple[list[dict], list[dict]]:
    """Tach tag vuot nguong thanh nhom duoc gui va nhom dang cooldown."""

    ready_tags = []
    cooldown_tags = []

    for tag in exceeded_tags:
        alert_key = get_alert_key(config, tag)
        last_sent_at = last_alert_at.get(alert_key)

        if last_sent_at is None or now - last_sent_at >= cooldown_seconds:
            ready_tags.append(tag)
            continue

        tag_in_cooldown = dict(tag)
        tag_in_cooldown["CooldownRemainingSec"] = round(cooldown_seconds - (now - last_sent_at), 1)
        cooldown_tags.append(tag_in_cooldown)

    return ready_tags, cooldown_tags


def mark_alert_sent(config: dict, alert_tags: list[dict], last_alert_at: dict[str, float], now: float) -> None:
    """Cap nhat thoi diem da gui mail cho cac tag vua canh bao."""

    for tag in alert_tags:
        last_alert_at[get_alert_key(config, tag)] = now


def clear_recovered_alerts(config: dict, threshold_checks: list[dict], last_alert_at: dict[str, float]) -> None:
    """Xoa cooldown cua tag da ve trang thai khong vuot nguong."""

    for tag in threshold_checks:
        if not tag["Exceeded"]:
            last_alert_at.pop(get_alert_key(config, tag), None)


def build_alert_email(args, config: dict, mail_config: dict, ready_tags: list[dict]) -> tuple[str, str, str | None]:
    """Tao subject/body/html body cho nhom tag can gui canh bao."""

    if args.body:
        body = args.body
        html_body = None
    else:
        body = build_email_body(config, ready_tags)
        html_body = build_email_html_body(config, ready_tags)

    subject = args.subject or mail_config.get("subject") or build_email_subject(config, ready_tags)
    return subject, body, html_body


def record_sent_mail_history(config: dict, subject: str, body: str) -> None:
    """Luu lich su mail da gui, chi log loi neu DB history gap su co."""

    try:
        history_id = save_mail_history(config.get("Id"), subject, body, status=True)
    except Exception as exc:
        print("\nDa gui mail thanh cong nhung luu lich su mail vao mailhistories that bai.")
        print(f"Chi tiet: {exc}")
        return

    print(f"Da luu lich su mail vao mailhistories: {history_id}")


def run_check_once(args, last_alert_at: dict[str, float] | None = None, cycle_number: int | None = None) -> float:
    """Chay mot chu ky doc DB, kiem tra nguong va gui mail neu can."""

    last_alert_at = last_alert_at if last_alert_at is not None else {}
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")

    if cycle_number is None:
        print(f"\n===== KIEM TRA {started_at} =====")
    else:
        print(f"\n===== CHU KY {cycle_number} | {started_at} =====")

    config, connection_profile, tag_definitions, live_tags_by_id, threshold_checks = load_monitoring_snapshot()
    mail_config = config["InstanceConfigJsonMail"]
    exceeded_tags = [tag for tag in threshold_checks if tag["Exceeded"]]
    check_interval = get_check_interval(config, args.interval)

    print(f"Doc cau hinh mail/sensor thanh cong: {config['Name']}")
    if args.verbose_json or not args.loop:
        print_json("InstanceConfigJsonMail", mail_config)
        print_json("InstanceConfigJsonSensor", config["InstanceConfigJsonSensor"])
        print_json("ConnectionProfile", connection_profile)
        print_json("TagDefinitions", tag_definitions)
        print_json("LiveTags", list(live_tags_by_id.values()))
        print_json("ThresholdChecks", threshold_checks)

    print_parameter_log(config, connection_profile, threshold_checks)
    clear_recovered_alerts(config, threshold_checks, last_alert_at)

    if not exceeded_tags:
        print("\nKhong co tag vuot nguong. Khong gui mail.")
        return check_interval

    now = time.time()
    ready_tags, cooldown_tags = split_tags_by_cooldown(
        config,
        exceeded_tags,
        last_alert_at,
        max(float(args.cooldown), 0),
        now,
    )
    print_cooldown_log(cooldown_tags)

    if not ready_tags:
        print("\nTat ca tag vuot nguong dang trong cooldown. Khong gui mail.")
        return check_interval

    subject, body, html_body = build_alert_email(args, config, mail_config, ready_tags)

    if args.dry_run:
        print("\nDry run: co tag vuot nguong nhung chua gui mail.")
        print(f"Subject: {subject}")
        print("Body:")
        print(body)
        if html_body:
            print("\nHTML body: da tao kem theo de email hien thi dep hon trong Gmail/Outlook.")

        return check_interval

    try:
        receiver_emails = send_mail(mail_config, body, subject, html_body)
    except smtplib.SMTPAuthenticationError as exc:
        print("\nLoi gui mail: Dang nhap SMTP that bai.")
        print("Server SMTP tu choi sender_email hoac sender_password.")
        print(f"Chi tiet SMTP: {exc.smtp_code} {exc.smtp_error.decode(errors='ignore')}")
        if not args.loop:
            sys.exit(1)
        return check_interval
    except (smtplib.SMTPException, OSError) as exc:
        print("\nLoi gui mail: Khong gui duoc email qua SMTP.")
        print(f"Chi tiet: {exc}")
        if not args.loop:
            sys.exit(1)
        return check_interval

    record_sent_mail_history(config, subject, body)
    mark_alert_sent(config, ready_tags, last_alert_at, now)
    print(f"Da gui mail thanh cong toi: {', '.join(receiver_emails)}")

    return check_interval


def run_loop(args) -> None:
    """Chay he thong giam sat lien tuc."""

    last_alert_at: dict[str, float] = {}
    cycle_number = 0

    print("Bat dau chay lien tuc. Nhan Ctrl+C de dung.")
    print(f"Cooldown gui lai mail: {max(float(args.cooldown), 0)}s")

    try:
        while True:
            cycle_number += 1
            try:
                check_interval = run_check_once(args, last_alert_at, cycle_number)
            except Exception as exc:
                check_interval = max(float(args.interval or 10), 1)
                print(f"\nLoi chu ky {cycle_number}: {exc}")

            if args.max_cycles is not None and cycle_number >= args.max_cycles:
                print(f"\nDa chay du {args.max_cycles} chu ky. Dung loop.")
                return

            print(f"\nCho {check_interval}s truoc chu ky tiep theo...")
            time.sleep(check_interval)
    except KeyboardInterrupt:
        print("\nDa dung chuong trinh theo yeu cau nguoi dung.")
