"""Original paint layer over Raven Button. SDK input/timers remain authoritative.
The selection check means a gaze/click was accepted, NOT that the phone complied.
"""
import time
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from raven_framework.components.button import Button
from raven_framework.helpers.themes import RAVEN_CORE

ACCENT = "#8CEBD4"
WHITE = "#F6FAFC"
MUTED = "#B5C3CD"
DISABLED = "#5B6872"


def icon(painter, name, cx, cy, size, color):
    """Small, dependency-free vector icons: no emoji, image downloads or logos."""
    painter.save()
    painter.translate(cx, cy)
    painter.scale(size / 32, size / 32)
    painter.setPen(QPen(QColor(color), 2.6, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    def triangle(points):
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(color), 2.6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    name = {'line_previous':'previous','saved_previous':'previous','line_next':'next',
            'saved_next':'next','cancel_identify':'offline','confirm_delete':'offline',
            'timing_minus':'back','timing_plus':'forward','follow':'play',
            'listen':'mic','confirm_mic':'mic','fixture':'play','delete':'offline',
            'clear':'offline'}.get(name,name)
    if name in {'lyrics','result_lyrics'}:
        for y,width in [(-9,12),(0,9),(9,12)]: line(-12,y,width,y)
    elif name in {'identify','discoveries','link','spotify_link','youtube_link'}:
        painter.drawEllipse(QPointF(-3,-3),9,9)
        line(4,4,13,13)
    elif name == 'save_discovery':
        path=QPainterPath(QPointF(-9,-13))
        for x,y in [(9,-13),(9,13),(0,6),(-9,13),(-9,-13)]: path.lineTo(x,y)
        painter.drawPath(path)
    elif name in {"play", "toggle"}:
        triangle([(-8, -12), (-8, 12), (12, 0)])
    elif name == "pause":
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(-10, -12, 7, 24), 2, 2)
        painter.drawRoundedRect(QRectF(3, -12, 7, 24), 2, 2)
    elif name in {"next", "previous", "forward", "back"}:
        sign = -1 if name in {"previous", "back"} else 1
        if name in {"next", "previous"}:
            triangle([(sign * -11, -10), (sign * -11, 10), (sign * 6, 0)])
            line(sign * 11, -11, sign * 11, 11)
        else:
            triangle([(sign * -14, -9), (sign * -14, 9), (sign * -1, 0)])
            triangle([(sign * 0, -9), (sign * 0, 9), (sign * 13, 0)])
    elif name in {"voice", "mic"}:
        painter.drawRoundedRect(QRectF(-5, -13, 10, 19), 5, 5)
        path = QPainterPath(QPointF(-11, 0)); path.cubicTo(-11, 16, 11, 16, 11, 0)
        painter.drawPath(path); line(0, 12, 0, 16); line(-5, 16, 5, 16)
    elif name in {"tools", "modes"}:
        for y, knob in [(-9, -5), (0, 6), (9, -2)]:
            line(-13, y, 13, y)
            painter.setBrush(QColor("#060B0E"))
            painter.drawEllipse(QPointF(knob, y), 3.5, 3.5)
    elif name in {"expand", "hide"}:
        sign = -1 if name == "expand" else 1
        line(-9, sign * -3, 0, sign * 5); line(0, sign * 5, 9, sign * -3)
    elif name == "back_page":
        line(12, 0, -12, 0); line(-12, 0, -3, -9); line(-12, 0, -3, 9)
    elif name in {"volume_up", "volume_down"}:
        path = QPainterPath(QPointF(-13, -4))
        for x, y in [(-7, -4), (0, -11), (0, 11), (-7, 4), (-13, 4)]:
            path.lineTo(x, y)
        path.closeSubpath(); painter.drawPath(path)
        line(6, 0, 15, 0)
        if name == "volume_up": line(10.5, -4.5, 10.5, 4.5)
    elif name == "shuffle":
        path = QPainterPath(QPointF(-13, -9)); path.cubicTo(0, -9, 0, 9, 13, 9)
        painter.drawPath(path)
        path = QPainterPath(QPointF(-13, 9)); path.cubicTo(0, 9, 0, -9, 13, -9)
        painter.drawPath(path)
        line(8, -14, 13, -9); line(13, -9, 8, -4)
        line(8, 4, 13, 9); line(13, 9, 8, 14)
    elif name == "repeat":
        path = QPainterPath(QPointF(-12, 3)); path.lineTo(-12, -5)
        path.quadTo(-12, -10, -6, -10); path.lineTo(12, -10)
        painter.drawPath(path); line(7, -15, 12, -10); line(12, -10, 7, -5)
        path = QPainterPath(QPointF(12, -3)); path.lineTo(12, 5)
        path.quadTo(12, 10, 6, 10); path.lineTo(-12, 10)
        painter.drawPath(path); line(-7, 5, -12, 10); line(-12, 10, -7, 15)
    elif name == "check":
        line(-11, 0, -3, 8); line(-3, 8, 12, -9)
    elif name == "offline":
        line(-10, -10, 10, 10); line(-10, 10, 10, -10)
    else:
        painter.drawEllipse(QPointF(0, 0), 13, 13)
        line(0, -1, 0, 7); painter.drawPoint(QPointF(0, -7))
    painter.restore()


class GazeTarget(Button):
    """Same SDK hit box and dwell events, with clear icons and progress feedback."""
    def __init__(self, key, label, width, height, dwell_ms=1100, primary=False):
        self.key = key
        self.primary = primary
        self.selected_until = 0.0
        self.icon_name = key
        self.playback_icon = "play"
        super().__init__(center_text=label, width=width, height=height, text_size=23,
            background_color="#020506", text_color=WHITE, use_fill_dwell=False,
            use_gradient_border=False, outline_width=1, corner_radius=18,
            scale_by=0.0, delay_time=250, dwell_time=dwell_ms)
        self.setAccessibleName(label or "Open music controls")
        self._confirm_timer = QTimer(self)
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.timeout.connect(self.update)

    def confirm_selection(self):
        self.selected_label = self.text
        self.selected_until = time.monotonic() + .4
        self.update()
        self._confirm_timer.start(420)

    def selected(self):
        return time.monotonic() < self.selected_until

    def dwell_fraction(self):
        if self.is_disabled() or not self.underMouse():
            return 0.0
        return max(0.0, min(1.0, self.progress / max(1.0, self.max_progress)))

    def set_text(self, new_text):
        super().set_text(new_text)
        self.setAccessibleName(new_text or "Open music controls")
        if self.key == "toggle":
            self.icon_name = "pause" if new_text.lower() == "pause" else "play"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        disabled = self.is_disabled()
        focused = self.underMouse() and not disabled
        selected = self.selected() and not disabled
        compact = self.key == "expand"
        border = ACCENT if focused or selected else "#608078" if self.primary else "#60727D"
        if disabled: border = "#27343D"
        painter.setBrush(QColor("#091C18" if self.primary and not disabled else "#020506"))
        painter.setPen(QPen(QColor(border), 2.7 if focused or selected else 1.3))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 18, 18)
        ink = DISABLED if disabled else ACCENT if self.primary or focused else WHITE
        if compact:
            cx, cy, radius = self.width()-26, 21, 12
            icon(painter, "expand", cx, cy, 18, ink)
            icon(painter, self.playback_icon, 205, 21, 13, MUTED if not disabled else DISABLED)
        else:
            cx, cy, radius = self.width()/2, 35, 25
            icon(painter, "check" if selected else self.icon_name, cx, cy, 30, ink)
            # Use the font supplied by the Raven SDK for platform consistency.
            font = QFont(self.font)
            font.setPixelSize(RAVEN_CORE.fonts.body.size)  # Theme Body (28 px), per AGENTS.md.
            font.setWeight(QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(QColor(DISABLED if disabled else WHITE))
            label = "Done" if selected else self.text
            label = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, self.width()-12)
            painter.drawText(QRectF(6, 62, self.width()-12, 36), Qt.AlignmentFlag.AlignCenter, label)
            if disabled:
                painter.setPen(QPen(QColor(DISABLED), 2))
                painter.drawLine(QPointF(self.width()-20, 13), QPointF(self.width()-13, 20))
        # The ring uses the SDK's real dwell progress, never an independent timer.
        fraction = self.dwell_fraction()
        if focused and not selected and fraction > 0:
            ring = QRectF(cx-radius, cy-radius, radius*2, radius*2)
            painter.setPen(QPen(QColor("#253F39"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring)
            painter.setPen(QPen(QColor(ACCENT), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(ring, 90*16, -round(360*16*fraction))
        painter.end()
