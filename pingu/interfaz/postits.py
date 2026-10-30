"""Post-its en pantalla: cada nota es una ventanita de colores que puedes arrastrar.
Recuerda dónde la dejaste y de qué tamaño.
- Arrastrar: mover · esquina de abajo a la derecha: cambiar el tamaño
- Doble clic: editar · clic derecho: menú (editar, copiar, color, aviso, hecho)
- 📋 = copiar el texto · ✓ = hecha (se borra)
Normalmente solo se ven mientras Pingu tiene el foco (ver Tablero.mostrar)."""
import random

from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QApplication, QDesktopWidget, QHBoxLayout, QLabel, QMenu,
                             QPushButton, QVBoxLayout, QWidget)

from pingu import notas

# Medidas a tamaño normal; se multiplican por ESCALA (⚙️ Configuración → tamaño de los post-its)
ANCHO = 190                 # ancho de un post-it nuevo
ANCHO_MIN, ANCHO_MAX = 120, 600
ALTO_MAX = 600
SOMBRA = 4
ESQUINA = 14                # zona de la esquina para redimensionar
ESCALA = 1.0                # la pone Tablero.poner_escala


def px(n: float) -> int:
    """Medida a la escala de los post-its."""
    return max(1, round(n * ESCALA))


def _boton(texto: str, ayuda: str, hover: str) -> QPushButton:
    b = QPushButton(texto)
    b.setFixedSize(px(20), px(20))
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(ayuda)
    b.setStyleSheet(f"QPushButton {{ border: none; color: #5D4037; font-size: {px(13)}px;"
                    " font-weight: bold; background: transparent; }"
                    f"QPushButton:hover {{ color: {hover}; }}")
    return b


def _muestra(color: str) -> QIcon:
    """Cuadradito de color para el menú."""
    _, papel, franja = notas.COLORES[color]
    pix = QPixmap(14, 14)
    pix.fill(QColor(papel))
    p = QPainter(pix)
    p.setPen(QColor(franja))
    p.drawRect(0, 0, 13, 13)
    p.end()
    return QIcon(pix)


