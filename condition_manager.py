from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from threading import Event, RLock

from condition_worker import MailConditionWorker
from database import load_active_mail_sensor_configs
from mail_worker import MailWorker
from settings import DEFAULT_MAIL_CONFIG_RELOAD_INTERVAL_SECONDS


logger = logging.getLogger(__name__)


@dataclass
class ManagedConditionWorker:
    worker: MailConditionWorker
    fingerprint: str


def parse_bool(value, default: bool = True) -> bool:
    """Parse cac kieu boolean thuong gap trong DB/JSON config."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        if normalized_value in ("1", "true", "yes", "y", "on", "enabled", "active"):
            return True
        if normalized_value in ("0", "false", "no", "n", "off", "disabled", "inactive"):
            return False

    return default


def find_enabled_value(config: dict):
    """Tim field enabled/is_enabled trong config hoac JSON con neu co."""

    for source in (
        config,
        config.get("InstanceConfigJsonMail") or {},
        config.get("InstanceConfigJsonSensor") or {},
    ):
        if not isinstance(source, dict):
            continue

        for key in ("enabled", "Enabled", "is_enabled", "IsEnabled", "isEnabled"):
            if key in source:
                return source[key]

    return None


def is_config_enabled(config: dict) -> bool:
    """Xac dinh config co nen co worker hay khong dua tren schema hien tai."""

    if parse_bool(config.get("IsDeleted"), default=False):
        return False

    enabled_value = find_enabled_value(config)
    return parse_bool(enabled_value, default=True)


def get_config_fingerprint(config: dict) -> str:
    """Tao dau van tay de biet config co thay doi va can reload worker."""

    return json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)


def get_config_reload_interval(args) -> float:
    """Lay chu ky doc lai toan bo cau hinh mail tu DB."""

    interval = getattr(args, "config_reload_interval", None)
    if interval is None:
        interval = DEFAULT_MAIL_CONFIG_RELOAD_INTERVAL_SECONDS

    return max(float(interval), 1)


class MailConditionManager:
    """Quan ly lifecycle worker theo config_id va ngan duplicate thread."""

    def __init__(self, args, mail_worker: MailWorker | None = None, config_loader=None) -> None:
        self.args = args
        self.mail_worker = mail_worker or MailWorker()
        self.config_loader = config_loader or load_active_mail_sensor_configs
        self.workers: dict[str, ManagedConditionWorker] = {}
        self.lock = RLock()
        self.stop_event = Event()

    def start_all_active_configs(self) -> None:
        """Doc DB luc startup va start worker cho cac config enabled."""

        configs = self.load_configs_safely()
        logger.info("Da doc %s cau hinh active tu database.", len(configs))
        self.sync_configs(configs)

    def load_configs_safely(self) -> list[dict]:
        """Load configs, neu khong co config active thi tra list rong."""

        try:
            return self.config_loader()
        except RuntimeError as exc:
            if "Khong tim thay cau hinh active" in str(exc):
                logger.warning("Khong tim thay cau hinh active trong database.")
                return []
            raise

    def sync_from_database(self) -> None:
        """Dong bo worker hien tai voi danh sach config moi nhat trong DB."""

        configs = self.load_configs_safely()
        self.sync_configs(configs)

    def sync_configs(self, configs: list[dict]) -> None:
        """Start/reload/stop worker dua tren danh sach config hien tai."""

        desired_configs = {
            str(config.get("Id")): config
            for config in configs
            if config.get("Id") and is_config_enabled(config)
        }
        actions: list[tuple[str, str, dict | None]] = []

        with self.lock:
            current_ids = set(self.workers)
            desired_ids = set(desired_configs)

            for config_id in current_ids - desired_ids:
                actions.append(("stop", config_id, None))

            for config_id, config in desired_configs.items():
                fingerprint = get_config_fingerprint(config)
                managed_worker = self.workers.get(config_id)
                if managed_worker is None or not managed_worker.worker.is_alive():
                    actions.append(("start", config_id, config))
                elif managed_worker.fingerprint != fingerprint:
                    actions.append(("reload", config_id, config))

        for action, config_id, config in actions:
            if action == "stop":
                self.stop_worker(config_id)
            elif action == "start" and config is not None:
                self.start_worker(config)
            elif action == "reload" and config is not None:
                self.reload_worker(config)

    def start_worker(self, config: dict) -> bool:
        """Start worker cho config neu enabled va chua co worker song."""

        config_id = str(config.get("Id") or "")
        if not config_id:
            raise RuntimeError("Khong the start worker vi config thieu Id.")
        if not is_config_enabled(config):
            logger.info("Config %s dang disabled, khong start worker.", config_id)
            return False

        with self.lock:
            managed_worker = self.workers.get(config_id)
            if managed_worker is not None and managed_worker.worker.is_alive():
                logger.info("Config %s da co worker dang chay, bo qua start duplicate.", config_id)
                return False

            worker = MailConditionWorker(self.args, config, self.mail_worker)
            self.workers[config_id] = ManagedConditionWorker(
                worker=worker,
                fingerprint=get_config_fingerprint(config),
            )

        worker.start()
        logger.info("Da start worker cho config_id=%s, name=%s.", config_id, config.get("Name"))
        return True

    def stop_worker(self, config_id: str, timeout: float = 10) -> bool:
        """Stop worker theo config_id neu ton tai."""

        with self.lock:
            managed_worker = self.workers.pop(str(config_id), None)

        if managed_worker is None:
            logger.info("Config %s khong co worker de stop.", config_id)
            return False

        worker = managed_worker.worker
        worker.stop()
        worker.join(timeout=timeout)
        if worker.is_alive():
            logger.warning("Worker config_id=%s chua dung sau %ss.", config_id, timeout)
        else:
            logger.info("Da stop worker config_id=%s.", config_id)

        return True

    def reload_worker(self, config: dict) -> None:
        """Stop worker cu va start worker moi voi config moi nhat."""

        config_id = str(config.get("Id") or "")
        logger.info("Reload worker config_id=%s, name=%s.", config_id, config.get("Name"))
        self.stop_worker(config_id)
        self.start_worker(config)

    def delete_worker(self, config_id: str) -> bool:
        """Alias ro nghia nghiep vu khi config bi delete."""

        return self.stop_worker(config_id)

    def run_sync_loop(self) -> None:
        """Lien tuc sync DB de bat create/update/delete/enable/disable config."""

        interval = get_config_reload_interval(self.args)
        logger.info(
            "Se doc lai tat ca cau hinh mail trong DB moi %ss.",
            interval,
        )
        while not self.stop_event.wait(interval):
            try:
                logger.info("Doc lai tat ca cau hinh mail trong DB sau %ss.", interval)
                self.sync_from_database()
            except Exception as exc:
                logger.exception("Loi sync condition workers tu database: %s", exc)

    def join_all(self) -> None:
        """Cho tat ca worker hien tai ket thuc, dung cho --max-cycles khi test."""

        while True:
            with self.lock:
                workers = [managed.worker for managed in self.workers.values()]

            if not workers:
                return

            for worker in workers:
                worker.join(timeout=0.5)

            with self.lock:
                self.workers = {
                    config_id: managed
                    for config_id, managed in self.workers.items()
                    if managed.worker.is_alive()
                }

    def stop_all(self) -> None:
        """Stop tat ca worker va ngan sync loop tiep tuc."""

        self.stop_event.set()
        with self.lock:
            config_ids = list(self.workers)

        for config_id in config_ids:
            self.stop_worker(config_id)
