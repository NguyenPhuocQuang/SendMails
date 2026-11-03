from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import sys
import time
from threading import Event, Lock, Thread

from console_log import print_alerting_log, print_cooldown_log, print_json, print_parameter_log
from database import load_active_mail_sensor_configs, load_monitoring_snapshot_for_config
from email_builder import build_email_body, build_email_html_body, build_email_subject
from mail_worker import MailJob, MailWorker
from thresholds import parse_numeric_value


LOG_LOCK = Lock()
logger = logging.getLogger(__name__)


def get_check_interval(
    config: dict,
    interval_override: float | None,
    connection_profile: dict | None = None,
) -> float:
    """Lay thoi gian nghi giua cac chu ky kiem tra."""

    if interval_override is not None:
        return max(float(interval_override), 1)

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    interval = parse_numeric_value(sensor_config.get("time_threshold"))
    if interval is None or interval <= 0:
        polling_interval_ms = parse_numeric_value((connection_profile or {}).get("PollingIntervalMs"))
        if polling_interval_ms is not None and polling_interval_ms > 0:
            return max(polling_interval_ms / 1000, 1)

        return 10

    return max(interval, 1)


def get_cooldown_seconds(args, config: dict, mail_config: dict) -> float:
    """Lay cooldown tu config neu co, neu khong thi dung tham so CLI."""

    sensor_config = config.get("InstanceConfigJsonSensor") or {}
    for source in (sensor_config, mail_config, config):
        if not isinstance(source, dict):
            continue

        for key in ("cooldown", "cooldown_seconds", "mail_cooldown", "alert_cooldown"):
            cooldown = parse_numeric_value(source.get(key))
            if cooldown is not None:
                return max(float(cooldown), 0)

    return max(float(args.cooldown), 0)


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


def split_tags_by_alert_state(
    config: dict,
    exceeded_tags: list[dict],
    active_alert_keys: set[str] | None,
    last_alert_at: dict[str, float],
    cooldown_seconds: float,
    now: float,
) -> tuple[list[dict], list[dict]]:
    """Tach tag moi can canh bao va tag da dang trong trang thai alerting."""

    if active_alert_keys is None:
        return exceeded_tags, []

    ready_tags = []
    alerting_tags = []

    for tag in exceeded_tags:
        alert_key = get_alert_key(config, tag)
        last_sent_at = last_alert_at.get(alert_key)
        cooldown_elapsed = (
            cooldown_seconds > 0
            and last_sent_at is not None
            and now - last_sent_at >= cooldown_seconds
        )

        if alert_key not in active_alert_keys or cooldown_elapsed:
            ready_tags.append(tag)
            continue

        alerting_tags.append(dict(tag))

    return ready_tags, alerting_tags


def mark_alert_sent(
    config: dict,
    alert_tags: list[dict],
    last_alert_at: dict[str, float],
    now: float,
    active_alert_keys: set[str] | None = None,
) -> None:
    """Cap nhat thoi diem tag da duoc dua vao hang doi gui mail."""

    for tag in alert_tags:
        alert_key = get_alert_key(config, tag)
        last_alert_at[alert_key] = now
        if active_alert_keys is not None:
            active_alert_keys.add(alert_key)


def clear_recovered_alerts(
    config: dict,
    threshold_checks: list[dict],
    last_alert_at: dict[str, float],
    active_alert_keys: set[str] | None = None,
) -> None:
    """Xoa trang thai alerting cua tag da ve trang thai khong vuot nguong."""

    for tag in threshold_checks:
        if not tag["Exceeded"]:
            alert_key = get_alert_key(config, tag)
            if active_alert_keys is not None:
                active_alert_keys.discard(alert_key)


def build_alert_email(args, config: dict, mail_config: dict, ready_tags: list[dict]) -> tuple[str, str, str | None]:
    """Tao subject/body/html body cho nhom tag can gui canh bao."""

    if not isinstance(mail_config, dict):
        raise RuntimeError("InstanceConfigJsonMail phai la JSON object hop le.")

    if args.body:
        body = args.body
        html_body = None
    else:
        body = build_email_body(config, ready_tags)
        html_body = build_email_html_body(config, ready_tags)

    subject_template = mail_config.get("subject_template")
    subject = (
        args.subject
        or mail_config.get("subject")
        or (render_subject_template(subject_template, config, ready_tags) if subject_template else None)
        or build_email_subject(config, ready_tags)
    )
    return subject, body, html_body


