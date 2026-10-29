from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QPen, QPainterPath, QFont, QBrush


def make_logo(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#3b82f6"))
    g.setColorAt(1, QColor("#8b5cf6"))
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(size * .04, size * .04, size * .92, size * .92), size * .22, size * .22)
    f = QFont("Segoe UI", int(size * .42), QFont.Black)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, size * .02, size, size * .8), Qt.AlignCenter, "P")
    path = QPainterPath(QPointF(size * .2, size * .82))
    path.cubicTo(size * .35, size * .66, size * .55, size * .96, size * .8, size * .74)
    pen = QPen(QColor("#ffd166"), size * .055, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return pm
