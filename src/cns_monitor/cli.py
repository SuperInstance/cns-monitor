"""CLI entry point for cns-monitor."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__
from .display import CNSDisplay
from .stats import CNSStats
from .watcher import CNSWatcher


def default_inbox() -> str:
    return os.path.expanduser("~/.hermes/cns_inbox/")


def default_outbox() -> str:
    return os.path.expanduser("~/.hermes/cns_outbox/")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cns-monitor",
        description="Real-time CNS traffic monitor — htop for USCP signals.",
    )
    parser.add_argument(
        "--inbox",
        default=default_inbox(),
        help="Path to cns_inbox directory (default: ~/.hermes/cns_inbox/)",
    )
    parser.add_argument(
        "--outbox",
        default=default_outbox(),
        help="Path to cns_outbox directory (default: ~/.hermes/cns_outbox/)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Poll interval in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Scan once and print results, then exit (non-live mode)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cns-monitor {__version__}",
    )

    args = parser.parse_args()

    inbox = str(Path(args.inbox))
    outbox = str(Path(args.outbox))

    watcher = CNSWatcher(inbox, outbox, poll_interval=args.interval)
    stats = CNSStats()
    display = CNSDisplay()

    def on_signal(event):
        stats.record(event)
        display.add_event(event)
        if args.once:
            display.print_event(event)

    watcher.on_signal(on_signal)

    if args.once:
        events = watcher.scan_once()
        if not events:
            print("No signals detected.")
        sys.exit(0)

    # Live mode
    from rich.live import Live
    from rich.console import Console

    console = Console()
    console.clear()

    with Live(display.render(stats, inbox, outbox), console=console, refresh_per_second=4) as live:
        def on_signal_live(event):
            stats.record(event)
            display.add_event(event)
            live.update(display.render(stats, inbox, outbox))

        watcher._callbacks = [on_signal_live]
        watcher.watch()


if __name__ == "__main__":
    main()
