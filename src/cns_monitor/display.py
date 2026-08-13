"""Rich terminal display for real-time CNS signal flow."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .stats import CNSStats
from .watcher import SignalEvent

PRIORITY_COLORS = {
    "CRITICAL": "bold red",
    "HIGH": "yellow",
    "MEDIUM": "green",
    "LOW": "dim white",
}

DIRECTION_ICONS = {
    "inbox": "→",
    "outbox": "←",
}


class CNSDisplay:
    """Manages the rich terminal UI for CNS traffic."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()
        self._recent_events: list[SignalEvent] = []

    def add_event(self, event: SignalEvent) -> None:
        self._recent_events.append(event)
        if len(self._recent_events) > 50:
            self._recent_events = self._recent_events[-50:]

    def render(self, stats: CNSStats, inbox_path: str, outbox_path: str) -> Panel:
        layout = Layout()

        # Header
        now = datetime.now().strftime("%H:%M:%S")
        header = Text(
            f"📡 CNS Monitor  |  {now}  |  inbox: {inbox_path}  |  outbox: {outbox_path}",
            style="bold cyan",
        )

        # Stats table
        stats_table = Table(show_header=True, header_style="bold magenta", expand=True)
        stats_table.add_column("Metric", style="cyan", width=24)
        stats_table.add_column("Value", style="white")
        stats_table.add_row("Total signals", str(stats.total_signals))
        stats_table.add_row("Signals/min", f"{stats.signals_per_minute:.1f}")
        stats_table.add_row("Avg latency", f"{stats.avg_latency_ms:.0f}ms")
        stats_table.add_row("Active agents", ", ".join(stats.active_agents) or "—")

        # Intent distribution
        intent_table = Table(show_header=True, header_style="bold blue", expand=True)
        intent_table.add_column("Intent", style="white")
        intent_table.add_column("Count", justify="right", style="cyan")
        for intent, count in stats.intent_counts.most_common(10):
            intent_table.add_row(intent, str(count))
        if not stats.intent_counts:
            intent_table.add_row("—", "0")

        # Signal feed
        feed_table = Table(show_header=True, header_style="bold green", expand=True)
        feed_table.add_column("T", width=8)
        feed_table.add_column("Dir", width=4)
        feed_table.add_column("Origin", width=18)
        feed_table.add_column("Intent", width=22)
        feed_table.add_column("Pri", width=9)
        feed_table.add_column("Seq", width=5)

        for ev in reversed(self._recent_events[-20:]):
            ts_short = ev.timestamp[11:19] if len(ev.timestamp) >= 19 else ev.timestamp[:8]
            icon = DIRECTION_ICONS.get(ev.direction, "?")
            pri_style = PRIORITY_COLORS.get(ev.priority, "white")
            seq = str(ev.sequence_id) if ev.sequence_id is not None else "—"
            feed_table.add_row(
                ts_short,
                Text(icon, style="bold"),
                ev.origin_id[:18],
                ev.intent[:22],
                Text(ev.priority, style=pri_style),
                seq,
            )

        if not self._recent_events:
            feed_table.add_row("—", "—", "—", "—", "—", "—")

        # Combine into layout
        top_row = Table.grid(expand=True)
        top_row.add_column(ratio=1)
        top_row.add_column(ratio=1)
        top_row.add_row(stats_table, intent_table)

        body = Table.grid(expand=True)
        body.add_row(top_row)
        body.add_row(Panel(feed_table, title="[bold]Signal Feed[/]", border_style="green"))

        return Panel(
            body,
            title=header,
            border_style="cyan",
            subtitle=f"[dim]{stats.total_signals} signals observed[/]",
        )

    def print_event(self, event: SignalEvent) -> None:
        """Print a single event as a one-liner (for non-live mode)."""
        ts_raw = event.timestamp
        if isinstance(ts_raw, (int, float)):
            from datetime import datetime, timezone
            ts_short = datetime.fromtimestamp(ts_raw, tz=timezone.utc).strftime("%H:%M:%S")
        elif isinstance(ts_raw, str) and len(ts_raw) >= 19:
            ts_short = ts_raw[11:19]
        elif isinstance(ts_raw, str):
            ts_short = ts_raw[:8]
        else:
            ts_short = "?"
        icon = DIRECTION_ICONS.get(event.direction, "?")
        pri_style = PRIORITY_COLORS.get(event.priority, "white")
        self.console.print(
            f"[dim]{ts_short}[/] "
            f"[bold]{icon}[/] "
            f"[cyan]{event.origin_id:<18}[/] "
            f"[white]{event.intent:<22}[/] "
            f"[{pri_style}]{event.priority:<8}[/] "
            f"[dim]seq={event.sequence_id}[/]"
        )
