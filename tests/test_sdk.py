"""Real SDK tests for corner-first controls; no physical-eye/phone claim."""
import importlib.util
import os
import time
import pytest

pytestmark = [pytest.mark.sdk, pytest.mark.skipif(
    os.environ.get("RMC_TEST_SDK") != "1" or importlib.util.find_spec("raven_framework") is None,
    reason="Set RMC_TEST_SDK=1 after installing the authorized Raven Framework")]


@pytest.fixture
def app(qtbot):
    from muse.demo import DemoTransport
    from muse.ui import MuseApp
    a = MuseApp({"mode":"demo", "voice_backend":"typed", "dwell_ms":700}, DemoTransport())
    qtbot.addWidget(a); a.show(); qtbot.wait(150)
    yield a
    a.close()


def test_preserves_qwidget_render_method():
    from muse.ui import MuseApp
    assert "render" not in MuseApp.__dict__


def test_defaults_to_one_small_corner_target(app):
    from PySide6.QtCore import Qt
    assert not app.expanded
    assert app.panel.geometry().getRect() == (368, 264, 256, 112)
    assert set(app.buttons) == {"expand"}
    assert not app.close_icon.isVisible()  # SDK Home button hidden by request.
    assert not app.app.use_gradient_border
    assert "rgba(0,0,0,0)" in app.app._background.styleSheet()
    assert app.title.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_opening_card_does_not_change_playback(app, qtbot):
    from PySide6.QtCore import Qt
    before = len(app.transport.commands)
    qtbot.mouseClick(app.buttons["expand"], Qt.MouseButton.LeftButton)
    assert app.expanded and app.panel.geometry().getRect() == (192, 160, 432, 320)
    assert len(app.transport.commands) == before


def test_real_sdk_click_and_metadata(app, qtbot):
    from PySide6.QtCore import Qt
    app.expand()
    qtbot.mouseClick(app.buttons["toggle"], Qt.MouseButton.LeftButton)
    assert app.transport.snapshot().playing is False
    app.command("next")
    assert "Golden Hour" in app.title.toolTip()


def test_real_sdk_disabled_capability(app, qtbot):
    app.expand()
    app.transport.scenario("unsupported"); app.refresh()
    assert app.buttons["next"].is_disabled()
    app.transport.scenario("disconnect"); app.refresh()
    assert app.buttons["toggle"].is_disabled()


def test_typed_commands_work_while_compact(app):
    app.handle_transcript("pause")
    assert not app.transport.snapshot().playing and not app.expanded
    app.handle_transcript("next song")
    assert "Golden Hour" in app.title.toolTip()
    app.demo_switch()
    assert app.transport.snapshot().player == "YouTube Music"
    assert "DEMO" in app.source.text()


def test_expanded_panel_is_one_flat_page_of_music_controls(app):
    app.expand()
    assert set(app.buttons) == {"previous", "toggle", "next", "volume_down", "volume_up", "hide"}
    assert app.panel.geometry().getRect() == (192, 160, 432, 320)
    assert not hasattr(app, "show_page") and not hasattr(app, "open_reach")
    before = app.transport.snapshot().volume
    app.command("volume_up")
    assert app.transport.snapshot().volume > before
    app.collapse()
    assert not app.expanded


def test_sdk_dwell_activates_next_once(app, qtbot):
    from PySide6.QtCore import QPoint
    app.expand()
    button = app.buttons["next"]
    before = len(app.transport.commands)
    qtbot.mouseMove(app, QPoint(5, 5))
    qtbot.mouseMove(button, button.rect().center())
    qtbot.waitUntil(lambda: len(app.transport.commands) > before, timeout=7000)
    qtbot.wait(1800)
    assert len(app.transport.commands) == before + 1
    assert app.transport.commands[-1] == "next"


def test_dwell_open_requires_rearming_and_never_autoplays(app, qtbot):
    from PySide6.QtCore import QPoint
    before = len(app.transport.commands)
    button = app.buttons["expand"]
    qtbot.mouseMove(app, QPoint(5, 5))
    qtbot.mouseMove(button, button.rect().center())
    qtbot.waitUntil(lambda: app.expanded, timeout=7000)
    qtbot.wait(1800)
    assert len(app.transport.commands) == before
    assert app.entry_guard is not None
    qtbot.mouseMove(app, QPoint(5, 5))
    qtbot.waitUntil(lambda: app.entry_guard is None, timeout=1500)
    assert not app.buttons["next"].is_disabled()


def test_auto_collapse_after_leaving(app):
    app.expand()
    t = app.last_interaction
    assert not app.check_auto_collapse(now=t+5, pointer_inside=False)
    assert app.check_auto_collapse(now=t+6.1, pointer_inside=False)
    assert not app.expanded


@pytest.mark.parametrize("flag", ["recording", "processing", "dialog_active"])
def test_busy_ui_does_not_auto_collapse(app, flag):
    app.expand()
    setattr(app, flag, True)
    assert not app.check_auto_collapse(now=app.last_interaction+20, pointer_inside=False)
    assert app.expanded
    setattr(app, flag, False)


def test_hover_keeps_expanded_controls_available(app):
    app.expand()
    assert not app.check_auto_collapse(now=app.last_interaction+20, pointer_inside=True)
    assert app.expanded


def test_voice_activation_returns_to_compact(app, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    app.expand()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("pause", True))
    app.voice()
    assert not app.expanded and app.transport.snapshot().playing is False


def test_long_title_is_elided_not_wrapped_over_controls(app):
    from dataclasses import replace
    with app.transport.lock:
        app.transport.state = replace(app.transport.state,
            title="A very long song title that cannot possibly fit inside the compact corner card")
    app.refresh()
    assert len(app.title.text()) < len(app.title.toolTip())
    assert app.title.width() == 154  # v1.3 reserves 64px for non-interactive artwork.
    assert "very long song" in app.title.toolTip()
