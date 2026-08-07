"""Additional edge case tests for CNSStats tracking."""

import time
from pathlib import Path
from collections import Counter

from cns_monitor.stats import CNSStats
from cns_monitor.watcher import SignalEvent


def make_signal(direction="inbox", origin="agent-a", intent="HEARTBEAT",
                priority="LOW", mtime=None):
    """Create a minimal SignalEvent for testing."""
    return SignalEvent(
        filepath=Path(f"/tmp/test_{int(time.time()*1000)}.json"),
        filename=f"test_{int(time.time()*1000)}.json",
        direction=direction,
        origin_id=origin,
        timestamp="2026-08-07T00:00:00Z",
        priority=priority,
        sequence_id=1,
        intent=intent,
        payload_type="test",
        raw={},
        file_mtime=mtime or time.time(),
    )


class TestCNSStatsEdgeCases:
    def test_empty_stats(self):
        stats = CNSStats()
        assert stats.total_signals == 0
        assert stats.signals_per_minute == 0.0
        assert stats.avg_latency_ms == 0.0
        assert stats.active_agents == []

    def test_single_signal(self):
        stats = CNSStats()
        stats.record(make_signal())
        assert stats.total_signals == 1
        assert "agent-a" in stats.active_agents

    def test_signals_per_minute_calculation(self):
        stats = CNSStats()
        now = time.time()
        # Record signals at different times
        for i in range(10):
            event = make_signal(mtime=now - (10 - i))
            stats._recent_timestamps.append(now - (10 - i))
        spm = stats.signals_per_minute
        assert spm > 0

    def test_latency_tracking(self):
        stats = CNSStats()
        now = time.time()
        # Inbox signal first
        inbox = make_signal(direction="inbox", origin="agent-a", mtime=now - 5)
        stats.record(inbox)
        # Outbox signal from different agent 2 seconds later
        outbox = make_signal(direction="outbox", origin="agent-b", mtime=now - 3)
        stats.record(outbox)
        assert len(stats._latencies) == 1
        assert 1.5 < stats._latencies[0] < 2.5  # ~2 seconds

    def test_latency_ignored_for_same_origin(self):
        stats = CNSStats()
        now = time.time()
        inbox = make_signal(direction="inbox", origin="agent-a", mtime=now - 5)
        stats.record(inbox)
        outbox = make_signal(direction="outbox", origin="agent-a", mtime=now - 3)
        stats.record(outbox)
        assert len(stats._latencies) == 0  # Same origin, no latency tracked

    def test_latency_window_limit(self):
        """Latency > 300s should be ignored."""
        stats = CNSStats()
        now = time.time()
        inbox = make_signal(direction="inbox", origin="agent-a", mtime=now - 400)
        stats.record(inbox)
        outbox = make_signal(direction="outbox", origin="agent-b", mtime=now)
        stats.record(outbox)
        assert len(stats._latencies) == 0

    def test_intent_distribution(self):
        stats = CNSStats()
        for intent in ["HEARTBEAT", "HEARTBEAT", "QUERY", "REPLY"]:
            stats.record(make_signal(intent=intent))
        assert stats.intent_counts["HEARTBEAT"] == 2
        assert stats.intent_counts["QUERY"] == 1
        assert stats.intent_counts["REPLY"] == 1

    def test_priority_distribution(self):
        stats = CNSStats()
        for prio in ["LOW", "LOW", "HIGH", "CRITICAL"]:
            stats.record(make_signal(priority=prio))
        assert stats.priority_counts["LOW"] == 2
        assert stats.priority_counts["CRITICAL"] == 1

    def test_active_agents_sorted(self):
        stats = CNSStats()
        stats.record(make_signal(origin="charlie"))
        stats.record(make_signal(origin="alpha"))
        stats.record(make_signal(origin="bravo"))
        assert stats.active_agents == ["alpha", "bravo", "charlie"]

    def test_agent_signal_counts(self):
        stats = CNSStats()
        for _ in range(5):
            stats.record(make_signal(origin="prolific"))
        stats.record(make_signal(origin="quiet"))
        assert stats.agent_signal_counts["prolific"] == 5
        assert stats.agent_signal_counts["quiet"] == 1

    def test_recent_timestamps_capped(self):
        """_recent_timestamps should be capped at 100 entries."""
        stats = CNSStats()
        for i in range(150):
            stats._recent_timestamps.append(float(i))
        assert len(stats._recent_timestamps) == 100

    def test_latencies_capped(self):
        """_latencies should be capped at 50 entries."""
        stats = CNSStats()
        for i in range(100):
            stats._latencies.append(float(i))
        assert len(stats._latencies) == 50

    def test_zero_elapsed_spm(self):
        """If all timestamps are identical, spm should be 0."""
        stats = CNSStats()
        t = time.time()
        stats._recent_timestamps.append(t)
        stats._recent_timestamps.append(t)
        assert stats.signals_per_minute == 0.0

    def test_single_timestamp_spm(self):
        """With only one timestamp, spm should be 0."""
        stats = CNSStats()
        stats._recent_timestamps.append(time.time())
        assert stats.signals_per_minute == 0.0
