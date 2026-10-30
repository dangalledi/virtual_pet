import os
import sys
import fcntl
from pathlib import Path

from PyQt5.QtWidgets import QApplication

LOCK_FILE = Path(__file__).resolve().parent / ".pingu.lock"


def aplicar_zoom():
    """Zoom de todo (mascota, globos, menús, post-its…) elegido en el menú 🔍 Tamaño.
    Qt lo lee al crear la aplicación, así que hay que ponerlo antes."""
    from utils import load_settings
    zoom = load_settings().get("zoom")
    if zoom and zoom != 1:
        os.environ["QT_SCALE_FACTOR"] = str(zoom)


def ya_abierto() -> bool:
    """True si ya hay otro pingüino abierto (evita dos al arrancar sesión + a mano)."""
    global _lock
    _lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)   # se suelta solo al cerrar
        return False
    except OSError:
        return True


if __name__ == "__main__":
    if ya_abierto():
        print("El pingüino ya está abierto.")
        sys.exit(0)

    aplicar_zoom()
    from penguin import PenguinCharacter
    app = QApplication(sys.argv)
    # Al esconderse en la barra no hay ventanas visibles: que no se cierre la app
    app.setQuitOnLastWindowClosed(False)
    penguin = PenguinCharacter()
    penguin.show()
    penguin.setFocus()
    penguin.setupAutoMoveTimer()
    sys.exit(app.exec_())
