from __future__ import annotations

import logging
from threading import Event, Thread

from mail_worker import MailWorker
from monitor import get_fallback_interval, get_thread_name, run_config_check_once


logger = logging.getLogger(__name__)


class MailConditionWorker(Thread):
    """Worker thread kiem tra dieu kien canh bao cho mot config duy nhat."""

    def __init__(self, args, config: dict, mail_worker: MailWorker) -> None:
        self.config_id = str(config.get("Id") or "")
        self.config = config
        self.mail_worker = mail_worker
        self.stop_event = Event()
        self.is_alerting = False
        self.last_sent_at: dict[str, float] = {}
        self.active_alert_keys: set[str] = set()
        self.cycle_number = 0
        super().__init__(name=get_thread_name(config), daemon=True)
        self.args = args

    def get_current_value(self) -> None:
        """Hook ro nghia nghiep vu: gia tri moi nhat duoc doc trong run_config_check_once."""

        return None

    def check_condition(self) -> float:
        """Chay mot chu ky doc DB, check condition va dua mail vao queue neu can."""

        self.get_current_value()
        self.cycle_number += 1
        check_interval = run_config_check_once(
            self.args,
            self.config,
            self.last_sent_at,
            self.cycle_number,
            self.mail_worker,
            self.active_alert_keys,
        )
        self.is_alerting = bool(self.active_alert_keys)
        return check_interval

    def handle_alert(self) -> None:
        """Hook mo rong neu can them xu ly alert rieng ngoai mail queue hien tai."""

        self.is_alerting = bool(self.active_alert_keys)

    def stop(self) -> None:
        """Yeu cau worker dung an toan o lan wait/vong lap gan nhat."""

        self.stop_event.set()

    def run(self) -> None:
        logger.info(
            "Khoi dong condition worker config_id=%s, name=%s.",
            self.config_id,
            self.config.get("Name"),
        )

        while not self.stop_event.is_set():
            try:
                check_interval = self.check_condition()
                self.handle_alert()
            except Exception as exc:
                check_interval = get_fallback_interval(self.args)
                logger.exception(
                    "Loi condition worker config_id=%s, name=%s: %s",
                    self.config_id,
                    self.config.get("Name"),
                    exc,
                )

            if self.args.max_cycles is not None and self.cycle_number >= self.args.max_cycles:
                logger.info(
                    "%s: da chay du %s chu ky. Dung worker.",
                    self.config.get("Name"),
                    self.args.max_cycles,
                )
                break

            logger.info(
                "%s: cho %ss truoc chu ky tiep theo...",
                self.config.get("Name"),
                check_interval,
            )
            self.stop_event.wait(check_interval)

        logger.info(
            "Dung condition worker config_id=%s, name=%s.",
            self.config_id,
            self.config.get("Name"),
        )
