"""Notas y recordatorios (post-its del pingüino), guardados en notas.json.

- Recordatorio: texto + hora de aviso. Cuando avisa, desaparece.
- Nota: se queda en la lista hasta que la marcas como hecha. Puede llevar aviso;
  cuando avisa, sigue en la lista (sin aviso).
"""
import datetime
import json
import time

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QLineEdit, QTimeEdit, QVBoxLayout)

from utils import BASE_DIR, log

NOTAS_FILE = BASE_DIR / "notas.json"

# Opciones de "cuándo" en el diálogo: (texto, minutos). None = sin aviso, -1 = a una hora
CUANDO = [("Sin aviso", None), ("En 5 min", 5), ("En 15 min", 15), ("En 30 min", 30),
          ("En 1 hora", 60), ("En 2 horas", 120), ("A las…", -1)]
POSPONER = [("En 15 min", 15), ("En 30 min", 30), ("En 1 hora", 60)]


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


def nueva(notas: list, texto: str, aviso, fija: bool) -> dict:
    """Añade una nota (fija=True) o un recordatorio (fija=False). aviso: datetime o None."""
    nota = {"id": int(time.time() * 1000), "texto": texto.strip(), "fija": fija,
            "aviso": aviso.isoformat(timespec="minutes") if aviso else None}
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
class DialogoNota(QDialog):
    def __init__(self, recordatorio: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⏰ Recuérdame" if recordatorio else "📝 Nueva nota")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(360)

        self.texto = QLineEdit()
        self.texto.setPlaceholderText("Llamar a Marta" if recordatorio else "Revisar el backup del nodo 3")

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

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        self.texto.textChanged.connect(
            lambda t: botones.button(QDialogButtonBox.Ok).setEnabled(bool(t.strip())))
        botones.button(QDialogButtonBox.Ok).setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.texto)
        layout.addLayout(fila)
        layout.addWidget(botones)

    def aviso(self):
        """datetime del aviso elegido, o None si es "Sin aviso"."""
        minutos = self._opciones[self.cuando.currentIndex()][1]
        if minutos is None:
            return None
        if minutos == -1:
            return a_las(self.hora.time())
        return en_minutos(minutos)
