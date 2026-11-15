"""Actual SDK subclass rendering/interaction tests, not physical-eye validation."""
import importlib.util
import os
from pathlib import Path
import pytest

pytestmark = [pytest.mark.sdk, pytest.mark.skipif(
    os.environ.get("RMC_TEST_SDK") != "1" or importlib.util.find_spec("raven_framework") is None,
    reason="Authorized Raven SDK and RMC_TEST_SDK=1 required")]


@pytest.fixture
def app(qtbot):
    from muse.demo import DemoTransport
    from muse.ui import MuseApp
    a = MuseApp({"mode":"demo", "voice_backend":"typed", "dwell_ms":1100}, DemoTransport())
    # Standalone widget tests lack RunApp's black canvas; match it explicitly.
    from PySide6.QtGui import QColor, QPalette
    palette = a.palette(); palette.setColor(QPalette.ColorRole.Window, QColor("black"))
    a.setPalette(palette); a.setAutoFillBackground(True)
    qtbot.addWidget(a); a.show(); qtbot.wait(150)
    yield a
    a.close()


def test_targets_are_real_sdk_buttons(app):
    from raven_framework.components.button import Button
    from muse.gaze_target import GazeTarget
    app.expand()
    assert all(isinstance(b, Button) and isinstance(b, GazeTarget) for b in app.buttons.values())
    assert "enterEvent" not in GazeTarget.__dict__
    assert "update_progress" not in GazeTarget.__dict__


def test_all_six_targets_have_equal_large_hit_boxes(app):
    app.expand()
    assert len(app.buttons) == 6
    for b in app.buttons.values():
        assert (b.width(), b.height()) == (128, 104)
    a, b, c = [app.buttons[key] for key in ("previous", "toggle", "next")]
    assert b.x() - (a.x()+a.width()) == 16
    assert c.x() - (b.x()+b.width()) == 16
    assert app.buttons["volume_down"].y() - (a.y()+a.height()) == 16


def test_demo_marker_is_not_elided_from_compact_header(app):
    app.demo_switch()
    assert "DEMO" in app.source.text()
    assert "YT Music" in app.source.text()
    assert app.title.toolTip() == "Midnight Drive"  # Text may elide beside the cover.
    assert app.transport.snapshot().title == "Demo: Midnight Drive"


def test_real_metadata_is_not_rewritten(app):
    from dataclasses import replace
    from muse.ui import MuseApp
    state = replace(app.transport.snapshot(), title="Demo: A Real Song", simulated=False)
    assert MuseApp.display_title(state) == "Demo: A Real Song"


def test_progress_ring_uses_sdk_progress_and_cancels(app, qtbot):
    from PySide6.QtCore import QPoint
    out = Path(os.environ.get("RMC_GAZE_OUTPUT", "test-output"))
    out.mkdir(parents=True, exist_ok=True)
    app.panel.grab().save(str(out / "compact-panel.png"))
    app.expand()
    app.panel.grab().save(str(out / "expanded-panel.png"))
    target = app.buttons["next"]
    before = len(app.transport.commands)
    qtbot.mouseMove(app, QPoint(5, 5))
    qtbot.mouseMove(target, target.rect().center())
    qtbot.waitUntil(lambda: .30 < target.dwell_fraction() < .85, timeout=7000)
    app.refresh()
    fraction = target.dwell_fraction()
    assert fraction == pytest.approx(target.progress / target.max_progress)
    assert len(app.transport.commands) == before
    app.panel.grab().save(str(out / "focused-panel.png"))
    qtbot.mouseMove(app, QPoint(5, 5))
    qtbot.wait(1600)
    assert len(app.transport.commands) == before
    assert target.dwell_fraction() == 0


def test_selection_feedback_means_input_not_phone_confirmation(app, qtbot):
    from PySide6.QtCore import Qt
    app.expand()
    button = app.buttons["toggle"]
    assert not button.selected()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert button.selected()
    assert button.selected_label == "Pause"
    assert app.transport.commands[-1] == "pause"
    assert button.text == "Play"
    qtbot.wait(500)
    assert not button.selected()


def test_disabled_target_never_shows_progress_or_dispatches(app, qtbot):
    from PySide6.QtCore import Qt
    app.expand()
    app.transport.scenario("unsupported"); app.refresh()
    target = app.buttons["next"]
    before = len(app.transport.commands)
    qtbot.mouseClick(target, Qt.MouseButton.LeftButton)
    assert target.dwell_fraction() == 0
    assert not target.selected()
    assert len(app.transport.commands) == before


def test_gutter_is_not_a_hidden_hit_target(app, qtbot):
    from PySide6.QtCore import QPoint
    app.expand()
    before = len(app.transport.commands)
    qtbot.mouseMove(app.panel, QPoint(144, 140))
    qtbot.wait(1700)
    assert len(app.transport.commands) == before


def test_toggle_icon_and_accessible_label_follow_reported_state(app):
    app.expand()
    target = app.buttons["toggle"]
    assert target.icon_name == "pause"
    assert target.accessibleName() == "Pause"
    app.handle_transcript("pause")
    assert target.icon_name == "play"
    assert target.accessibleName() == "Play"


def test_refresh_does_not_recreate_gaze_targets(app):
    app.expand()
    target = app.buttons["next"]
    for _ in range(10): app.refresh()
    assert app.buttons["next"] is target
