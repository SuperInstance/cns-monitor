"""Filesystem watcher for USCP JSON packets in CNS inbox/outbox directories.

Uses polling for maximum portability — no native dependencies required.
Falls back gracefully on missing directories and recovers when they appear.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class SignalEvent:
    """A single observed USCP packet."""

    filepath: Path
    filename: str
    direction: str  # "inbox" or "outbox"
    origin_id: str = "?"
    timestamp: str = "?"
    priority: str = "?"
    sequence_id: Optional[int] = None
    intent: str = "?"
    payload_type: str = "?"
    raw: dict = field(default_factory=dict)
    file_mtime: float = 0.0

    @classmethod
    def from_file(cls, filepath: Path, direction: str) -> Optional["SignalEvent"]:
        """Parse a JSON file into a SignalEvent. Returns None on parse failure."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        # Support both USCP (header/body/signature) and flat packet formats
        if isinstance(data.get("header"), dict):
            # USCP format
            header = data.get("header", {})
            body = data.get("body", {}) if isinstance(data.get("body"), dict) else {}
            payload = body.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            origin_id = header.get("origin_id", "?")
            timestamp = header.get("timestamp", "?")
            if isinstance(timestamp, (int, float)):
                from datetime import datetime, timezone
                timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            priority = header.get("priority", "?")
            sequence_id = header.get("sequence_id")
            intent = body.get("intent", "?")
            payload_type = payload.get("type", "?")
        else:
            # Flat packet format (lucineer pulse, hermes task, etc.)
            origin_id = data.get("from", "?")
            timestamp = data.get("timestamp", "?")
            if isinstance(timestamp, (int, float)):
                from datetime import datetime, timezone
                timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            priority = data.get("priority", "?")
            sequence_id = data.get("pulse_number") or data.get("sequence_id")
            intent = data.get("type", "?")
            payload = data.get("content", {})
            if not isinstance(payload, dict):
                payload = {}
            payload_type = payload.get("signal", data.get("type", "?"))

        return cls(
            filepath=filepath,
            filename=filepath.name,
            direction=direction,
            origin_id=origin_id,
            timestamp=timestamp,
            priority=priority,
            sequence_id=sequence_id,
            intent=intent,
            payload_type=payload_type,
            raw=data,
            file_mtime=filepath.stat().st_mtime,
        )


class CNSWatcher:
    """Polls inbox and outbox directories for new USCP packets."""

    def __init__(
        self,
        inbox_path: str | Path,
        outbox_path: str | Path,
        poll_interval: float = 0.5,
    ) -> None:
        self.inbox = Path(inbox_path)
        self.outbox = Path(outbox_path)
        self.poll_interval = poll_interval
        self._seen: set[str] = set()
        self._callbacks: list[Callable[[SignalEvent], None]] = []

    def on_signal(self, callback: Callable[[SignalEvent], None]) -> None:
        """Register a callback fired for each new signal detected."""
        self._callbacks.append(callback)

    def _scan_dir(self, directory: Path, direction: str) -> list[SignalEvent]:
        """Scan a directory for JSON files we haven't seen yet."""
        events: list[SignalEvent] = []
        if not directory.is_dir():
            return events

        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.suffix != ".json":
                continue
            key = f"{direction}:{entry.name}"
            if key in self._seen:
                continue
            event = SignalEvent.from_file(entry, direction)
            if event:
                self._seen.add(key)
                events.append(event)
        return events

    def scan_once(self) -> list[SignalEvent]:
        """Do a single scan of both directories and return new events."""
        events = []
        events.extend(self._scan_dir(self.inbox, "inbox"))
        events.extend(self._scan_dir(self.outbox, "outbox"))
        return events

    def watch(self) -> None:
        """Block forever, polling for new signals and firing callbacks."""
        # Seed seen-set so we don't fire for pre-existing files on startup
        for ev in self.scan_once():
            pass  # mark as seen, don't emit

        while True:
            events = self.scan_once()
            for event in events:
                for cb in self._callbacks:
                    cb(event)
            time.sleep(self.poll_interval)
