"""Tests for CNSWatcher watch() method and SignalEvent edge cases."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cns_monitor.watcher import CNSWatcher, SignalEvent


def make_packet(origin="hermes", priority="HIGH", intent="QUERY", seq=1):
    return {
        "header": {
            "origin_id": origin,
            "timestamp": "2026-08-06T09:00:00Z",
            "priority": priority,
            "sequence_id": seq,
            "packet_id": f"pkt-{seq}",
        },
        "body": {"intent": intent, "payload": {"msg": "test"}},
        "signature": {"type": "sha256", "checksum": "abc"},
    }


class TestWatchMethod:
    def test_watch_fires_callback_for_new_file(self, tmp_path):
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        watcher = CNSWatcher(str(inbox), str(outbox), poll_interval=0.05)
        callback_calls = []
        watcher.on_signal(lambda ev: callback_calls.append(ev))

        # Write the file on the first sleep call (after seeding)
        packet = make_packet()
        sleep_count = [0]
        def write_then_stop(seconds):
            sleep_count[0] += 1
            if sleep_count[0] == 1:
                # Write file AFTER seed scan but BEFORE next scan
                (inbox / "sig.uscp.json").write_text(json.dumps(packet))
            elif sleep_count[0] >= 3:
                raise KeyboardInterrupt

        with patch("cns_monitor.watcher.time.sleep", side_effect=write_then_stop):
            try:
                watcher.watch()
            except KeyboardInterrupt:
                pass

        assert len(callback_calls) >= 1
        assert callback_calls[0].origin_id == "hermes"

    def test_watch_does_not_fire_for_pre_existing(self, tmp_path):
        """Pre-existing files should be seeded and NOT trigger callbacks."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        packet = make_packet()
        (inbox / "old.uscp.json").write_text(json.dumps(packet))

        watcher = CNSWatcher(str(inbox), str(outbox), poll_interval=0.05)
        callback_calls = []
        watcher.on_signal(lambda ev: callback_calls.append(ev))

        call_count = [0]
        def stop_after(count=3):
            call_count[0] += 1
            if call_count[0] >= count:
                raise KeyboardInterrupt

        with patch("cns_monitor.watcher.time.sleep", side_effect=lambda s: stop_after(3)):
            try:
                watcher.watch()
            except KeyboardInterrupt:
                pass

        # Pre-existing file should NOT trigger callback
        assert len(callback_calls) == 0

    def test_watch_multiple_callbacks(self, tmp_path):
        """Multiple callbacks should all fire."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        watcher = CNSWatcher(str(inbox), str(outbox), poll_interval=0.05)
        calls1 = []
        calls2 = []
        watcher.on_signal(lambda ev: calls1.append(ev))
        watcher.on_signal(lambda ev: calls2.append(ev))

        packet = make_packet()
        sleep_count = [0]
        def write_then_stop(seconds):
            sleep_count[0] += 1
            if sleep_count[0] == 1:
                (inbox / "sig.uscp.json").write_text(json.dumps(packet))
            elif sleep_count[0] >= 3:
                raise KeyboardInterrupt

        with patch("cns_monitor.watcher.time.sleep", side_effect=write_then_stop):
            try:
                watcher.watch()
            except KeyboardInterrupt:
                pass

        assert len(calls1) >= 1
        assert len(calls2) >= 1


class TestSignalEventEdgeCases:
    def test_from_file_corrupt_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = SignalEvent.from_file(f, "inbox")
        assert result is None

    def test_from_file_missing(self, tmp_path):
        f = tmp_path / "nonexistent.json"
        result = SignalEvent.from_file(f, "inbox")
        assert result is None

    def test_from_file_partial_header(self, tmp_path):
        """Missing header fields should produce defaults."""
        f = tmp_path / "partial.json"
        f.write_text(json.dumps({"body": {"intent": "QUERY"}}))
        result = SignalEvent.from_file(f, "inbox")
        assert result is not None
        assert result.origin_id == "?"
        assert result.priority == "?"

    def test_from_file_empty_dict(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("{}")
        result = SignalEvent.from_file(f, "inbox")
        assert result is not None
        assert result.origin_id == "?"

    def test_from_file_with_all_fields(self, tmp_path):
        f = tmp_path / "full.json"
        packet = make_packet(origin="alice", priority="CRITICAL", intent="ALERT", seq=42)
        f.write_text(json.dumps(packet))
        result = SignalEvent.from_file(f, "outbox")
        assert result is not None
        assert result.origin_id == "alice"
        assert result.priority == "CRITICAL"
        assert result.intent == "ALERT"
        assert result.sequence_id == 42
        assert result.direction == "outbox"

    def test_signal_event_raw_preserved(self, tmp_path):
        f = tmp_path / "raw.json"
        packet = make_packet()
        f.write_text(json.dumps(packet))
        result = SignalEvent.from_file(f, "inbox")
        assert result is not None
        assert "header" in result.raw
        assert "body" in result.raw

    def test_signal_event_file_mtime(self, tmp_path):
        f = tmp_path / "mtime.json"
        packet = make_packet()
        f.write_text(json.dumps(packet))
        result = SignalEvent.from_file(f, "inbox")
        assert result is not None
        assert result.file_mtime > 0
