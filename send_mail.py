from __future__ import annotations

import sys

from cli import parse_args
from monitor import run_check_once, run_loop
from settings import load_env


def configure_output_encoding() -> None:
    """Dam bao console/log tren Windows in duoc tieng Viet tu database."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    """Ham chay chinh cua script."""

    configure_output_encoding()
    args = parse_args()
    load_env()

    if args.loop:
        run_loop(args)
        return

    run_check_once(args)


if __name__ == "__main__":
    main()
