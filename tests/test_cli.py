"""Tests for the cns-monitor CLI module."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cns_monitor import __version__
from cns_monitor import cli


# ─── Default Path Tests ────────────────────────────────────────

class TestDefaultPaths:
    def test_default_inbox(self):
        result = cli.default_inbox()
        assert "cns_inbox" in result

    def test_default_outbox(self):
        result = cli.default_outbox()
        assert "cns_outbox" in result

    def test_default_inbox_expands(self):
        with patch.dict("os.environ", {"HOME": "/tmp/fakehome"}):
            result = cli.default_inbox()
            assert "/tmp/fakehome" in result

    def test_default_outbox_expands(self):
        with patch.dict("os.environ", {"HOME": "/tmp/fakehome"}):
            result = cli.default_outbox()
            assert "/tmp/fakehome" in result


# ─── Once Mode Tests ───────────────────────────────────────────

class TestOnceMode:
    def test_once_no_signals(self, tmp_path, capsys):
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once"]):
                cli.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No signals" in captured.out

    def test_once_with_signal(self, tmp_path, capsys):
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        packet = {
            "header": {
                "origin_id": "hermes",
                "destination_id": "lucineer",
                "timestamp": "2026-08-06T09:00:00Z",
                "priority": "HIGH",
                "sequence_id": 1,
                "packet_id": "test-001",
            },
            "body": {
                "intent": "QUERY",
                "payload": {"message": "test"},
            },
            "signature": {"type": "sha256", "checksum": "abc"},
        }
        (inbox / "signal.uscp.json").write_text(json.dumps(packet))

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once"]):
                cli.main()
        assert exc_info.value.code == 0

    def test_once_with_outbox_signal(self, tmp_path, capsys):
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        packet = {
            "header": {
                "origin_id": "lucineer",
                "destination_id": "hermes",
                "timestamp": "2026-08-06T09:00:00Z",
                "priority": "NORMAL",
                "sequence_id": 1,
                "packet_id": "resp-001",
            },
            "body": {"intent": "STATUS_REPORT", "payload": {}},
            "signature": {"type": "sha256", "checksum": "def"},
        }
        (outbox / "response.uscp.json").write_text(json.dumps(packet))

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once"]):
                cli.main()
        assert exc_info.value.code == 0


# ─── Version Flag Tests ────────────────────────────────────────

class TestVersionFlag:
    def test_version_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["cns-monitor", "--version"]):
                cli.main()
        assert exc_info.value.code == 0


# ─── Custom Interval Tests ─────────────────────────────────────

class TestCustomArgs:
    def test_custom_interval_accepted(self, tmp_path):
        """--interval should be accepted without error."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        outbox = tmp_path / "outbox"
        outbox.mkdir()

        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once", "--interval", "2.0"]):
                cli.main()

    def test_custom_inbox_outbox(self, tmp_path, capsys):
        inbox = tmp_path / "custom_in"
        inbox.mkdir()
        outbox = tmp_path / "custom_out"
        outbox.mkdir()

        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["cns-monitor", "--inbox", str(inbox), "--outbox", str(outbox), "--once"]):
                cli.main()
        captured = capsys.readouterr()
        assert "No signals" in captured.out
