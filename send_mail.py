from __future__ import annotations

import logging
import sys

from cli import parse_args
from monitor import run_check_once, run_loop
from settings import load_env


def configure_output_encoding() -> None:
    """Dam bao console/log tren Windows in duoc tieng Viet tu database."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def configure_logging() -> None:
    """Cau hinh logging chung cho monitor va worker threads."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Ham chay chinh cua script."""

    configure_output_encoding()
    configure_logging()
    args = parse_args()
    args.loop = not args.once
    load_env()

    if args.once:
        run_check_once(args)
        return

    run_loop(args)


if __name__ == "__main__":
    main()
