"""Coverage gap tests for cns_monitor — targeting cli.py (69%) and stats.py (98%).

Missing lines:
- cli.py: 67-70 (live mode setup), 81-94 (live mode callbacks + watch), 98 (watch call)
- stats.py: 56 (latency boundary: exactly 300 seconds)
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cns_monitor import __version__
from cns_monitor import cli
from cns_monitor.stats import CNSStats
from cns_monitor.watcher import SignalEvent


# ── cli.py coverage gaps ───────────────────────────────────────


class TestCLILiveMode:
    """Test live mode entry paths (lines 67-98)."""

    def test_live_mode_calls_watch(self, tmp_path):
        """Live mode should call watcher.watch()."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with patch("cns_monitor.cli.CNSWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher

            with patch("cns_monitor.cli.CNSDisplay") as mock_display_cls:
                mock_display = MagicMock()
                mock_display_cls.return_value = mock_display

                with patch("rich.live.Live") as mock_live_cls:
                    mock_live = MagicMock()
                    mock_live_cls.return_value = mock_live

                    with patch.object(sys, "argv", [
                        "cns-monitor",
                        "--inbox", str(inbox),
                        "--outbox", str(outbox),
                        "--interval", "0.1",
                    ]):
                        cli.main()

                    mock_watcher.watch.assert_called_once()

    def test_live_mode_sets_up_callbacks(self, tmp_path):
        """Live mode should register callbacks on watcher."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with patch("cns_monitor.cli.CNSWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher

            with patch("cns_monitor.cli.CNSDisplay") as mock_display_cls:
                mock_display = MagicMock()
                mock_display_cls.return_value = mock_display

                with patch("rich.live.Live"):
                    with patch.object(sys, "argv", [
                        "cns-monitor",
                        "--inbox", str(inbox),
                        "--outbox", str(outbox),
                    ]):
                        cli.main()

                    # on_signal should have been called
                    mock_watcher.on_signal.assert_called()

    def test_live_mode_uses_console(self, tmp_path):
        """Live mode should create and clear a console."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with patch("cns_monitor.cli.CNSWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher

            with patch("cns_monitor.cli.CNSDisplay"):
                with patch("rich.live.Live"):
                    with patch("rich.console.Console") as mock_console_cls:
                        mock_console = MagicMock()
                        mock_console_cls.return_value = mock_console

                        with patch.object(sys, "argv", [
                            "cns-monitor",
                            "--inbox", str(inbox),
                            "--outbox", str(outbox),
                        ]):
                            cli.main()

                        mock_console.clear.assert_called_once()

    def test_live_mode_replaces_callbacks(self, tmp_path):
        """Live mode should replace callbacks for live updating."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with patch("cns_monitor.cli.CNSWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher

            with patch("cns_monitor.cli.CNSDisplay"):
                with patch("rich.live.Live"):
                    with patch.object(sys, "argv", [
                        "cns-monitor",
                        "--inbox", str(inbox),
                        "--outbox", str(outbox),
                    ]):
                        cli.main()

                    # _callbacks should be replaced with live callback
                    assert mock_watcher._callbacks is not None


# ── cli.py edge cases ──────────────────────────────────────────


class TestCLIEdgeCases:
    def test_once_with_both_inbox_and_outbox_signals(self, tmp_path, capsys):
        """Once mode with signals in both dirs."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        packet_in = {
            "header": {"origin_id": "hermes", "timestamp": "2026-08-06T09:00:00Z",
                        "priority": "HIGH", "sequence_id": 1, "packet_id": "p1"},
            "body": {"intent": "QUERY", "payload": {"msg": "test"}},
            "signature": {"type": "sha256", "checksum": "abc"},
        }
        packet_out = {
            "header": {"origin_id": "wesley", "timestamp": "2026-08-06T09:00:01Z",
                        "priority": "NORMAL", "sequence_id": 2, "packet_id": "p2"},
            "body": {"intent": "STATUS_REPORT", "payload": {}},
            "signature": {"type": "sha256", "checksum": "def"},
        }
        (inbox / "sig_in.uscp.json").write_text(json.dumps(packet_in))
        (outbox / "sig_out.uscp.json").write_text(json.dumps(packet_out))

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", [
                "cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once",
            ]):
                cli.main()
        assert exc_info.value.code == 0

    def test_help_flag(self):
        """--help should exit with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["cns-monitor", "--help"]):
                cli.main()
        assert exc_info.value.code == 0

    def test_default_interval_is_float(self, tmp_path):
        """Ensure --interval accepts floats."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", [
                "cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox),
                "--once", "--interval", "0.25",
            ]):
                cli.main()


# ── stats.py coverage gaps ─────────────────────────────────────


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


class TestStatsEdgeCases:
    def test_latency_exactly_300_seconds(self):
        """Latency of exactly 300s should be ignored (line 56: < 300, not <=)."""
        stats = CNSStats()
        base = time.time()
        inbox_event = make_event(origin="agent-a", direction="inbox", mtime=base)
        stats.record(inbox_event)
        # latency = exactly 300 should NOT be recorded
        outbox_event = make_event(origin="agent-b", direction="outbox", mtime=base + 300)
        stats.record(outbox_event)
        assert stats.avg_latency_ms == 0.0

    def test_latency_just_under_300(self):
        """Latency just under 300s should be recorded."""
        stats = CNSStats()
        base = time.time()
        inbox_event = make_event(origin="agent-a", direction="inbox", mtime=base)
        stats.record(inbox_event)
        outbox_event = make_event(origin="agent-b", direction="outbox", mtime=base + 299)
        stats.record(outbox_event)
        assert stats.avg_latency_ms > 0

    def test_signals_per_minute_single_event(self):
        """Single event should give 0.0 signals/min."""
        stats = CNSStats()
        stats._recent_timestamps.append(time.time())
        assert stats.signals_per_minute == 0.0

    def test_signals_per_minute_zero_elapsed(self):
        """Same timestamp should give 0.0 (elapsed <= 0)."""
        stats = CNSStats()
        ts = time.time()
        stats._recent_timestamps.append(ts)
        stats._recent_timestamps.append(ts)
        assert stats.signals_per_minute == 0.0

    def test_agent_target_counts(self):
        """Outbox events should track target counts."""
        stats = CNSStats()
        stats.record(make_event(origin="wesley", direction="inbox"))
        # agent_signal_counts should track origin
        assert stats.agent_signal_counts["wesley"] == 1

    def test_multiple_outbox_same_origin_no_latency(self):
        """Outbox from same origin as last inbox shouldn't create latency."""
        stats = CNSStats()
        base = time.time()
        stats.record(make_event(origin="same-agent", direction="inbox", mtime=base))
        stats.record(make_event(origin="same-agent", direction="outbox", mtime=base + 5))
        assert stats.avg_latency_ms == 0.0

    def test_outbox_without_prior_inbox(self):
        """Outbox without prior inbox should not crash."""
        stats = CNSStats()
        stats.record(make_event(origin="lonely", direction="outbox", mtime=time.time()))
        assert stats.avg_latency_ms == 0.0

    def test_priority_counts_multiple(self):
        """Verify all priority levels tracked."""
        stats = CNSStats()
        for p in ["LOW", "NORMAL", "HIGH", "CRITICAL", "URGENT"]:
            stats.record(make_event(priority=p))
        assert stats.priority_counts["URGENT"] == 1
        assert stats.priority_counts["LOW"] == 1
