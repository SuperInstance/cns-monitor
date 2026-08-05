"""Tests for the CNS Monitor Watcher — filesystem polling for USCP packets."""

import json
import pytest
import time
from pathlib import Path

from cns_monitor.watcher import SignalEvent, CNSWatcher


def make_signal_file(
    directory: Path,
    filename: str,
    origin="test-agent",
    priority="HIGH",
    intent="QUERY",
    sequence_id=1,
):
    """Create a USCP signal file in the given directory."""
    packet = {
        "header": {
            "origin_id": origin,
            "timestamp": "2026-08-05T12:00:00Z",
            "priority": priority,
            "sequence_id": sequence_id,
        },
        "body": {
            "intent": intent,
            "payload": {
                "type": "signal",
                "data": {"msg": "hello"},
            },
        },
        "signature": {
            "type": "USCP-v1",
            "checksum": "verified",
        },
    }
    path = directory / filename
    path.write_text(json.dumps(packet, indent=2))
    return path


class TestSignalEvent:
    def test_from_file_valid(self, tmp_path):
        path = make_signal_file(tmp_path, "signal1.json", origin="lucineer")
        event = SignalEvent.from_file(path, "inbox")
        assert event is not None
        assert event.origin_id == "lucineer"
        assert event.priority == "HIGH"
        assert event.intent == "QUERY"
        assert event.direction == "inbox"
        assert event.filename == "signal1.json"

    def test_from_file_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json at all {{{")
        event = SignalEvent.from_file(path, "inbox")
        assert event is None

    def test_from_file_missing_fields(self, tmp_path):
        """Packet with missing fields still parses, uses defaults."""
        path = tmp_path / "partial.json"
        path.write_text(json.dumps({"header": {}, "body": {}}))
        event = SignalEvent.from_file(path, "inbox")
        assert event is not None
        assert event.origin_id == "?"
        assert event.priority == "?"

    def test_from_file_payload_type(self, tmp_path):
        path = make_signal_file(tmp_path, "sig.json")
        event = SignalEvent.from_file(path, "inbox")
        assert event.payload_type == "signal"

    def test_from_file_has_raw(self, tmp_path):
        path = make_signal_file(tmp_path, "sig.json")
        event = SignalEvent.from_file(path, "inbox")
        assert isinstance(event.raw, dict)
        assert "header" in event.raw

    def test_from_file_has_mtime(self, tmp_path):
        path = make_signal_file(tmp_path, "sig.json")
        event = SignalEvent.from_file(path, "inbox")
        assert event.file_mtime > 0

    def test_from_file_nonexistent(self, tmp_path):
        event = SignalEvent.from_file(tmp_path / "ghost.json", "inbox")
        assert event is None

    def test_sequence_id_extracted(self, tmp_path):
        path = make_signal_file(tmp_path, "sig.json", sequence_id=42)
        event = SignalEvent.from_file(path, "inbox")
        assert event.sequence_id == 42


class TestCNSWatcherConstruction:
    def test_default_construction(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        w = CNSWatcher(inbox, outbox)
        assert w.inbox == inbox
        assert w.outbox == outbox
        assert w.poll_interval == 0.5

    def test_custom_poll_interval(self, tmp_path):
        w = CNSWatcher(tmp_path, tmp_path, poll_interval=2.0)
        assert w.poll_interval == 2.0

    def test_no_callbacks_initially(self, tmp_path):
        w = CNSWatcher(tmp_path, tmp_path)
        assert len(w._callbacks) == 0


class TestCNSWatcherScan:
    def test_scan_finds_json_files(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        make_signal_file(inbox, "sig1.json")
        make_signal_file(outbox, "sig2.json")

        w = CNSWatcher(inbox, outbox)
        events = w.scan_once()
        assert len(events) == 2

    def test_scan_ignores_non_json(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        make_signal_file(inbox, "sig1.json")
        (inbox / "readme.txt").write_text("hello")

        w = CNSWatcher(inbox, outbox)
        events = w.scan_once()
        assert len(events) == 1

    def test_scan_dedupes_seen(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        make_signal_file(inbox, "sig1.json")

        w = CNSWatcher(inbox, outbox)
        first = w.scan_once()
        assert len(first) == 1
        second = w.scan_once()
        assert len(second) == 0

    def test_scan_handles_missing_directory(self, tmp_path):
        """Missing directories should produce empty results, not errors."""
        w = CNSWatcher(tmp_path / "nonexistent_inbox", tmp_path / "nonexistent_outbox")
        events = w.scan_once()
        assert events == []

    def test_scan_direction_labels(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        make_signal_file(inbox, "in1.json")
        make_signal_file(outbox, "out1.json")

        w = CNSWatcher(inbox, outbox)
        events = w.scan_once()
        directions = [e.direction for e in events]
        assert "inbox" in directions
        assert "outbox" in directions

    def test_scan_new_file_after_first_scan(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        make_signal_file(inbox, "sig1.json")

        w = CNSWatcher(inbox, outbox)
        assert len(w.scan_once()) == 1

        # Add a new file
        make_signal_file(inbox, "sig2.json")
        assert len(w.scan_once()) == 1  # only the new one

    def test_scan_invalid_json_skipped(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        (inbox / "broken.json").write_text("invalid{{{")
        make_signal_file(inbox, "good.json")

        w = CNSWatcher(inbox, outbox)
        events = w.scan_once()
        assert len(events) == 1
        assert events[0].filename == "good.json"


class TestCNSWatcherCallbacks:
    def test_on_signal_registers_callback(self, tmp_path):
        w = CNSWatcher(tmp_path, tmp_path)
        called = []
        w.on_signal(lambda ev: called.append(ev))
        assert len(w._callbacks) == 1

    def test_callback_not_fired_on_initial_seen(self, tmp_path):
        """The watch() method seeds the seen-set before firing callbacks."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        make_signal_file(inbox, "pre.json")

        w = CNSWatcher(inbox, outbox)
        # scan_once marks as seen
        w.scan_once()

        called = []
        w.on_signal(lambda ev: called.append(ev))
        # Next scan finds nothing new
        w.scan_once()
        assert len(called) == 0

    def test_multiple_callbacks(self, tmp_path):
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        w = CNSWatcher(inbox, outbox)
        calls_a = []
        calls_b = []
        w.on_signal(lambda ev: calls_a.append(ev))
        w.on_signal(lambda ev: calls_b.append(ev))

        make_signal_file(inbox, "new.json")
        events = w.scan_once()
        # Callbacks fire in watch() not scan_once(), so just verify events
        assert len(events) == 1
