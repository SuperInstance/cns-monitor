"""Tests for bug fixes: once-mode printing, live-mode callback registration,
project.scripts entry point, and dead code removal."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cns_monitor import cli
from cns_monitor.stats import CNSStats
from cns_monitor.watcher import SignalEvent


def write_packet(directory: Path, filename: str, origin="agent-x", intent="QUERY",
                 priority="HIGH", seq=1) -> None:
    """Write a USCP packet to a directory."""
    packet = {
        "header": {
            "origin_id": origin,
            "timestamp": "2026-08-07T10:00:00Z",
            "priority": priority,
            "sequence_id": seq,
        },
        "body": {"intent": intent, "payload": {"type": "signal"}},
        "signature": {"type": "USCP-v1", "checksum": "ok"},
    }
    (directory / filename).write_text(json.dumps(packet))


class TestOnceModePrintsEvents:
    """Bug fix: --once mode was never calling print_event because
    scan_once() doesn't fire callbacks. Now we iterate events directly."""

    def test_once_prints_event_details(self, tmp_path, capsys):
        """--once should actually print signal details to stdout."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        write_packet(inbox, "sig1.json", origin="visible-agent", intent="QUERY")

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", [
                "cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once",
            ]):
                cli.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        # The printed output should contain the agent name (now that we print directly)
        assert "visible-agent" in captured.out

    def test_once_prints_multiple_events(self, tmp_path, capsys):
        """--once should print all detected signals."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()
        write_packet(inbox, "sig1.json", origin="agent-one")
        write_packet(outbox, "sig2.json", origin="agent-two")

        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", [
                "cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once",
            ]):
                cli.main()
        captured = capsys.readouterr()
        assert "agent-one" in captured.out
        assert "agent-two" in captured.out

    def test_once_no_signals_message(self, tmp_path, capsys):
        """--once with no signals should print 'No signals detected.'"""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", [
                "cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once",
            ]):
                cli.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No signals" in captured.out


class TestLiveModeCallbackRegistration:
    """Bug fix: Live mode was doing watcher._callbacks = [...] which bypasses
    the on_signal() API. Now uses on_signal() properly."""

    def test_live_mode_uses_on_signal_not_assignment(self, tmp_path):
        """Live mode should register callbacks via on_signal(), not
        direct _callbacks assignment."""
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        inbox.mkdir()
        outbox.mkdir()

        with patch("cns_monitor.cli.CNSWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher

            with patch("cns_monitor.cli.CNSDisplay"):
                with patch("rich.live.Live"):
                    with patch("rich.console.Console"):
                        with patch.object(sys, "argv", [
                            "cns-monitor", "--inbox", str(inbox),
                            "--outbox", str(outbox),
                        ]):
                            cli.main()

                        # on_signal should be called (not _callbacks assignment)
                        mock_watcher.on_signal.assert_called()
                        # _callbacks should NOT be assigned to directly
                        # (the old code did watcher._callbacks = [cb])
                        # We verify on_signal was the registration method
                        assert mock_watcher.on_signal.call_count >= 1


class TestProjectScriptsEntryPoint:
    """Bug fix: cns-monitor entry point was under [tool.pytest.ini_options]
    instead of [project.scripts]."""

    def test_pyproject_has_project_scripts(self):
        """pyproject.toml should have [project.scripts] with cns-monitor."""
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        assert "[project.scripts]" in content
        assert 'cns-monitor = "cns_monitor.cli:main"' in content

    def test_pytest_config_is_clean(self):
        """The pytest config section should NOT contain the entry point."""
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        # Find the pytest section
        pytest_start = content.find("[tool.pytest.ini_options]")
        assert pytest_start != -1
        pytest_section = content[pytest_start:]
        assert "cns-monitor" not in pytest_section


class TestDeadCodeRemoval:
    """Verify dead code was removed cleanly."""

    def test_stats_no_agent_target_counts(self):
        """agent_target_counts was never populated — dead code removed."""
        stats = CNSStats()
        assert not hasattr(stats, "agent_target_counts")

    def test_stats_no_defaultdict_import(self):
        """defaultdict was imported but never used after removing dead code."""
        import cns_monitor.stats as stats_mod
        source = open(stats_mod.__file__).read()
        assert "defaultdict" not in source


class TestSignalEventDisplayWithNoneSeq:
    """Edge case: sequence_id=None should render '—' in display."""

    def test_print_event_none_seq_id(self):
        """print_event should handle sequence_id=None without error."""
        from cns_monitor.display import CNSDisplay
        display = CNSDisplay(console=MagicMock())
        ev = SignalEvent(
            filepath=Path("/tmp/t.json"),
            filename="t.json",
            direction="inbox",
            origin_id="test",
            timestamp="2026-08-07T10:00:00Z",
            priority="HIGH",
            sequence_id=None,
            intent="TEST",
        )
        display.print_event(ev)
        assert display.console.print.called
