"""Globo de texto con forma de bocadillo de cómic."""
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush
from PyQt5.QtCore import Qt, QRectF, QPointF


class BubbleLabel(QLabel):
    """Bocadillo de cómic: cuerpo redondeado + piquito que apunta al pingüino.
    Se dibuja a mano (paintEvent) para que la forma funcione en Linux."""

    # Paletas predefinidas: (fondo, borde)
    THEME_DEFAULT = ("#FFFDE7", "#F9A825")   # amarillo — normal / chiste
    THEME_ERROR   = ("#FFEBEE", "#E53935")   # rojo     — VPN caída
    THEME_OK      = ("#E8F5E9", "#43A047")   # verde    — VPN recuperada
    THEME_MSG     = ("#E3F2FD", "#1E88E5")   # azul     — mensajes de Rocket.Chat
    THEME_CALM    = ("#F3E5F5", "#8E24AA")   # morado   — pausas

    TAIL_H  = 14   # alto del piquito
    TAIL_W  = 20   # ancho de su base
    SHADOW  = 3    # desplazamiento de la sombra
    RADIUS  = 16

    def __init__(self, text: str, theme: tuple = None, on_click=None, on_close=None):
        super().__init__(text)
        self._bg, self._border = theme or self.THEME_DEFAULT
        self._on_click = on_click
        self._on_close = on_close
        self.tail_x = None   # x del piquito (relativa al globo); None = centro
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWordWrap(True)
        self.setMaximumWidth(320)
        # Abajo dejamos sitio para el piquito; a la derecha y abajo, para la sombra
        pad = 12
        self.setStyleSheet(
            "background-color: transparent;"
            "color: #1A1A1A;"
            "font-size: 13px;"
            f"padding: {pad}px {16 + self.SHADOW}px {pad + self.TAIL_H + self.SHADOW}px 16px;"
        )
        if on_click:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("Click para abrir")

    def fit(self):
        """Ajusta el tamaño al texto. (adjustSize de Qt con wordWrap deja el globo
        demasiado estrecho y parte líneas cortas.)"""
        self.ensurePolished()   # aplica el font-size de la hoja de estilos
        fm = self.fontMetrics()
        m = self.contentsMargins()
        pad_h = 16 + 16 + self.SHADOW + m.left() + m.right() + 6
        text_w = max((fm.horizontalAdvance(line) for line in self.text().splitlines()), default=0)
        w = min(text_w + pad_h, self.maximumWidth())
        self.setFixedWidth(w)
        self.setFixedHeight(self.heightForWidth(w))

    def _shape(self) -> QPainterPath:
        m = 2
        body = QRectF(m, m, self.width() - 2 * m - self.SHADOW,
                      self.height() - 2 * m - self.TAIL_H - self.SHADOW)
        path = QPainterPath()
        path.addRoundedRect(body, self.RADIUS, self.RADIUS)

        # Piquito: base pegada al borde inferior, punta un poco ladeada (estilo cómic)
        tx = self.tail_x if self.tail_x is not None else body.center().x()
        tx = max(body.left() + self.RADIUS + self.TAIL_W / 2,
                 min(tx, body.right() - self.RADIUS - self.TAIL_W / 2))
        base_y = body.bottom() - 1
        tail = QPainterPath()
        tail.moveTo(QPointF(tx - self.TAIL_W / 2, base_y))
        tail.quadTo(QPointF(tx - 2, base_y + self.TAIL_H * 0.5),
                    QPointF(tx - 6, base_y + self.TAIL_H))
        tail.quadTo(QPointF(tx + 4, base_y + self.TAIL_H * 0.6),
                    QPointF(tx + self.TAIL_W / 2, base_y))
        tail.closeSubpath()
        return path.united(tail)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shape = self._shape()

        # Sombra suave
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawPath(shape.translated(self.SHADOW, self.SHADOW))

        # Globo con borde continuo (cuerpo + piquito en un solo trazo)
        p.setBrush(QBrush(QColor(self._bg)))
        p.setPen(QPen(QColor(self._border), 2))
        p.drawPath(shape)
        p.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        event.accept()
        # Primero se cierra este globo y después se hace la acción del click,
        # por si la acción enseña otro globo (si no, este volvería a salir)
        if self._on_close:
            self._on_close()   # el pingüino lo cierra y recupera el foco
        else:
            self.hide()
        if self._on_click and event.button() == Qt.LeftButton:
            self._on_click()
