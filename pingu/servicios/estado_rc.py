"""Estado automático en Rocket.Chat.

Reglas (de más a menos prioridad):
  • en una reunión del calendario  → No molestar
  • pingüino escondido o ya has fichado la salida → Ausente
  • en otro caso                     → Disponible

Solo cambia el estado si sigue siendo el último que puso él, o si estás en
"Disponible". Si lo cambias a mano a otra cosa (o estás Invisible / desconectado),
no lo toca hasta que vuelvas a ponerte Disponible.
"""
import threading

from pingu.utils import log


class EstadoAuto:
    def __init__(self, client):
        self.client     = client
        self.activo     = False    # desactivado por defecto; se activa desde el menú
        self.en_reunion = False
        self.escondido  = False
        self.fuera      = False    # fichada la salida
        self._puesto    = None     # último estado que puso el pingüino
        self._lock      = threading.Lock()

    def deseado(self) -> str:
        if self.en_reunion:
            return "busy"
        if self.escondido or self.fuera:
            return "away"
        return "online"

    def actualizar(self, **cambios):
        """Cambia las condiciones (en_reunion=…, escondido=…, fuera=…) y aplica
        el estado en segundo plano."""
        for k, v in cambios.items():
            setattr(self, k, v)
        if self.activo:
            threading.Thread(target=self._aplicar, daemon=True).start()

    def _aplicar(self):
        with self._lock:
            actual = self.client.get_status()
            if actual is None:
                return
            objetivo = self.deseado()
            if actual == objetivo:
                self._puesto = objetivo if self._puesto else None
                return
            if actual != self._puesto and actual != "online":
                log(f"[RC] Estado '{actual}' puesto a mano: no lo cambio")
                return
            if self.client.set_status(objetivo):
                self._puesto = objetivo

    def manual(self, status: str) -> bool:
        """Estado elegido a mano desde el menú: el automático lo respeta."""
        with self._lock:
            ok = self.client.set_status(status)
            if ok:
                self._puesto = None
            return ok
