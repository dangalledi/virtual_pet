"""Notas y recordatorios (post-its del pingüino), guardados en notas.json.

- Recordatorio: texto + hora de aviso. Cuando avisa, desaparece.
- Nota: se queda en la lista hasta que la marcas como hecha. Puede llevar aviso;
  cuando avisa, sigue en la lista (sin aviso).
"""
import datetime
import json
import time

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                             QLabel, QPlainTextEdit, QPushButton, QTimeEdit, QVBoxLayout)

from pingu.utils import BASE_DIR, log

NOTAS_FILE = BASE_DIR / "notas.json"

# Opciones de "cuándo" en el diálogo: (texto, minutos). None = sin aviso, -1 = a una hora
CUANDO = [("Sin aviso", None), ("En 5 min", 5), ("En 15 min", 15), ("En 30 min", 30),
          ("En 1 hora", 60), ("En 2 horas", 120), ("A las…", -1)]
POSPONER = [("En 15 min", 15), ("En 30 min", 30), ("En 1 hora", 60)]

# Colores de los post-its: clave -> (nombre, papel, franja de arriba)
COLORES = {
    "amarillo": ("Amarillo", "#FFF59D", "#FBC02D"),
    "naranja":  ("Naranja",  "#FFCC80", "#F57C00"),
    "rosa":     ("Rosa",     "#F8BBD0", "#EC407A"),
    "verde":    ("Verde",    "#C5E1A5", "#7CB342"),
    "azul":     ("Azul",     "#B3E5FC", "#039BE5"),
    "lila":     ("Lila",     "#D1C4E9", "#7E57C2"),
}


def color_de(nota: dict) -> str:
    """El color elegido; si no hay, naranja si tiene aviso y amarillo si no."""
    if nota.get("color") in COLORES:
        return nota["color"]
    return "naranja" if nota.get("aviso") else "amarillo"


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def cargar() -> list:
    try:
        notas = json.loads(NOTAS_FILE.read_text())
        return [n for n in notas if isinstance(n, dict) and n.get("texto")]
    except (OSError, ValueError):
        return []


def guardar(notas: list):
    try:
        NOTAS_FILE.write_text(json.dumps(notas, indent=2, ensure_ascii=False))
    except OSError as e:
        log(f"No se pudo guardar {NOTAS_FILE.name}: {e}")


def nueva(notas: list, texto: str, aviso, fija: bool, color=None) -> dict:
    """Añade una nota (fija=True) o un recordatorio (fija=False). aviso: datetime o None."""
    nota = {"id": int(time.time() * 1000), "texto": texto.strip(), "fija": fija,
            "aviso": aviso.isoformat(timespec="minutes") if aviso else None}
    if color:
        nota["color"] = color
    notas.append(nota)
    guardar(notas)
    log(f"[NOTAS] {'Nota' if fija else 'Recordatorio'}: {nota['texto']!r} aviso={nota['aviso']}")
    return nota


def hora_aviso(nota: dict):
    try:
        return datetime.datetime.fromisoformat(nota["aviso"]) if nota.get("aviso") else None
    except ValueError:
        return None


def poner_aviso(notas: list, nota: dict, aviso):
    nota["aviso"] = aviso.isoformat(timespec="minutes") if aviso else None
    guardar(notas)


def borrar(notas: list, nota: dict):
    if nota in notas:
        notas.remove(nota)
        guardar(notas)


def vencidas(notas: list) -> list:
    """Saca los avisos que ya tocan: los recordatorios se borran y las notas pierden el aviso.
    Devuelve [(texto, hora_prevista)]."""
    ahora = datetime.datetime.now()
    salen = []
    for nota in list(notas):
        cuando = hora_aviso(nota)
        if cuando and cuando <= ahora:
            salen.append((nota["texto"], cuando))
            if nota.get("fija"):
                nota["aviso"] = None
            else:
                notas.remove(nota)
    if salen:
        guardar(notas)
    return sorted(salen, key=lambda s: s[1])


def ordenadas(notas: list) -> list:
    """Primero las que tienen aviso (la más próxima antes), luego el resto por antigüedad."""
    lejos = datetime.datetime.max
    return sorted(notas, key=lambda n: (hora_aviso(n) or lejos, n.get("id", 0)))


def en_minutos(minutos: int) -> datetime.datetime:
    return (datetime.datetime.now() + datetime.timedelta(minutes=minutos)).replace(second=0,
                                                                                   microsecond=0)


def a_las(hora: QTime) -> datetime.datetime:
    """La próxima vez que sean esas HH:MM (hoy, o mañana si ya han pasado)."""
    ahora = datetime.datetime.now()
    cuando = ahora.replace(hour=hora.hour(), minute=hora.minute(), second=0, microsecond=0)
    return cuando if cuando > ahora else cuando + datetime.timedelta(days=1)


