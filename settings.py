from __future__ import annotations

import os
from pathlib import Path


# Lay duong dan thu muc hien tai cua project.
BASE_DIR = Path(__file__).resolve().parent

# File .env nam cung thu muc voi send_mail.py, dung de luu thong tin ket noi DB.
ENV_PATH = BASE_DIR / ".env"

# Sau 60 phut doc lai toan bo cau hinh mail/sensor mot lan.
DEFAULT_MAIL_CONFIG_RELOAD_INTERVAL_SECONDS = 60 * 60


def load_env(path: Path = ENV_PATH) -> None:
    """Doc file .env va dua cac bien cau hinh vao os.environ."""

    if not path.exists():
        raise FileNotFoundError(f"Missing .env file: {path}")

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_db_config() -> dict[str, object]:
    """Lay cau hinh ket noi MySQL tu cac bien trong file .env."""

    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", ""),
        "charset": os.getenv("DB_CHARSET", "utf8mb4"),
    }
