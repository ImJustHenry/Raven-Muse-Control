"""Real SDK compact/expanded screenshot proof, using simulated phone state."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from raven_framework.core.run_app import RunApp
from muse.demo import DemoTransport
from muse.ui import MuseApp

out = Path(os.environ.get("RMC_SMOKE_OUTPUT", "test-output"))
out.mkdir(parents=True, exist_ok=True)
result = {"real_sdk_window": False, "demo_transport": True, "physical_phone": False}


def make():
    app = MuseApp({"mode":"demo", "voice_backend":"typed", "dwell_ms":1100}, DemoTransport())
    def windows():
        return [w for w in QApplication.topLevelWidgets() if type(w).__name__ == "SimulatorRunApp"]
    def exercise():
        try:
            assert not app.expanded
            app.handle_transcript("pause")
            assert app.transport.snapshot().playing is False and not app.expanded
            app.handle_transcript("next song")
            assert "Golden Hour" in app.transport.snapshot().title
            app.handle_transcript("resume")
            assert app.transport.snapshot().playing is True
            app.demo_switch()
            assert app.transport.snapshot().player == "YouTube Music"
            result["transport_and_transcript_checks"] = "passed"
        except Exception as error:
            result["error"] = repr(error)
    def compact_capture():
        result["real_sdk_window"] = bool(windows())
        result["content_size"] = [app.app.width(), app.app.height()]
        result["compact_rect"] = list(app.panel.geometry().getRect())
        result["cover_size"] = [app.cover.width(), app.cover.height()]
        result["demo_cover_visible"] = not app.cover.image.isNull()
        result["compact_target_count"] = len(app.buttons)
        app.panel.grab().save(str(out / "simulator-cover-card.png"))
        app.grab().save(str(out / "muse-app.png"))
        for window in windows():
            window.grab().save(str(out / "raven-sdk-simulator.png"))
        QTimer.singleShot(150, expand)
        QTimer.singleShot(1100, expanded_capture)
        QTimer.singleShot(1600, finish)
    def expand():
        before = len(app.transport.commands)
        app.expand()
        result["expanded_rect"] = list(app.panel.geometry().getRect())
        result["expanding_sends_no_music_command"] = len(app.transport.commands) == before
    def expanded_capture():
        app.grab().save(str(out / "muse-expanded.png"))
        for window in windows():
            window.grab().save(str(out / "raven-sdk-expanded.png"))
        result["auto_collapse"] = app.check_auto_collapse(now=app.last_interaction+7, pointer_inside=False)
        result["compact_after_timeout"] = not app.expanded
    def finish():
        (out / "sdk-smoke.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        app.close()
        for window in windows():
            window.close()
        QTimer.singleShot(300, QApplication.instance().quit)
    QTimer.singleShot(1200, exercise)
    import time
    deadline=time.monotonic()+12
    def wait_for_cover():
        if not app.cover.image.isNull() or time.monotonic()>deadline:
            compact_capture()
        else:
            QTimer.singleShot(100,wait_for_cover)
    QTimer.singleShot(2500, wait_for_cover)
    return app


if __name__ == "__main__":
    RunApp.run(make)
    if (not result.get("real_sdk_window") or "error" in result or not result.get("auto_collapse")
            or not result.get("demo_cover_visible") or result.get("compact_target_count") != 1):
        raise SystemExit(1)
