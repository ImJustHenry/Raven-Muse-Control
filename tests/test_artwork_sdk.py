"""Actual Raven/Qt rendering checks; all music and cover data are simulated."""
from dataclasses import replace
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
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtCore import QPoint
    a = MuseApp({"mode":"demo", "voice_backend":"typed"}, DemoTransport())
    palette = a.palette(); palette.setColor(QPalette.ColorRole.Window, QColor("black"))
    a.setPalette(palette); a.setAutoFillBackground(True)
    qtbot.addWidget(a); a.show(); qtbot.mouseMove(a, QPoint(5,5))
    qtbot.waitUntil(lambda: not a.cover.image.isNull(), timeout=3000)
    yield a
    a.close()


def test_cover_is_64px_noninteractive_and_card_unchanged(app):
    from PySide6.QtCore import Qt
    assert (app.cover.width(), app.cover.height()) == (64,64)
    assert app.cover.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert app.cover.parent() is app.buttons["expand"]
    assert set(app.buttons) == {"expand"}
    assert app.panel.size().width() == 256 and app.panel.size().height() == 112
    assert app.cover.geometry().right() < app.title.x()
    assert app.cover.geometry().bottom() < app.progress.y()


def test_cover_area_hit_routes_to_parent_card(app, qtbot):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication
    point = app.cover.mapToGlobal(QPoint(32,32))
    target = QApplication.widgetAt(point)
    assert target is app.buttons["expand"]
    before = len(app.transport.commands)
    qtbot.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.mapFromGlobal(point))
    assert app.expanded and len(app.transport.commands) == before


def test_song_change_replaces_art_and_missing_art_falls_back(app, qtbot):
    old = app.cover.result.data
    app.command("next")
    assert app.cover.image.isNull()  # old artwork never remains on the new title
    qtbot.waitUntil(lambda: not app.cover.image.isNull(), timeout=3000)
    assert app.cover.result.data != old
    app.transport.scenario("missing_artwork"); app.refresh()
    assert app.cover.image.isNull()
    assert app.transport.snapshot().can("pause")


def test_disconnect_removes_cover_without_hiding_card(app):
    app.transport.scenario("disconnect"); app.refresh()
    assert app.cover.image.isNull() and app.panel.isVisible()


def test_refresh_reuses_cover_widget(app):
    cover = app.cover
    for _ in range(10): app.refresh()
    assert app.cover is cover


def test_close_stops_artwork_publication(app):
    app.close()
    assert app.artwork.closed and not app.artwork.result.data


def test_metadata_match_has_distinct_accessible_provenance(app):
    from muse.artwork import ArtResult
    app.cover.set_artwork(ArtResult(app.cover.result.data, "matched", "MusicBrainz / Cover Art Archive"))
    assert "Metadata-matched" in app.cover.accessibleName()
    assert "MusicBrainz" in app.cover.toolTip()


def test_artwork_screenshot_evidence(app, qtbot):
    out = Path(os.environ.get("RMC_GAZE_OUTPUT", "test-output")); out.mkdir(parents=True, exist_ok=True)
    app.panel.grab().save(str(out / "cover-midnight.png"))
    app.command("next")
    qtbot.waitUntil(lambda: not app.cover.image.isNull(), timeout=3000)
    app.panel.grab().save(str(out / "cover-golden.png"))
    app.transport.scenario("missing_artwork"); app.refresh()
    app.panel.grab().save(str(out / "cover-unavailable.png"))
    app.expand()
    app.panel.grab().save(str(out / "cover-expanded.png"))
