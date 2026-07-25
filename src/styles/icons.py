"""Simple line icons drawn with QPainter, so they are always visible
on the dark theme regardless of the platform icon set."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from styles.theme import ACCENT_COLOR, TEXT_COLOR

# Icons are drawn in a 40x40 coordinate space and scaled down by the toolbar
_CANVAS = 40
_PEN_WIDTH = 2.6


def _make_icon(draw):
    pixmap = QPixmap(_CANVAS, _CANVAS)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(TEXT_COLOR), _PEN_WIDTH, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    draw(painter)
    painter.end()

    return QIcon(pixmap)


def open_icon():
    """Folder."""

    def draw(p):
        path = QPainterPath()
        path.moveTo(6, 13)
        path.lineTo(15, 13)
        path.lineTo(19, 17)
        path.lineTo(34, 17)
        path.lineTo(34, 31)
        path.lineTo(6, 31)
        path.closeSubpath()
        p.drawPath(path)

    return _make_icon(draw)


def save_icon():
    """Floppy disk."""

    def draw(p):
        path = QPainterPath()
        path.moveTo(8, 8)
        path.lineTo(27, 8)
        path.lineTo(32, 13)
        path.lineTo(32, 32)
        path.lineTo(8, 32)
        path.closeSubpath()
        p.drawPath(path)
        p.drawRect(QRectF(14, 8, 11, 7))
        p.drawRect(QRectF(13, 21, 14, 11))

    return _make_icon(draw)


def save_all_icon():
    """Two stacked floppy disks."""

    def draw(p):
        p.drawRoundedRect(QRectF(13, 7, 20, 20), 2, 2)
        path = QPainterPath()
        path.moveTo(8, 13)
        path.lineTo(8, 33)
        path.lineTo(28, 33)
        p.drawPath(path)
        p.drawRect(QRectF(19, 7, 8, 6))

    return _make_icon(draw)


def app_icon():
    """Application icon - accent tile with 'Dx'."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(ACCENT_COLOR))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 12, 12)

    font = QFont("Segoe UI", 26)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(2, 2, 60, 60), Qt.AlignCenter, "Dx")
    painter.end()

    return QIcon(pixmap)


def export_icon():
    """Arrow up out of a tray."""

    def draw(p):
        p.drawLine(20, 8, 20, 24)
        p.drawLine(13, 15, 20, 8)
        p.drawLine(27, 15, 20, 8)
        path = QPainterPath()
        path.moveTo(8, 23)
        path.lineTo(8, 32)
        path.lineTo(32, 32)
        path.lineTo(32, 23)
        p.drawPath(path)

    return _make_icon(draw)


def anonymize_icon():
    """Person with a strike-through."""

    def draw(p):
        p.drawEllipse(QRectF(14, 7, 12, 12))
        path = QPainterPath()
        path.moveTo(8, 33)
        path.cubicTo(8, 24, 32, 24, 32, 33)
        p.drawPath(path)
        p.drawLine(9, 9, 31, 31)

    return _make_icon(draw)


def compare_icon():
    """Two panes side by side."""

    def draw(p):
        p.drawRoundedRect(QRectF(7, 9, 11, 22), 2, 2)
        p.drawRoundedRect(QRectF(22, 9, 11, 22), 2, 2)

    return _make_icon(draw)
