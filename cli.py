from __future__ import annotations

import argparse

from settings import DEFAULT_MAIL_CONFIG_RELOAD_INTERVAL_SECONDS


def parse_args():
    """Doc tham so dong lenh khi chay script."""

    parser = argparse.ArgumentParser(description="Gui mail tu cau hinh InstanceConfigJsonMail.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi in cau hinh va noi dung mail, khong gui mail that.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Chay lien tuc. Day la mac dinh khi khong truyen --once.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Chi kiem tra mot lan roi thoat.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        help="So giay nghi giua cac chu ky. Neu khong truyen se dung time_threshold trong DB.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=300,
        help="So giay toi thieu truoc khi gui lai mail cho cung mot tag dang vuot nguong.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        help="So chu ky toi da khi chay loop, dung de test. Bo trong de chay lien tuc.",
    )
    parser.add_argument(
        "--config-reload-interval",
        type=float,
        default=DEFAULT_MAIL_CONFIG_RELOAD_INTERVAL_SECONDS,
        help=(
            "So giay giua cac lan doc lai tat ca cau hinh mail trong DB. "
            f"Mac dinh {DEFAULT_MAIL_CONFIG_RELOAD_INTERVAL_SECONDS}s (60 phut)."
        ),
    )
    parser.add_argument(
        "--verbose-json",
        action="store_true",
        help="In day du JSON cau hinh/tag/live moi chu ky.",
    )
    parser.add_argument(
        "--subject",
        help="Tieu de mail tuy chinh. Neu khong truyen se lay subject trong database.",
    )
    parser.add_argument(
        "--body",
        help="Noi dung mail tuy chinh. Neu khong truyen se tu tao noi dung tu sensor config.",
    )
    return parser.parse_args()
