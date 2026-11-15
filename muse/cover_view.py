"""Non-interactive 64px artwork; the parent card remains the only gaze target."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from .artwork import ArtResult


class CoverView(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.result = ArtResult()
        self.image = QImage()
        self.setAccessibleName("Cover art unavailable")

    def set_artwork(self, result):
        if result == self.result:
            return
        self.result = result
        self.image = QImage.fromData(result.data) if result.data else QImage()
        self.setAccessibleName("Cover art unavailable" if self.image.isNull()
            else "Metadata-matched cover art" if result.source == "matched" else "Song cover art")
        self.setToolTip(result.attribution or "No cover art available")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 64, 64), 8, 8)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor("#142723"))
        if not self.image.isNull():
            p.drawImage(QRectF(0, 0, 64, 64), self.image)
        else:
            p.setPen(QPen(QColor("#8BAEA4"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(29, 39), QPointF(29, 20))
            p.drawLine(QPointF(29, 20), QPointF(43, 17))
            p.drawLine(QPointF(43, 17), QPointF(43, 36))
            p.setBrush(QColor("#8BAEA4"))
            p.drawEllipse(QRectF(19, 37, 10, 7))
            p.drawEllipse(QRectF(33, 34, 10, 7))
        if self.result.source == "matched" and not self.image.isNull():
            # Amber marker distinguishes inferred online art from phone artwork.
            p.setPen(QPen(QColor("#07110F"), 2))
            p.setBrush(QColor("#F1BF6B"))
            p.drawEllipse(QPointF(56, 56), 4, 4)
        p.end()