class PostIt(QWidget):
    def __init__(self, nota: dict, acciones: dict):
        super().__init__()
        self.nota = nota
        self._acc = acciones     # hecho(nota), editar(nota), avisar(nota, min), cambiado()
        self._arrastre = None    # desplazamiento del ratón al mover
        self._redim = None       # (pos del ratón, tamaño) al empezar a redimensionar

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)   # que no te robe el foco
        self.setMouseTracking(True)                      # cursor de redimensionar en la esquina

        self.cabecera = QLabel()
        self.cabecera.setStyleSheet(f"color: #5D4037; font-size: {px(11)}px; font-weight: bold;")
        copiar = _boton("📋", "Copiar el texto", "#1565C0")
        copiar.setStyleSheet(copiar.styleSheet() + f"QPushButton {{ font-size: {px(11)}px; }}")
        copiar.clicked.connect(self._copiar)
        hecho = _boton("✓", "Hecho (borrar)", "#2E7D32")
        hecho.clicked.connect(lambda: self._acc["hecho"](self.nota))

        self.texto = QLabel()
        self.texto.setWordWrap(True)
        self.texto.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.texto.setStyleSheet(f"color: #212121; font-size: {px(13)}px;")
        self.texto.setAttribute(Qt.WA_TransparentForMouseEvents)   # arrastrar desde el texto

        arriba = QHBoxLayout()
        arriba.setContentsMargins(0, 0, 0, 0)
        arriba.setSpacing(px(2))
        arriba.addWidget(self.cabecera, 1)
        arriba.addWidget(copiar)
        arriba.addWidget(hecho)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(10), px(4), px(10) + SOMBRA, px(10) + SOMBRA)
        layout.setSpacing(px(6))
        layout.addLayout(arriba)
        layout.addWidget(self.texto, 1)

        self.setCursor(Qt.OpenHandCursor)
        self.actualizar(nota)
        self._colocar()

    # --- Contenido ---
    def actualizar(self, nota: dict):
        """Repinta con los datos de la nota (texto, hora del aviso, color, tamaño)."""
        self.nota = nota
        hora = notas.hora_texto(nota)
        self._colores = notas.COLORES[notas.color_de(nota)][1:]
        self.cabecera.setText(f"⏰ {hora}" if hora else "📝")
        self.texto.setText(nota["texto"])
        self._ajustar_tamano()
        self.update()

    def _alto_minimo(self, ancho: int) -> int:
        alto = self.heightForWidth(ancho)
        return alto if alto > 0 else self.sizeHint().height()

    def _ajustar_tamano(self, ancho=None, alto=None):
        """Ancho/alto pedidos (o los guardados); nunca más bajo de lo que ocupa el texto."""
        tam = self.nota.get("tam") or [ANCHO, 0]   # guardado a tamaño normal
        ancho = max(px(ANCHO_MIN), min(px(ANCHO_MAX), ancho if ancho is not None else px(tam[0])))
        alto = alto if alto is not None else px(tam[1])
        alto = max(self._alto_minimo(ancho), min(px(ALTO_MAX), alto))
        self.resize(ancho, alto)

    def _colocar(self):
        """Donde la dejaste; si es nueva, arriba a la derecha con un poco de desorden."""
        pantalla = QDesktopWidget().availableGeometry()
        pos = self.nota.get("pos")
        if pos:
            x, y = pos
        else:
            x = pantalla.right() - self.width() - 30 - random.randint(0, 40)
            y = pantalla.top() + 40 + random.randint(0, 200)
        # Que no quede fuera si cambiaste de monitor
        x = max(pantalla.left(), min(x, pantalla.right() - self.width()))
        y = max(pantalla.top(), min(y, pantalla.bottom() - 60))
        self.move(x, y)

    def _copiar(self):
        QApplication.clipboard().setText(self.nota["texto"])
        self.cabecera.setText("📋 ¡Copiado!")
        QTimer.singleShot(1200, lambda: self.actualizar(self.nota))

    # --- Dibujo: papel con sombra, franja de "celo" arriba y esquina para redimensionar ---
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
        # Rayitas de la esquina
        p.setPen(QPen(QColor(franja), 1.2))
        for d in (4, 8, 12):
            p.drawLine(QPointF(r.right() - d, r.bottom() - 2), QPointF(r.right() - 2, r.bottom() - d))

    def _en_esquina(self, pos) -> bool:
        return (pos.x() >= self.width() - SOMBRA - px(ESQUINA)
                and pos.y() >= self.height() - SOMBRA - px(ESQUINA))

    # --- Ratón: arrastrar, redimensionar, doble clic, menú ---
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._en_esquina(event.pos()):
            self._redim = (event.globalPos(), self.size())
        else:
            self._arrastre = event.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._redim is not None:
            inicio, tam = self._redim
            delta = event.globalPos() - inicio
            self._ajustar_tamano(tam.width() + delta.x(), tam.height() + delta.y())
        elif self._arrastre is not None:
            self.move(event.globalPos() - self._arrastre)
        else:
            self.setCursor(Qt.SizeFDiagCursor if self._en_esquina(event.pos()) else Qt.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        if self._redim is not None:
            self._redim = None
            self.nota["tam"] = [round(self.width() / ESCALA), round(self.height() / ESCALA)]
            self._acc["cambiado"]()
        elif self._arrastre is not None:
            self._arrastre = None
            self.setCursor(Qt.OpenHandCursor)
            self.nota["pos"] = [self.x(), self.y()]
            self._acc["cambiado"]()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._en_esquina(event.pos()):
            self._acc["editar"](self.nota)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("✏️ Editar…", lambda: self._acc["editar"](self.nota))
        menu.addAction("📋 Copiar el texto", self._copiar)
        colores = menu.addMenu("🎨 Color")
        actual = notas.color_de(self.nota)
        for clave, (nombre, _, _) in notas.COLORES.items():
            accion = colores.addAction(_muestra(clave), nombre, lambda c=clave: self._poner_color(c))
            accion.setCheckable(True)
            accion.setChecked(clave == actual)
        aviso = menu.addMenu("⏰ Avisarme")
        for nombre, minutos in notas.POSPONER:
            aviso.addAction(nombre, lambda m=minutos: self._acc["avisar"](self.nota, m))
        if self.nota.get("aviso"):
            aviso.addAction("🔕 Quitar el aviso", lambda: self._acc["avisar"](self.nota, None))
        if self.nota.get("tam"):
            menu.addAction("↩️ Tamaño normal", self._tamano_normal)
        menu.addSeparator()
        menu.addAction("✅ Hecho (borrar)", lambda: self._acc["hecho"](self.nota))
        menu.exec_(event.globalPos())

    def _poner_color(self, color: str):
        self.nota["color"] = color
        self.actualizar(self.nota)
        self._acc["cambiado"]()

    def _tamano_normal(self):
        self.nota.pop("tam", None)
        self._ajustar_tamano()
        self._acc["cambiado"]()


class Tablero:
    """Mantiene un post-it por nota, al día con la lista de notas.
    Las ventanas existen siempre; mostrar() decide si se ven.
    acciones: hecho(nota), editar(nota), avisar(nota, minutos), cambiado()"""

    def __init__(self, **acciones):
        self._acciones = acciones
        self._postits = {}   # id de la nota -> PostIt
        self._lista = []
        self.a_la_vista = False

    def poner_escala(self, escala: float):
        """Cambia el tamaño de todos los post-its (se vuelven a crear con la escala nueva)."""
        global ESCALA
        if abs(escala - ESCALA) < 0.001:
            return
        ESCALA = escala
        self.cerrar_todos()
        self.sincronizar(self._lista)

    def mostrar(self, si: bool):
        if si == self.a_la_vista:
            return
        self.a_la_vista = si
        for postit in self._postits.values():
            postit.setVisible(si)

    def sincronizar(self, lista: list):
        self._lista = lista
        vivas = {n["id"]: n for n in lista}
        for nid in list(self._postits):
            if nid not in vivas:
                self._postits.pop(nid).close()
        for nid, nota in vivas.items():
            if nid in self._postits:
                self._postits[nid].actualizar(nota)
            else:
                postit = PostIt(nota, self._acciones)
                self._postits[nid] = postit
                postit.setVisible(self.a_la_vista)

    def cerrar_todos(self):
        for postit in self._postits.values():
            postit.close()
        self._postits.clear()
