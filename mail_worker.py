from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread

from database import save_mail_history
from mailer import send_mail


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailJob:
    """Du lieu can thiet de mail worker gui mot email canh bao."""

    config_id: str | None
    mail_config: dict
    subject: str
    body: str
    html_body: str | None = None


def format_smtp_error(error) -> str:
    """Chuyen loi SMTP ve chuoi an toan, ke ca khi server tra ve bytes."""

    if isinstance(error, bytes):
        return error.decode(errors="ignore")

    return str(error)


class MailWorker:
    """Worker thread nhan job tu queue va gui email trong background."""

    def __init__(self) -> None:
        self._queue: Queue[MailJob | None] = Queue()
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._errors: list[Exception] = []

    @property
    def has_errors(self) -> bool:
        """Cho biet worker da gap loi gui mail nao trong vong doi hien tai."""

        return bool(self._errors)

    def start(self) -> None:
        """Khoi dong worker thread neu chua chay."""

        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="mail-worker", daemon=True)
        self._thread.start()

    def enqueue(self, job: MailJob) -> None:
        """Dua mot job gui mail vao hang doi."""

        self.start()
        self._queue.put(job)

    def wait_until_idle(self) -> None:
        """Cho den khi queue da xu ly het cac job hien co."""

        self._queue.join()

    def stop(self) -> None:
        """Dung worker sau khi xu ly het cac job dang cho."""

        if self._thread is None:
            return

        if self._thread.is_alive():
            self._stop_event.set()
            self._queue.put(None)
            self._queue.join()
            self._thread.join()

        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                job = self._queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                if job is None:
                    continue

                self._send_job(job)
            finally:
                self._queue.task_done()

    def _send_job(self, job: MailJob) -> None:
        try:
            receiver_emails = send_mail(job.mail_config, job.body, job.subject, job.html_body)
        except smtplib.SMTPAuthenticationError as exc:
            self._errors.append(exc)
            logger.error("\nLoi gui mail: Dang nhap SMTP that bai.")
            logger.error("Server SMTP tu choi sender_email hoac sender_password.")
            logger.error("Chi tiet SMTP: %s %s", exc.smtp_code, format_smtp_error(exc.smtp_error))
            self._record_mail_history(job, status=False)
            return
        except (smtplib.SMTPException, OSError, RuntimeError) as exc:
            self._errors.append(exc)
            logger.exception("\nLoi gui mail: Khong gui duoc email qua SMTP. Chi tiet: %s", exc)
            self._record_mail_history(job, status=False)
            return
        except Exception as exc:
            self._errors.append(exc)
            logger.exception("\nLoi gui mail khong mong doi trong mail worker. Chi tiet: %s", exc)
            self._record_mail_history(job, status=False)
            return

        self._record_mail_history(job, status=True)
        logger.info("Da gui mail thanh cong toi: %s", ", ".join(receiver_emails))

    def _record_mail_history(self, job: MailJob, status: bool) -> None:
        try:
            history_id = save_mail_history(job.config_id, job.subject, job.body, status=status)
        except Exception as exc:
            if status:
                logger.exception("\nDa gui mail thanh cong nhung luu lich su mail vao mailhistories that bai.")
            else:
                logger.exception("\nGui mail that bai va luu lich su mail vao mailhistories cung that bai.")
            logger.exception("Chi tiet: %s", exc)
            return

        history_status = "thanh cong" if status else "that bai"
        logger.info("Da luu lich su mail (%s) vao mailhistories: %s", history_status, history_id)
