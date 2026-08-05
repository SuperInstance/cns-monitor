"""Tests for CNS Monitor stats tracking."""

import pytest
import time
from pathlib import Path
from cns_monitor.stats import CNSStats
from cns_monitor.watcher import SignalEvent


_event_counter = [0]


def make_event(
    origin="lucineer-riker",
    intent="QUERY",
    priority="HIGH",
    direction="inbox",
    mtime=None,
):
    _event_counter[0] += 1
    return SignalEvent(
        filepath=Path(f"/tmp/test_{_event_counter[0]}.json"),
        filename=f"test_{_event_counter[0]}.json",
        direction=direction,
        origin_id=origin,
        intent=intent,
        priority=priority,
        file_mtime=mtime or time.time(),
    )


class TestCNSStats:
    def test_initial_state(self):
        stats = CNSStats()
        assert stats.total_signals == 0
        assert stats.signals_per_minute == 0.0
        assert stats.avg_latency_ms == 0.0
        assert stats.active_agents == []

    def test_record_increments_total(self):
        stats = CNSStats()
        stats.record(make_event())
        assert stats.total_signals == 1

    def test_intent_counting(self):
        stats = CNSStats()
        stats.record(make_event(intent="QUERY"))
        stats.record(make_event(intent="QUERY"))
        stats.record(make_event(intent="HANDSHAKE_COMPLETE"))
        assert stats.intent_counts["QUERY"] == 2
        assert stats.intent_counts["HANDSHAKE_COMPLETE"] == 1

    def test_priority_counting(self):
        stats = CNSStats()
        stats.record(make_event(priority="HIGH"))
        stats.record(make_event(priority="CRITICAL"))
        stats.record(make_event(priority="HIGH"))
        assert stats.priority_counts["HIGH"] == 2
        assert stats.priority_counts["CRITICAL"] == 1

    def test_agent_tracking(self):
        stats = CNSStats()
        stats.record(make_event(origin="wesley"))
        stats.record(make_event(origin="hermes-cns"))
        stats.record(make_event(origin="wesley"))
        assert stats.agent_signal_counts["wesley"] == 2
        assert stats.agent_signal_counts["hermes-cns"] == 1

    def test_active_agents_sorted(self):
        stats = CNSStats()
        stats.record(make_event(origin="riker"))
        stats.record(make_event(origin="wesley"))
        stats.record(make_event(origin="hermes"))
        assert stats.active_agents == ["hermes", "riker", "wesley"]

    def test_signals_per_minute_with_data(self):
        stats = CNSStats()
        now = time.time()
        for i in range(10):
            stats._recent_timestamps.append(now - 60 + i * 6)
        spm = stats.signals_per_minute
        assert spm > 0

    def test_latency_estimation(self):
        stats = CNSStats()
        base = time.time()
        inbox_event = make_event(origin="agent-a", direction="inbox", mtime=base)
        stats.record(inbox_event)
        outbox_event = make_event(origin="agent-b", direction="outbox", mtime=base + 5)
        stats.record(outbox_event)
        assert stats.avg_latency_ms > 0
        assert stats.avg_latency_ms == pytest.approx(5000, abs=100)

    def test_latency_ignored_if_too_long(self):
        stats = CNSStats()
        base = time.time()
        inbox_event = make_event(origin="agent-a", direction="inbox", mtime=base)
        stats.record(inbox_event)
        outbox_event = make_event(origin="agent-b", direction="outbox", mtime=base + 600)
        stats.record(outbox_event)
        assert stats.avg_latency_ms == 0.0

    def test_multiple_agents_multiple_events(self):
        stats = CNSStats()
        for agent in ["wesley", "riker", "hermes", "wesley", "riker"]:
            stats.record(make_event(origin=agent))
        assert stats.total_signals == 5
        assert len(stats.active_agents) == 3


class TestSignalEvent:
    def test_from_file_valid(self, tmp_path):
        import json
        packet = {
            "header": {
                "origin_id": "test-agent",
                "timestamp": "2026-08-05T01:00:00Z",
                "priority": "HIGH",
                "sequence_id": 1,
            },
            "body": {
                "intent": "QUERY",
                "payload": {"type": "signal", "data": {}},
            },
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(packet))
        event = SignalEvent.from_file(p, "inbox")
        assert event is not None
        assert event.origin_id == "test-agent"
        assert event.intent == "QUERY"
        assert event.priority == "HIGH"
        assert event.direction == "inbox"

    def test_from_file_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        event = SignalEvent.from_file(p, "inbox")
        assert event is None

    def test_from_file_missing_fields(self, tmp_path):
        p = tmp_path / "minimal.json"
        p.write_text("{}")
        event = SignalEvent.from_file(p, "inbox")
        assert event is not None
        assert event.origin_id == "?"
        assert event.intent == "?"


class TestCNSWatcher:
    def test_scan_finds_json(self, tmp_path):
        from cns_monitor.watcher import CNSWatcher
        import json

        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        packet = {
            "header": {"origin_id": "test", "timestamp": "2026-08-05T01:00:00Z",
                       "priority": "HIGH", "sequence_id": 1},
            "body": {"intent": "QUERY", "payload": {"type": "signal", "data": {}}},
        }
        (inbox / "signal_001.json").write_text(json.dumps(packet))

        watcher = CNSWatcher(inbox, outbox)
        events = watcher.scan_once()
        assert len(events) == 1
        assert events[0].origin_id == "test"

    def test_scan_dedupes(self, tmp_path):
        from cns_monitor.watcher import CNSWatcher
        import json

        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        packet = {
            "header": {"origin_id": "test", "timestamp": "2026-08-05T01:00:00Z",
                       "priority": "HIGH", "sequence_id": 1},
            "body": {"intent": "QUERY", "payload": {"type": "signal", "data": {}}},
        }
        (inbox / "signal_001.json").write_text(json.dumps(packet))

        watcher = CNSWatcher(inbox, outbox)
        assert len(watcher.scan_once()) == 1
        assert len(watcher.scan_once()) == 0  # already seen

    def test_scan_ignores_non_json(self, tmp_path):
        from cns_monitor.watcher import CNSWatcher

        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        (inbox / "readme.txt").write_text("not a signal")

        watcher = CNSWatcher(inbox, outbox)
        assert watcher.scan_once() == []

    def test_scan_handles_missing_dirs(self, tmp_path):
        from cns_monitor.watcher import CNSWatcher

        watcher = CNSWatcher(tmp_path / "nonexistent_in", tmp_path / "nonexistent_out")
        assert watcher.scan_once() == []
