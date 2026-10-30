"""Rocket.Chat: cliente (estado, usuario) y avisos de mensajes directos y menciones.

Adaptado del whisperer_bot. No marca nada como leído en Rocket.Chat.
"""
import threading

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from pingu.utils import env, log

# Estados de Rocket.Chat → (emoji, nombre)
ESTADOS = {
    "online":  ("🟢", "Disponible"),
    "busy":    ("🔴", "No molestar"),
    "away":    ("🟡", "Ausente"),
    "offline": ("⚫", "Invisible"),
}

HISTORY_ENDPOINTS = {"d": "im.history", "c": "channels.history", "p": "groups.history"}
ROOM_PATHS        = {"d": "direct", "c": "channel", "p": "group"}


def configurado() -> bool:
    return bool(env("ROCKET_CHAT_URL") and env("ROCKET_CHAT_APP_ID")
                and env("ROCKET_CHAT_APP_SECRET"))


class RocketChatClient:
    def __init__(self):
        self.url     = env("ROCKET_CHAT_URL").rstrip("/")
        self.user_id = env("ROCKET_CHAT_APP_ID")
        self._username = None
        self.session = requests.Session()
        self.session.headers.update({"X-User-Id":    self.user_id,
                                     "X-Auth-Token": env("ROCKET_CHAT_APP_SECRET")})
        self._lock = threading.Lock()   # la sesión se usa desde varios hilos

    def get(self, path: str, **params) -> dict:
        with self._lock:
            resp = self.session.get(f"{self.url}/api/v1/{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def username(self):
        """Username propio (para detectar menciones). Se pide una vez."""
        if self._username is None:
            try:
                self._username = self.get("me").get("username") or ""
            except Exception as e:
                log(f"[RC] No se pudo obtener el username propio: {e}")
                return None
        return self._username or None

    def get_status(self):
        """Estado actual (online, busy, away, offline) o None si falla."""
        try:
            return self.get("users.getStatus").get("status")
        except Exception as e:
            log(f"[RC] Error consultando estado: {e}")
            return None

    def set_status(self, status: str) -> bool:
        try:
            with self._lock:
                resp = self.session.post(f"{self.url}/api/v1/users.setStatus",
                                         json={"status": status}, timeout=10)
            resp.raise_for_status()
            if not resp.json().get("success"):
                log(f"[RC] Rechazado el cambio de estado: {resp.text[:200]}")
                return False
            log(f"[RC] Estado → {status}")
            return True
        except Exception as e:
            log(f"[RC] Error cambiando estado: {e}")
            return False

    def room_url(self, sub: dict) -> str:
        path = ROOM_PATHS.get(sub.get("t"), "direct")
        ident = sub["rid"] if sub.get("t") == "d" else sub.get("name", sub["rid"])
        return f"{self.url}/{path}/{ident}"

    def me_mencionan(self, msg: dict) -> bool:
        """True si el mensaje me menciona a mí o usa @all / @here."""
        own = self.username()
        for m in msg.get("mentions", []):
            username = m.get("username", "")
            if username in ("all", "here"):
                return True
            if m.get("_id") == self.user_id or (own and username == own):
                return True
        return False


class RocketChatWorker(QThread):
    """Cada POLL_SECONDS mira las suscripciones y avisa de DMs y menciones nuevas."""
    # (texto para la burbuja, url para abrir la conversación)
    mensajes_nuevos = pyqtSignal(str, str)

    POLL_SECONDS = 20
    MAX_SEEN     = 1000
    MAX_TEXT     = 160   # caracteres por mensaje en la burbuja
    MAX_LINES    = 3     # mensajes que caben en una burbuja

    def __init__(self, client: RocketChatClient, parent=None):
        super().__init__(parent)
        self.client   = client
        self.activo   = True      # lo cambia el pingüino desde el menú
        self._running = True
        self._despertar = threading.Event()   # espera entre vueltas, interrumpible
        self._seen    = []        # ids ya avisados (orden de llegada)
        self._seen_set = set()
        self._first   = True
        self._error   = None

    def stop(self):
        self._running = False
        self._despertar.set()   # sale de la espera al momento
        self.quit()

    def _remember(self, msg_id: str):
        if msg_id in self._seen_set:
            return
        self._seen.append(msg_id)
        self._seen_set.add(msg_id)
        if len(self._seen) > self.MAX_SEEN:
            self._seen_set.discard(self._seen.pop(0))

    def _nuevos(self) -> list:
        """[(url, cabecera, texto)] de DMs y menciones sin leer que aún no se avisaron."""
        subs = self.client.get("subscriptions.get").get("update", [])
        nuevos = []
        for sub in subs:
            tipo, unread = sub.get("t"), sub.get("unread", 0)
            if unread <= 0 or tipo not in HISTORY_ENDPOINTS:
                continue
            es_dm = tipo == "d"
            # En canales solo miramos si la suscripción dice que hay alguna mención
            if not es_dm and not (sub.get("userMentions", 0) + sub.get("groupMentions", 0)):
                continue
            try:
                hist = self.client.get(HISTORY_ENDPOINTS[tipo], roomId=sub["rid"],
                                       count=min(unread, 50))
            except Exception as e:
                log(f"[RC] Historial de {sub.get('name')}: {e}")
                continue

            for msg in reversed(hist.get("messages", [])):
                msg_id = msg.get("_id")
                if not msg_id or msg_id in self._seen_set:
                    continue
                self._remember(msg_id)
                user = msg.get("u", {})
                if user.get("_id") == self.client.user_id or msg.get("t"):
                    continue   # mío, o mensaje de sistema (entró/salió, etc.)
                if not es_dm and not self.client.me_mencionan(msg):
                    continue

                texto = (msg.get("msg") or "").strip()
                if not texto:
                    adjuntos = msg.get("attachments") or []
                    texto = "🖼️ Imagen" if any(a.get("image_url") for a in adjuntos) else "📎 Archivo"
                nombre = user.get("name") or user.get("username") or "Alguien"
                cabecera = f"💬 {nombre}" if es_dm else f"📣 {nombre} en #{sub.get('name', '?')}"
                nuevos.append((self.client.room_url(sub), cabecera, texto))
        return nuevos

    def _formatear(self, nuevos: list) -> str:
        lineas = []
        for _, cabecera, texto in nuevos[-self.MAX_LINES:]:
            if len(texto) > self.MAX_TEXT:
                texto = texto[:self.MAX_TEXT].rstrip() + "…"
            lineas.append(f"{cabecera}:\n{texto}")
        extra = len(nuevos) - self.MAX_LINES
        if extra > 0:
            lineas.insert(0, f"(+{extra} mensajes más)")
        return "\n\n".join(lineas)

    def run(self):
        log("[RC] Vigilando mensajes directos y menciones")
        while self._running:
            try:
                nuevos = self._nuevos()
                if self._error:
                    log("[RC] Conexión recuperada")
                    self._error = None
                if self._first:
                    # Al arrancar no repetimos uno a uno lo que ya estaba sin leer
                    self._first = False
                    if nuevos and self.activo:
                        quienes = sorted({c.split(" ", 1)[1] for _, c, _ in nuevos})
                        self.mensajes_nuevos.emit(
                            f"💬 Tienes {len(nuevos)} mensaje(s) sin leer:\n" + "\n".join(quienes),
                            f"{self.client.url}/home")
                elif nuevos and self.activo:
                    self.mensajes_nuevos.emit(self._formatear(nuevos), nuevos[-1][0])
                    log(f"[RC] {len(nuevos)} mensaje(s) nuevo(s)")
            except Exception as e:
                if str(e) != self._error:
                    log(f"[RC] Error consultando Rocket.Chat: {e}")
                    self._error = str(e)

            self._despertar.wait(self.POLL_SECONDS)
