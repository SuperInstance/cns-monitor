"""
Tests for cns_monitor display module — the Rich terminal UI.

Tests cover:
- CNSDisplay initialization
- add_event and event buffering (max 50)
- render() output structure
- print_event formatting
- Priority color mapping
- Direction icon mapping
- Empty state handling
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from cns_monitor.display import CNSDisplay, PRIORITY_COLORS, DIRECTION_ICONS
from cns_monitor.watcher import SignalEvent
from cns_monitor.stats import CNSStats


# ─── Helpers ─────────────────────────────────────────────

def make_event(**kwargs):
    """Create a SignalEvent with sensible defaults."""
    defaults = dict(
        filepath=Path("/tmp/test.json"),
        filename="test.json",
        direction="inbox",
        origin_id="agent:tester",
        timestamp="2026-08-05T14:30:00Z",
        priority="HIGH",
        sequence_id=42,
        intent="test_signal",
        raw={},
    )
    defaults.update(kwargs)
    return SignalEvent(**defaults)


# ─── Fixtures ─────────────────────────────────────────────

@pytest.fixture
def sample_event():
    return make_event()


@pytest.fixture
def critical_event():
    return make_event(
        filename="crit.json",
        direction="outbox",
        origin_id="agent:architect",
        intent="emergency",
        priority="CRITICAL",
        sequence_id=43,
    )


@pytest.fixture
def empty_stats():
    return CNSStats()


@pytest.fixture
def display():
    return CNSDisplay(console=MagicMock())


# ─── Initialization Tests ────────────────────────────────

class TestCNSDisplayInit:
    def test_default_init(self):
        d = CNSDisplay()
        assert d._recent_events == []

    def test_custom_console(self):
        console = MagicMock()
        d = CNSDisplay(console=console)
        assert d.console is console

    def test_starts_empty(self, display):
        assert len(display._recent_events) == 0


# ─── Event Buffering Tests ───────────────────────────────

class TestEventBuffering:
    def test_add_single_event(self, display, sample_event):
        display.add_event(sample_event)
        assert len(display._recent_events) == 1

    def test_add_multiple_events(self, display):
        for i in range(10):
            display.add_event(make_event(filename=f"test_{i}.json", sequence_id=i))
        assert len(display._recent_events) == 10

    def test_buffer_caps_at_50(self, display):
        for i in range(60):
            display.add_event(make_event(filename=f"test_{i}.json", sequence_id=i))
        assert len(display._recent_events) == 50

    def test_buffer_keeps_most_recent(self, display):
        for i in range(55):
            display.add_event(make_event(
                filename=f"test_{i}.json",
                intent=f"intent_{i}",
                sequence_id=i,
            ))
        # Buffer caps at 50, so with 55 events (0-54), oldest 5 are dropped
        assert display._recent_events[0].intent == "intent_5"
        assert display._recent_events[-1].intent == "intent_54"


# ─── Render Tests ────────────────────────────────────────

class TestRender:
    def test_render_returns_panel(self, display, empty_stats):
        panel = display.render(empty_stats, "/inbox", "/outbox")
        assert panel is not None

    def test_render_with_events(self, display, sample_event, empty_stats):
        display.add_event(sample_event)
        panel = display.render(empty_stats, "/inbox", "/outbox")
        assert panel is not None

    def test_render_empty_state(self, display, empty_stats):
        panel = display.render(empty_stats, "/inbox", "/outbox")
        assert panel is not None

    def test_render_with_populated_stats(self, display):
        stats = CNSStats()
        ev1 = make_event(direction="inbox", origin_id="agent:a", intent="build")
        ev2 = make_event(direction="outbox", origin_id="agent:b", intent="run")
        stats.record(ev1)
        stats.record(ev2)
        display.add_event(ev1)
        panel = display.render(stats, "/inbox", "/outbox")
        assert panel is not None


# ─── Print Event Tests ───────────────────────────────────

class TestPrintEvent:
    def test_print_event_calls_console(self, display, sample_event):
        display.print_event(sample_event)
        assert display.console.print.called

    def test_print_critical_event(self, display, critical_event):
        display.print_event(critical_event)
        assert display.console.print.called

    def test_print_event_with_none_sequence(self, display):
        ev = make_event(sequence_id=None)
        display.print_event(ev)
        assert display.console.print.called


# ─── Priority Colors Tests ───────────────────────────────

class TestPriorityColors:
    def test_all_priorities_mapped(self):
        assert "CRITICAL" in PRIORITY_COLORS
        assert "HIGH" in PRIORITY_COLORS
        assert "MEDIUM" in PRIORITY_COLORS
        assert "LOW" in PRIORITY_COLORS

    def test_critical_is_red(self):
        assert "red" in PRIORITY_COLORS["CRITICAL"]

    def test_medium_is_green(self):
        assert "green" in PRIORITY_COLORS["MEDIUM"]


# ─── Direction Icons Tests ───────────────────────────────

class TestDirectionIcons:
    def test_inbox_icon(self):
        assert DIRECTION_ICONS["inbox"] == "→"

    def test_outbox_icon(self):
        assert DIRECTION_ICONS["outbox"] == "←"

    def test_unknown_direction_handled(self, display):
        """Unknown direction should get '?' icon, not crash."""
        ev = make_event(direction="sideways")
        display.print_event(ev)
        assert display.console.print.called
