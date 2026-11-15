"""Corner-first Raven SDK UI with optional, non-blocking cover artwork."""
import time
from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import QApplication, QInputDialog, QProgressBar
from raven_framework.core.raven_app import RavenApp
from raven_framework.components.container import Container
from raven_framework.components.text_box import TextBox
from raven_framework.helpers.async_runner import AsyncRunner
from raven_framework.helpers.animation_utils import fade_in
from .corner import COMPACT_SIZE, EXPANDED_SIZE, CONTROL_SIZE, CONTROL_GAP, DEFAULT_CORNER, anchored_rect
from .gaze_target import GazeTarget
from .voice import parse, Transcriber
from .artwork import ArtworkManager
from .cover_view import CoverView

CYAN = "#8CEBD4"
WHITE = "#FAFBFF"
MUTED = "#AEBCC8"


class MuseApp(RavenApp):
    """Music controls only: compact now-playing card plus one page of playback targets."""
    def __init__(self, config, transport):
        super().__init__()
        palette=self.palette()
        palette.setColor(QPalette.ColorRole.Window,QColor('#000000'))
        self.setPalette(palette)
        self.config, self.transport = config, transport
        self.artwork = ArtworkManager(config)
        QApplication.instance().aboutToQuit.connect(self.artwork.close)
        self.runner = AsyncRunner()
        self.transcriber = Transcriber(config)
        self.mic = None
        self.recording = self.processing = self.dialog_active = False
        self.closing = False
        self.expanded = False
        self.page = "main"
        self.last_activation = 0.0
        self.last_interaction = time.monotonic()
        self.locked_widget = None
        self.entry_guard = None
        self.banner = ""
        self.banner_until = 0.0
        self.buttons = {}
        self.shortcuts = []
        # Use the SDK's public styling API; do not paint a full-screen panel.
        # Black is optically unlit on the waveguide, not an opaque physical mask.
        self.app.use_gradient_border = False
        self.app.update_background_style("transparent", None, 0, 0, "transparent")
        self.build_page()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(150)
        self.transport.start()
        QApplication.instance().aboutToQuit.connect(self.transport.close)
        shortcuts = (("Space", self.toggle), ("Right", lambda: self.command("next")),
                     ("Left", lambda: self.command("previous")), ("V", self.voice),
                     ("Up", lambda: self.command("volume_up")),
                     ("Down", lambda: self.command("volume_down")),
                     ("D", self.demo_switch), ("L", self.lab),
                     ("E", self.expand), ("Escape", self.collapse))
        for key, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        # User choice: no SDK Home (four-circle) button. Enter still exits in the
        # simulator via RavenApp.keyPressEvent; the SDK itself is unmodified.
        if getattr(self, "close_icon", None) is not None:
            self.close_icon.hide()
        self.refresh()
        fade_in(self.app)  # AGENTS.md: fade in at the end of __init__.

    def notice(self, text, seconds=4):
        self.banner = text
        self.banner_until = time.monotonic() + seconds
        self.refresh()

    def text(self, text, x, y, width, height, font_type="body", color=WHITE, parent=None,
             wrap=False, alignment="left"):
        # Theme font roles only (AGENTS.md): title 38 / headline 33 / body 28 / small 18.
        parent = parent or self.panel
        label = TextBox(text=text, parent=parent, width=width, height=height,
                        font_type=font_type, text_color=color, wrap_words=wrap,
                        alignment=alignment)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.move(x, y)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.show()
        return label

    def fit(self, label, value):
        value = str(value)
        label.setToolTip(value)  # Full text is inspectable in desktop testing.
        label.set_text(label.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, label.width()))

    def button(self, key, label, x, y, width, height, callback, accent=False):
        button = GazeTarget(key, label, width, height, primary=accent,
            dwell_ms=max(700, min(2200, int(self.config.get("dwell_ms", 1100)))))
        button.setParent(self.panel)
        button.move(x, y)
        button.installEventFilter(self)
        def clicked():
            now = time.monotonic()
            if self.locked_widget is button or now - self.last_activation < .5:
                return
            if self.entry_guard is not None:
                return
            self.locked_widget = button
            self.last_activation = self.last_interaction = now
            button.confirm_selection()
            callback()
        button.on_clicked(clicked)
        button.show()
        self.buttons[key] = button
        return button

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Leave and watched is self.locked_widget:
            self.locked_widget = None
        if event.type() == QEvent.Type.Enter and watched in self.buttons.values():
            self.last_interaction = time.monotonic()
        return super().eventFilter(watched, event)

    def build_page(self):
        # Do not override QWidget.render: the real SDK simulator calls it.
        self.app.clear()
        self.buttons = {}
        self.locked_widget = None
        size = EXPANDED_SIZE if self.expanded else COMPACT_SIZE
        x, y, width, height = anchored_rect(self.app.width(), self.app.height(), *size,
            corner=self.config.get("ui_corner", DEFAULT_CORNER))
        self.panel = Container(width=width, height=height, background_color="transparent",
                               border_width=0, use_gradient_border=False)
        self.app.add(self.panel, x=x, y=y)
        self.panel.setPalette(self.palette())
        if not self.expanded:
            card = self.button("expand", "", 0, 0, width, height, self.open_from_gaze, True)
            # Text overlays do not intercept gaze/mouse events. The WHOLE card is
            # one large target; there are no tiny hidden play/next hit regions.
            self.source = self.text("", 14, 6, 178, 26, "small", MUTED, parent=card)
            self.cover = CoverView(card)
            self.cover.move(12, 34)
            self.cover.show()
            self.title = self.text("", 88, 32, 154, 38, "body", parent=card)
            self.artist = self.text("", 88, 72, 154, 26, "small", MUTED, parent=card)
            self.progress = self.progress_bar(228, 3, card, 14, 105)
            return
        # Minimal text: source + time on one quiet line, then the title. No
        # instruction line; the focus outline and dwell ring carry that.
        self.source = self.text("", 10, 4, 270, 26, "small", MUTED)
        self.time_label = self.text("", 286, 4, 136, 26, "small", MUTED, alignment="right")
        self.title = self.text("", 10, 32, 412, 46, "headline")
        self.artist = None
        self.progress = None
        # One flat page of music controls; no sub-menus.
        rows = [("previous", "Prev", lambda: self.command("previous")),
                ("toggle", "Play", self.toggle),
                ("next", "Next", lambda: self.command("next")),
                ("volume_down", "Vol -", lambda: self.command("volume_down")),
                ("volume_up", "Vol +", lambda: self.command("volume_up")),
                ("hide", "Hide", self.collapse)]
        for i, (key, label, callback) in enumerate(rows):
            row = i // 3
            self.button(key, label, 8 + (i % 3) * (CONTROL_SIZE[0] + CONTROL_GAP),
                        88 + row * (CONTROL_SIZE[1] + CONTROL_GAP),
                        *CONTROL_SIZE, callback, key == "toggle")

    def progress_bar(self, width, height, parent, x, y):
        bar = QProgressBar(parent)
        bar.setFixedSize(width, height)
        bar.setRange(0, 1000)
        bar.setTextVisible(False)
        bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bar.setStyleSheet("QProgressBar{border:0;background:#17221F;}"
                          "QProgressBar::chunk{background:#76E9D1;}")
        bar.move(x, y); bar.show()
        return bar

    def open_from_gaze(self):
        old = QRect(self.panel.mapToGlobal(QPoint(0, 0)), self.panel.size())
        self.expand()
        # Look away from the old card to re-arm. Expanding never sends playback.
        self.entry_guard = old
        self.refresh()

    def expand(self):
        if self.recording or self.processing:
            return
        self.expanded = True
        self.page = "main"
        self.entry_guard = None
        self.last_interaction = time.monotonic()
        self.build_page(); self.refresh()

    def collapse(self):
        if not self.expanded:
            return
        self.expanded = False
        self.page = "main"
        self.entry_guard = None
        self.build_page(); self.refresh()

    def check_auto_collapse(self, now=None, pointer_inside=None):
        if not self.expanded or self.recording or self.processing or self.dialog_active:
            return False
        now = time.monotonic() if now is None else now
        if pointer_inside is None:
            point = self.panel.mapFromGlobal(QCursor.pos())
            pointer_inside = self.panel.rect().contains(point)
        if pointer_inside:
            self.last_interaction = now
            return False
        timeout = max(2, min(30, float(self.config.get("auto_collapse_seconds", 6))))
        if now - self.last_interaction >= timeout:
            self.collapse()
            return True
        return False

    def set_enabled(self, key, value):
        button = self.buttons.get(key)
        if button is not None and button.is_disabled() == bool(value):
            button.set_enabled(bool(value))

    def current_message(self, state):
        if self.recording:
            return "Listening to a short command"
        if self.processing:
            return "Recognizing command..."
        return self.banner if time.monotonic() < self.banner_until else state.message

    def refresh(self):
        if self.closing:
            return
        if self.entry_guard is not None and not self.entry_guard.contains(QCursor.pos()):
            self.entry_guard = None
            self.last_interaction = time.monotonic()
        if self.check_auto_collapse():
            return
        state = self.transport.snapshot()
        art = self.artwork.observe(state)
        busy = self.recording or self.processing
        message = self.current_message(state)
        if not self.expanded:
            player_label = "YT Music" if state.player == "YouTube Music" else state.player or "Muse"
            header = ("DEMO · " if state.simulated else "") + player_label
            if not state.connected:
                header = "Disconnected" + (" · DEMO" if state.simulated else "")
            if self.recording:
                header = "Listening" + (" · DEMO" if state.simulated else "")
            elif self.processing:
                header = "Recognizing command"
            self.cover.set_artwork(art)
            card = self.buttons["expand"]
            card.setAccessibleDescription(art.attribution or "Cover unavailable; select card to open controls")
            card.playback_icon = "voice" if self.recording else "offline" if not state.connected else "play" if state.playing is True else "pause" if state.playing is False else "info"
            card.update()
            self.fit(self.source, header)
            self.fit(self.title, self.display_title(state))
            detail = message if busy or time.monotonic() < self.banner_until or not state.connected else state.artist
            self.fit(self.artist, detail or "Artist not provided")
            elapsed = state.elapsed()
            known = elapsed is not None and state.duration is not None and state.duration > 0
            self.progress.setValue(round(1000 * elapsed / state.duration) if known else 0)
            self.set_enabled("expand", not busy)
            return
        self.fit(self.source, ("DEMO · " if state.simulated else "") + (state.player or "No active app"))
        self.fit(self.title, self.display_title(state))
        elapsed = state.elapsed()
        def clock(value):
            return "--:--" if value is None else f"{int(value)//60}:{int(value)%60:02d}"
        self.fit(self.time_label, f"{clock(elapsed)} / {clock(state.duration)}")
        if "toggle" in self.buttons:
            self.buttons["toggle"].set_text("Pause" if state.playing is True else "Play")
        navigation = {"hide"}
        for key in self.buttons:
            allowed = not busy and self.entry_guard is None
            if key == "toggle":
                allowed = allowed and state.toggle_action() is not None
            elif key not in navigation:
                allowed = allowed and state.can(key)
            self.set_enabled(key, allowed)

    @staticmethod
    def display_title(state):
        title = state.title or "No track information"
        # Clean the demo fixture's presentation only; never alter real metadata.
        return title.removeprefix("Demo: ") if state.simulated else title

    def command(self, op):
        if self.recording or self.processing:
            return
        self.last_interaction = time.monotonic()
        try:
            self.transport.send(op)
        except Exception as error:
            self.notice(str(error))
        self.refresh()

    def toggle(self):
        op = self.transport.snapshot().toggle_action()
        if op:
            self.command(op)
        else:
            self.notice("Play/pause unavailable. Start music on the phone first.")

    def now_playing(self):
        s = self.transport.snapshot()
        self.notice(f"{s.title or 'Title not provided'} - {s.artist or 'Artist not provided'}", 6)

    def handle_transcript(self, transcript):
        action = parse(transcript)
        if action == "now_playing":
            self.now_playing()
        elif action == "cancel":
            self.notice("Cancelled")
        elif action:
            self.command(action)
        else:
            self.notice("Try pause, resume, next song, previous song, volume up/down.", 6)

    def voice(self):
        if self.recording or self.processing:
            return
        # Deliberate activation only; no background/wake-word microphone.
        # The panel folds back down before recording, leaving its status visible.
        self.collapse()
        backend = self.config.get("voice_backend", "typed")
        if backend == "typed":
            self.dialog_active = True
            try:
                text, accepted = QInputDialog.getText(self, "Simulator voice input",
                    "Type the words a recognizer would return. No microphone is used.")
                if accepted:
                    self.handle_transcript(text)
            finally:
                self.dialog_active = False
                self.last_interaction = time.monotonic()
            return
        if backend not in {"vosk", "openai"}:
            self.notice("Unsupported voice backend in config")
            return
        if backend == "openai" and self.config.get("cloud_voice_consent") is not True:
            self.notice("Cloud speech is disabled until you explicitly opt in.")
            return
        try:
            if self.mic is None:
                from raven_framework.peripherals.microphone import Microphone
                self.mic = Microphone()
            self.mic.start_recording()
            self.recording = True
            QTimer.singleShot(max(2, min(6, int(self.config.get("record_seconds", 5)))) * 1000,
                              self.finish_recording)
            self.refresh()
        except Exception:
            self.notice("Microphone unavailable. Check device permissions/configuration.")

    def finish_recording(self):
        if not self.recording or self.closing:
            return
        self.recording = False
        try:
            audio = self.mic.stop_recording()
        except Exception:
            self.notice("Could not read microphone audio")
            return
        self.processing = True
        self.refresh()
        result = {}
        def recognize():
            try:
                result['text'] = self.transcriber.recognize(audio)
            except Exception:
                result['error'] = 'Voice recognition unavailable'
        def complete():
            if self.closing:
                return
            self.processing = False
            if "error" in result:
                self.notice(result["error"], 6)
            else:
                self.handle_transcript(result["text"])
            self.refresh()
        self.runner.run(recognize, on_complete=complete)

    def demo_switch(self):
        if self.config.get("mode") == "demo":
            self.transport.scenario("switch_app"); self.refresh()

    def lab(self):
        if self.config.get("mode") != "demo":
            return
        names = ["switch_app", "disconnect", "unsupported", "missing_metadata", "missing_artwork", "other_app", "reset"]
        self.dialog_active = True
        try:
            name, accepted = QInputDialog.getItem(self, "Demo scenarios", "Simulate:", names, editable=False)
            if accepted:
                self.transport.scenario(name); self.refresh()
        finally:
            self.dialog_active = False
            self.last_interaction = time.monotonic()

    def closeEvent(self, event):
        self.closing = True
        self.timer.stop()
        self.artwork.close()
        if self.recording and self.mic is not None:
            self.mic.stop_recording()
        self.transport.close()
        super().closeEvent(event)
