"""Post-its en pantalla: cada nota es una ventanita amarilla que puedes arrastrar.
Recuerda dónde la dejaste. ✓ = hecha (se borra).
Normalmente solo se ven mientras Pingu tiene el foco (ver Tablero.mostrar)."""
import random

from PyQt5.QtCore import Qt, QPoint, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QDesktopWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import notas

ANCHO = 190
COLORES = {   # (papel, franja de arriba)
    "nota":         ("#FFF59D", "#FBC02D"),   # amarillo
    "recordatorio": ("#FFCC80", "#F57C00"),   # naranja: tiene hora
}
SOMBRA = 4


class PostIt(QWidget):
    def __init__(self, nota: dict, on_hecho, on_movido):
        super().__init__()
        self.nota = nota
        self._on_hecho = on_hecho
        self._on_movido = on_movido
        self._arrastre = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)   # que no te robe el foco
        self.setFixedWidth(ANCHO)

        self.cabecera = QLabel()
        self.cabecera.setStyleSheet("color: #5D4037; font-size: 11px; font-weight: bold;")
        hecho = QPushButton("✓")
        hecho.setFixedSize(20, 20)
        hecho.setCursor(Qt.PointingHandCursor)
        hecho.setToolTip("Hecho (borrar)")
        hecho.setStyleSheet("QPushButton { border: none; color: #5D4037; font-size: 14px;"
                            " font-weight: bold; background: transparent; }"
                            "QPushButton:hover { color: #2E7D32; }")
        hecho.clicked.connect(lambda: self._on_hecho(self.nota))

        self.texto = QLabel()
        self.texto.setWordWrap(True)
        self.texto.setStyleSheet("color: #212121; font-size: 13px;")

        arriba = QHBoxLayout()
        arriba.setContentsMargins(0, 0, 0, 0)
        arriba.addWidget(self.cabecera, 1)
        arriba.addWidget(hecho)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10 + SOMBRA, 10 + SOMBRA)
        layout.setSpacing(6)
        layout.addLayout(arriba)
        layout.addWidget(self.texto)

        self.setCursor(Qt.OpenHandCursor)
        self.actualizar(nota)
        self._colocar()

    def actualizar(self, nota: dict):
        """Repinta con los datos de la nota (texto, hora del aviso)."""
        self.nota = nota
        hora = notas.hora_texto(nota)
        self._colores = COLORES["recordatorio" if hora else "nota"]
        self.cabecera.setText(f"⏰ {hora}" if hora else "📝")
        self.texto.setText(nota["texto"])
        self.adjustSize()
        self.update()

    def _colocar(self):
        """Donde la dejaste; si es nueva, arriba a la derecha con un poco de desorden."""
        pantalla = QDesktopWidget().availableGeometry()
        pos = self.nota.get("pos")
        if pos:
            x, y = pos
        else:
            x = pantalla.right() - ANCHO - 30 - random.randint(0, 40)
            y = pantalla.top() + 40 + random.randint(0, 200)
        # Que no quede fuera si cambiaste de monitor
        x = max(pantalla.left(), min(x, pantalla.right() - ANCHO))
        y = max(pantalla.top(), min(y, pantalla.bottom() - 60))
        self.move(x, y)

    # --- Dibujo: papel con sombra y franja de "celo" arriba ---
    def paintEvent(self, event):
        papel, franja = self._colores
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width() - SOMBRA, self.height() - SOMBRA)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawRoundedRect(r.translated(SOMBRA, SOMBRA), 3, 3)
        p.setBrush(QColor(papel))
        p.setPen(QPen(QColor(franja), 1))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(franja))
        p.drawRect(QRectF(r.left() + 1, r.top() + 1, r.width() - 2, 3))

    # --- Arrastrar ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._arrastre = event.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._arrastre is not None:
            self.move(event.globalPos() - self._arrastre)

    def mouseReleaseEvent(self, event):
        if self._arrastre is not None:
            self._arrastre = None
            self.setCursor(Qt.OpenHandCursor)
            self._on_movido(self.nota, self.x(), self.y())


class Tablero:
    """Mantiene un post-it por nota, al día con la lista de notas.
    Las ventanas existen siempre; mostrar() decide si se ven."""

    def __init__(self, on_hecho, on_movido):
        self._on_hecho = on_hecho
        self._on_movido = on_movido
        self._postits = {}   # id de la nota -> PostIt
        self.a_la_vista = False

    def mostrar(self, si: bool):
        if si == self.a_la_vista:
            return
        self.a_la_vista = si
        for postit in self._postits.values():
            postit.setVisible(si)

    def sincronizar(self, lista: list):
        vivas = {n["id"]: n for n in lista}
        for nid in list(self._postits):
            if nid not in vivas:
                self._postits.pop(nid).close()
        for nid, nota in vivas.items():
            if nid in self._postits:
                self._postits[nid].actualizar(nota)
            else:
                postit = PostIt(nota, self._on_hecho, self._on_movido)
                self._postits[nid] = postit
                postit.setVisible(self.a_la_vista)

    def cerrar_todos(self):
        for postit in self._postits.values():
            postit.close()
        self._postits.clear()
