"""Desktop-simulator display tuning. Has no effect on Raven hardware.

The SDK simulator's default preview blends every frame into a background video
with per-pixel numpy LUTs (~40 ms/frame on a typical laptop), so the window
updates only ~5-16 times a second even though the app itself renders in ~3 ms.
By default we switch the simulator to its built-in Raw view and refresh *only
that view* at 60 fps. Set RMC_SIM_PREVIEW=blend to start in the blended preview.

The SDK's shared OVERLAY_FRAME_RATE is deliberately left alone: the blended
(Room/Camera) modes discard any result older than the latest request, so a
request interval shorter than the ~40 ms blend time starves them to 0 fps.
The SDK itself is not modified; the Background menu still switches views.
"""
import os

RAW_INTERVAL_MS = 16  # ~60 fps; Raw frames cost ~3 ms.


def schedule_fast_preview():
    """Call from the RunApp widget factory; runs once the simulator window exists."""
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, _apply)


def _apply():
    try:
        from PySide6.QtWidgets import QApplication
        import raven_framework.core.raven_simulator as sim
    except ImportError:
        return
    windows = [w for w in QApplication.topLevelWidgets() if isinstance(w, sim.SimulatorRunApp)]
    if not windows or not hasattr(windows[0], '_raw_update_timer'):
        return  # On device (or an SDK without this view): leave everything alone.
    window = windows[0]

    def speed_up_raw():
        timer = window._raw_update_timer
        if timer.isActive() and timer.interval() != RAW_INTERVAL_MS:
            timer.setInterval(RAW_INTERVAL_MS)

    # The SDK restarts the raw timer at its default rate on view switches and
    # sleep/wake; re-apply the faster interval after those calls only.
    for name in ('_set_raw_view', 'wake_app_ui'):
        original = getattr(window, name, None)
        if original is None:
            continue
        def wrapped(*args, _original=original, **kwargs):
            result = _original(*args, **kwargs)
            speed_up_raw()
            return result
        setattr(window, name, wrapped)

    if os.environ.get('RMC_SIM_PREVIEW', 'raw').strip().lower() != 'blend':
        window._set_raw_view(True)