def render_subject_template(template, config: dict, ready_tags: list[dict]) -> str:
    """Render cac placeholder don gian trong subject_template."""

    sensor_config = config["InstanceConfigJsonSensor"] or {}
    rendered_subject = str(template)
    replacements = {
        "{{device_name}}": config.get("Name"),
        "{{config_name}}": config.get("Name"),
        "{{machine_id}}": config.get("MachineId"),
        "{{incident}}": sensor_config.get("incident"),
        "{{tag_count}}": len(ready_tags),
    }

    for placeholder, value in replacements.items():
        rendered_subject = rendered_subject.replace(placeholder, str(value or ""))

    return rendered_subject


def print_config_snapshot(
    args,
    config: dict,
    connection_profile: dict,
    tag_definitions: list[dict],
    live_tags_by_id: dict[str, dict],
    threshold_checks: list[dict],
) -> None:
    """In thong tin kiem tra cua mot cau hinh."""

    logger.info("Doc cau hinh mail/sensor thanh cong: %s", config["Name"])
    if args.verbose_json or not args.loop:
        print_json("InstanceConfigJsonMail", config["InstanceConfigJsonMail"])
        print_json("InstanceConfigJsonSensor", config["InstanceConfigJsonSensor"])
        print_json("ConnectionProfile", connection_profile)
        print_json("TagDefinitions", tag_definitions)
        print_json("LiveTags", list(live_tags_by_id.values()))
        print_json("ThresholdChecks", threshold_checks)

    print_parameter_log(config, connection_profile, threshold_checks)


def run_config_check_once(
    args,
    config: dict,
    last_alert_at: dict[str, float] | None = None,
    cycle_number: int | None = None,
    mail_worker: MailWorker | None = None,
    active_alert_keys: set[str] | None = None,
) -> float:
    """Chay mot chu ky kiem tra cho mot cau hinh."""

    last_alert_at = last_alert_at if last_alert_at is not None else {}
    owns_mail_worker = mail_worker is None
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    config, connection_profile, tag_definitions, live_tags_by_id, threshold_checks = load_monitoring_snapshot_for_config(
        config
    )
    mail_config = config["InstanceConfigJsonMail"]
    exceeded_tags = [tag for tag in threshold_checks if tag["Exceeded"]]
    check_interval = get_check_interval(config, args.interval, connection_profile)
    cooldown_seconds = get_cooldown_seconds(args, config, mail_config)

    with LOG_LOCK:
        if cycle_number is None:
            logger.info("\n===== KIEM TRA | %s | %s =====", config["Name"], started_at)
        else:
            logger.info(
                "\n===== %s | CHU KY %s | %s =====",
                config["Name"],
                cycle_number,
                started_at,
            )

        print_config_snapshot(
            args,
            config,
            connection_profile,
            tag_definitions,
            live_tags_by_id,
            threshold_checks,
        )
        clear_recovered_alerts(config, threshold_checks, last_alert_at, active_alert_keys)

        if not exceeded_tags:
            logger.info("\nKhong co tag vuot nguong. Khong gui mail.")
            return check_interval

        now = time.time()
        ready_tags, alerting_tags = split_tags_by_alert_state(
            config,
            exceeded_tags,
            active_alert_keys,
            last_alert_at,
            cooldown_seconds,
            now,
        )
        print_alerting_log(alerting_tags)

        if not ready_tags:
            logger.info("\nTat ca tag vuot nguong da o trang thai alerting. Khong gui mail.")
            return check_interval

        ready_tags, cooldown_tags = split_tags_by_cooldown(
            config,
            ready_tags,
            last_alert_at,
            cooldown_seconds,
            now,
        )
        print_cooldown_log(cooldown_tags)

        if not ready_tags:
            logger.info("\nTat ca tag vuot nguong dang trong cooldown. Khong gui mail.")
            return check_interval

        subject, body, html_body = build_alert_email(args, config, mail_config, ready_tags)

        if args.dry_run:
            logger.info("\nDry run: co tag vuot nguong nhung chua gui mail.")
            logger.info("Subject: %s", subject)
            logger.info("Body:")
            logger.info(body)
            if html_body:
                logger.info("\nHTML body: da tao kem theo de email hien thi dep hon trong Gmail/Outlook.")

            mark_alert_sent(config, ready_tags, last_alert_at, now, active_alert_keys)
            return check_interval

        mark_alert_sent(config, ready_tags, last_alert_at, now, active_alert_keys)
        if mail_worker is None:
            mail_worker = MailWorker()

        mail_worker.enqueue(
            MailJob(
                config_id=config.get("Id"),
                mail_config=mail_config,
                subject=subject,
                body=body,
                html_body=html_body,
            )
        )
        logger.info("Da dua mail canh bao vao hang doi gui bang mail worker thread.")

    if owns_mail_worker:
        mail_worker.wait_until_idle()
        had_errors = mail_worker.has_errors
        mail_worker.stop()
        if had_errors:
            sys.exit(1)

    return check_interval