def hora_texto(nota: dict) -> str:
    """"11:30" (o "29/10 11:30" si no es hoy); "" si no tiene aviso."""
    cuando = hora_aviso(nota)
    if not cuando:
        return ""
    return cuando.strftime("%H:%M" if cuando.date() == datetime.date.today() else "%d/%m %H:%M")


def etiqueta(nota: dict, largo: int = 40) -> str:
    """Línea para el menú: "⏰ 11:30 · llamar a Marta" o "📝 revisar backup"."""
    texto = " ".join(nota["texto"].split())
    if len(texto) > largo:
        texto = texto[:largo - 1] + "…"
    hora = hora_texto(nota)
    return f"⏰ {hora} · {texto}" if hora else f"📝 {texto}"


def texto_lista(notas: list) -> str:
    if not notas:
        return "📝 No tienes notas ni recordatorios"
    return "📝 Tus notas:\n\n" + "\n".join(etiqueta(n, 60) for n in ordenadas(notas))


# ---------------------------------------------------------------------------
# Diálogo para escribir una nota / recordatorio
# ---------------------------------------------------------------------------
class _Texto(QPlainTextEdit):
    """Caja de texto: Enter = salto de línea, Ctrl+Enter = guardar."""

    def __init__(self, al_guardar):
        super().__init__()
        self._al_guardar = al_guardar

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self._al_guardar()
            return
        super().keyPressEvent(event)


class DialogoNota(QDialog):
    """Nueva nota / recordatorio, o editar una que ya existe (nota=...)."""

    def __init__(self, recordatorio: bool, parent=None, nota: dict = None):
        super().__init__(parent)
        editando = nota is not None
        if editando:
            self.setWindowTitle("✏️ Editar nota")
        else:
            self.setWindowTitle("⏰ Recuérdame" if recordatorio else "📝 Nueva nota")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(380)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = botones.button(QDialogButtonBox.Ok)

        def guardar():
            if ok.isEnabled():
                self.accept()

        self.texto = _Texto(guardar)
        self.texto.setPlaceholderText("Llamar a Marta" if recordatorio else "Revisar el backup del nodo 3")
        self.texto.setTabChangesFocus(True)
        self.texto.setFixedHeight(110)

        # Colores: una fila de cuadraditos
        self._grupo_color = QButtonGroup(self)
        fila_color = QHBoxLayout()
        fila_color.addWidget(QLabel("Color:"))
        actual = color_de(nota) if editando else ("naranja" if recordatorio else "amarillo")
        # Si no eliges otro, no se guarda color y sigue el automático (naranja con aviso)
        self._automatico = None if (editando and nota.get("color")) else actual
        for clave, (nombre, papel, franja) in COLORES.items():
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(24, 24)
            b.setToolTip(nombre)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton {{ background: {papel}; border: 1px solid {franja};"
                            f" border-radius: 4px; }}"
                            f"QPushButton:checked {{ border: 3px solid #424242; }}")
            b.setProperty("color", clave)
            b.setChecked(clave == actual)
            self._grupo_color.addButton(b)
            fila_color.addWidget(b)
        fila_color.addStretch(1)

        self.cuando = QComboBox()
        self._opciones = CUANDO[1:] if recordatorio else CUANDO
        for nombre, _ in self._opciones:
            self.cuando.addItem(nombre)
        if recordatorio:
            self.cuando.setCurrentIndex(1)   # 15 min

        self.hora = QTimeEdit(QTime.currentTime().addSecs(3600))
        self.hora.setDisplayFormat("HH:mm")
        self.hora.setVisible(False)
        self.cuando.currentIndexChanged.connect(
            lambda i: self.hora.setVisible(self._opciones[i][1] == -1))

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Avisarme:"))
        fila.addWidget(self.cuando, 1)
        fila.addWidget(self.hora)

        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        self.texto.textChanged.connect(
            lambda: ok.setEnabled(bool(self.texto.toPlainText().strip())))
        ok.setEnabled(False)

        pista = QLabel("Enter = nueva línea · Ctrl+Enter = guardar")
        pista.setStyleSheet("color: gray; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.texto)
        layout.addWidget(pista)
        layout.addLayout(fila_color)
        if not editando:   # al editar, el aviso se cambia desde el menú del post-it
            layout.addLayout(fila)
        layout.addWidget(botones)

        if editando:
            self.texto.setPlainText(nota["texto"])
            self.texto.moveCursor(self.texto.textCursor().End)
        self.texto.setFocus()

    def texto_escrito(self) -> str:
        return self.texto.toPlainText().strip()

    def color(self) -> str:
        """Color elegido, o None si se deja el automático."""
        b = self._grupo_color.checkedButton()
        color = b.property("color") if b else None
        return None if color == self._automatico else color

    def aviso(self):
        """datetime del aviso elegido, o None si es "Sin aviso"."""
        minutos = self._opciones[self.cuando.currentIndex()][1]
        if minutos is None:
            return None
        if minutos == -1:
            return a_las(self.hora.time())
        return en_minutos(minutos)
