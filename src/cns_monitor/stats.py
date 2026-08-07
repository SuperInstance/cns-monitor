"""Tracks signal statistics: frequency, latency, intent distribution, active agents."""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque

from .watcher import SignalEvent


@dataclass
class CNSStats:
    """Aggregated statistics for observed CNS traffic."""

    total_signals: int = 0
    intent_counts: Counter = field(default_factory=Counter)
    priority_counts: Counter = field(default_factory=Counter)
    agent_signal_counts: Counter = field(default_factory=Counter)
    _recent_timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    _origin_timestamps: dict[str, float] = field(default_factory=dict)
    _latencies: Deque[float] = field(default_factory=lambda: deque(maxlen=50))

    def record(self, event: SignalEvent) -> None:
        self.total_signals += 1
        self.intent_counts[event.intent] += 1
        self.priority_counts[event.priority] += 1
        self.agent_signal_counts[event.origin_id] += 1

        # Track response latency: when we see an outbox signal shortly after
        # an inbox signal from a different origin, estimate latency
        now = time.time()
        self._recent_timestamps.append(now)

        if event.direction == "inbox":
            self._origin_timestamps[event.origin_id] = event.file_mtime

        # Detect direction pairing for latency estimate
        if event.direction == "outbox":
            # Find the most recent inbox origin that isn't the outbox sender
            for origin, ts in list(self._origin_timestamps.items()):
                if origin != event.origin_id and event.file_mtime > ts:
                    latency = event.file_mtime - ts
                    if 0 < latency < 300:  # sane window (5 min max)
                        self._latencies.append(latency)
                    break

    @property
    def signals_per_minute(self) -> float:
        if len(self._recent_timestamps) < 2:
            return 0.0
        elapsed = self._recent_timestamps[-1] - self._recent_timestamps[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._recent_timestamps) / elapsed) * 60.0

    @property
    def avg_latency_ms(self) -> float:
        if not self._latencies:
            return 0.0
        return (sum(self._latencies) / len(self._latencies)) * 1000.0

    @property
    def active_agents(self) -> list[str]:
        return sorted(self.agent_signal_counts.keys())