def get_thread_name(config: dict) -> str:
    """Tao ten thread ngan gon theo config."""

    config_id = str(config.get("Id") or "")[:8] or "unknown"
    return f"config-monitor-{config_id}"


def get_fallback_interval(args) -> float:
    """Lay interval fallback khi mot thread gap loi."""

    return max(float(args.interval or 10), 1)


def run_check_once(
    args,
    last_alert_at: dict[str, dict[str, float]] | None = None,
    cycle_number: int | None = None,
    mail_worker: MailWorker | None = None,
) -> float:
    """Doc tat ca cau hinh va kiem tra song song moi cau hinh bang mot thread."""

    configs = load_active_mail_sensor_configs()
    last_alert_at = last_alert_at if last_alert_at is not None else {}
    owns_mail_worker = mail_worker is None
    if mail_worker is None:
        mail_worker = MailWorker()

    mail_worker.start()
    logger.info("\nDa doc %s cau hinh active. Bat dau xu ly song song...", len(configs))

    intervals = []
    with ThreadPoolExecutor(max_workers=max(len(configs), 1), thread_name_prefix="config-check") as executor:
        future_to_config = {
            executor.submit(
                run_config_check_once,
                args,
                config,
                last_alert_at.setdefault(config["Id"], {}),
                cycle_number,
                mail_worker,
            ): config
            for config in configs
        }

        for future in as_completed(future_to_config):
            config = future_to_config[future]
            try:
                intervals.append(future.result())
            except Exception as exc:
                with LOG_LOCK:
                    logger.exception("\nLoi khi xu ly cau hinh %s: %s", config.get("Name"), exc)
                intervals.append(get_fallback_interval(args))

    if owns_mail_worker:
        mail_worker.wait_until_idle()
        had_errors = mail_worker.has_errors
        mail_worker.stop()
        if had_errors:
            sys.exit(1)

    return min(intervals) if intervals else get_fallback_interval(args)


def run_config_loop(args, config: dict, mail_worker: MailWorker, stop_event: Event) -> None:
    """Thread doc DB va kiem tra lap lai cho mot cau hinh co dinh."""

    last_alert_at: dict[str, float] = {}
    active_alert_keys: set[str] = set()
    cycle_number = 0

    while not stop_event.is_set():
        cycle_number += 1
        try:
            check_interval = run_config_check_once(
                args,
                config,
                last_alert_at,
                cycle_number,
                mail_worker,
                active_alert_keys,
            )
        except Exception as exc:
            check_interval = get_fallback_interval(args)
            with LOG_LOCK:
                logger.exception(
                    "\nLoi thread %s - %s: %s",
                    get_thread_name(config),
                    config.get("Name"),
                    exc,
                )

        if args.max_cycles is not None and cycle_number >= args.max_cycles:
            with LOG_LOCK:
                logger.info(
                    "\n%s: da chay du %s chu ky. Dung thread.",
                    config.get("Name"),
                    args.max_cycles,
                )
            return

        with LOG_LOCK:
            logger.info(
                "\n%s: cho %ss truoc chu ky tiep theo...",
                config.get("Name"),
                check_interval,
            )
        stop_event.wait(check_interval)


def run_loop(args) -> None:
    """Chay manager quan ly worker rieng cho tung cau hinh active."""

    from condition_manager import MailConditionManager

    mail_worker = MailWorker()
    manager = MailConditionManager(args, mail_worker=mail_worker)
    mail_worker.start()

    try:
        manager.start_all_active_configs()
        if args.max_cycles is not None:
            manager.join_all()
            return

        logger.info("Mail condition manager dang chay. Nhan Ctrl+C de dung.")
        manager.run_sync_loop()
    except KeyboardInterrupt:
        logger.info("\nDa dung chuong trinh theo yeu cau nguoi dung.")
    finally:
        logger.info("\nDang dung condition workers va mail worker sau khi xu ly het job con lai...")
        manager.stop_all()
        mail_worker.stop()
