"""Detección de VPN / red interna:
- Lo que manda es si alguna máquina interna responde por SSH (sin login).
- La interfaz del túnel (ppp0) solo dice *cómo* llegamos: con ella es la VPN;
  sin ella, estamos en la red de la oficina y la VPN no hace falta.
Así se detecta también el caso "túnel levantado pero sin tráfico".
"""
import re
import shlex
import shutil
import socket
import subprocess

from pingu.utils import con_usuario, env, log


def interfaz() -> str:
    return env("VPN_INTERFACE", "ppp0")


def hosts() -> list:
    """Lista de (host, puerto) desde VPN_CHECK_HOSTS (host:puerto,host:puerto).
    Vacío = solo se mira la interfaz (y no se puede saber si estás en la oficina)."""
    raw = env("VPN_CHECK_HOSTS")
    result = []
    for h in raw.split(","):
        h = h.strip()
        if not h:
            continue
        if ":" in h:
            name, port = h.rsplit(":", 1)
            result.append((name, int(port)))
        else:
            result.append((h, 22))
    return result


def interfaz_activa(iface: str) -> bool:
    """¿Existe la interfaz, está UP y tiene IP? (sin ping, que el gateway suele bloquear)"""
    try:
        link = subprocess.run(["ip", "link", "show", iface], capture_output=True, timeout=2)
        if link.returncode != 0 or b"UP" not in link.stdout:
            return False
        # Si el túnel muere, la IP desaparece aunque la interfaz tarde en bajar
        addr = subprocess.run(["ip", "addr", "show", iface],
                              capture_output=True, text=True, timeout=2)
        return bool(re.search(r"inet \d+\.\d+\.\d+\.\d+", addr.stdout))
    except Exception:
        return False


def ssh_responde(host: str, port: int, timeout: float = 5) -> bool:
    """True si el host acepta TCP en el puerto y saluda como SSH. No hace login."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            return sock.recv(64).startswith(b"SSH-")
    except OSError:
        return False


# Detalle de "conectada" cuando llegamos a la red interna sin túnel (estamos en la oficina)
OFICINA = "oficina"


def _detalle_ok(iface_activa: bool) -> str:
    return "" if iface_activa else OFICINA


def _detalle_caida(iface: str, iface_activa: bool, failed: list) -> str:
    if iface and not iface_activa:
        return f"La interfaz {iface} no está activa."
    return "No responde: " + ", ".join(failed)


def estado_ahora() -> tuple:
    """Comprobación completa e inmediata (prueba todos los hosts).
    Devuelve (conectada, detalle); detalle == OFICINA si es por la red de la oficina."""
    iface = interfaz()
    activa = interfaz_activa(iface) if iface else True
    hs = hosts()
    if not hs:
        return activa, "" if activa else f"La interfaz {iface} no está activa."
    failed = [h for h, p in hs if not ssh_responde(h, p)]
    if len(failed) < len(hs):
        return True, _detalle_ok(activa)
    return False, _detalle_caida(iface, activa, failed)


def comando_conexion() -> str:
    """Comando para conectar la VPN (VPN_CONNECT_CMD en el .env)."""
    return con_usuario(env("VPN_CONNECT_CMD"))


def conexion_en_marcha() -> bool:
    """¿Hay ya un openfortivpn corriendo (aunque aún no haya terminado de conectar)?"""
    return subprocess.run(["pgrep", "-x", "openfortivpn"], capture_output=True).returncode == 0


def conectar_en_terminal() -> str:
    """Abre una terminal con el comando de conexión; ahí escribes las contraseñas.
    Devuelve "" si se abrió, o el motivo por el que no."""
    cmd = comando_conexion()
    if not cmd:
        return "Falta VPN_CONNECT_CMD en el .env"
    terminal = shutil.which("gnome-terminal") or shutil.which("x-terminal-emulator")
    if not terminal:
        return "No encuentro ninguna terminal"
    # La terminal se queda abierta: openfortivpn sigue en primer plano mientras dura la VPN
    script = (f"echo '🐧 Conectando la VPN… (cierra esta ventana para desconectar)'; echo; "
              f"{cmd}; echo; read -rp 'VPN desconectada. Pulsa Enter para cerrar…'")
    args = [terminal, "--title=VPN", "--", "bash", "-c", script]
    if not terminal.endswith("gnome-terminal"):
        args = [terminal, "-e", "bash -c " + shlex.quote(script)]
    try:
        subprocess.Popen(args, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"No pude abrir la terminal: {e}"
    log(f"VPN: terminal de conexión abierta ({cmd})")
    return ""


class VpnMonitor:
    """Chequeo periódico barato: un host por vuelta, rotando.
    Caída = todos los hosts han fallado en su última prueba.
    Si el túnel se cae estando conectados, se prueban todos a la vez para avisar
    rápido (o darse cuenta enseguida de que estamos en la red de la oficina)."""

    def __init__(self):
        self.conectada = None      # None = desconocido (primer arranque)
        self.en_oficina = False    # conectada sin túnel: red interna de la oficina
        self._results  = {}        # host -> último resultado
        self._index    = 0
        self._iface_activa = None

    def comprobar(self):
        """Devuelve (conectada, detalle) si el estado ha cambiado; None si sigue igual."""
        iface = interfaz()
        activa = interfaz_activa(iface) if iface else True
        iface_cambio = activa != self._iface_activa
        self._iface_activa = activa

        hs = hosts()
        if not hs:
            if not iface:
                return None
            return self._cambiar(activa, "" if activa else f"La interfaz {iface} no está activa.")

        # El túnel acaba de cambiar: lo de antes ya no vale, probar todos ahora
        a_probar = hs if iface_cambio else [hs[self._index % len(hs)]]
        if iface_cambio:
            self._results.clear()
        else:
            self._index += 1
        for host, port in a_probar:
            ok = ssh_responde(host, port)
            if self._results.get(host) != ok:
                log(f"VPN check {host}:{port} -> {'OK' if ok else 'FALLO'}")
            self._results[host] = ok
            if ok:
                return self._cambiar(True, _detalle_ok(activa))

        if all(h in self._results for h, _ in hs) and not any(self._results[h] for h, _ in hs):
            return self._cambiar(False, _detalle_caida(iface, activa, [h for h, _ in hs]))
        return None

    def _cambiar(self, conectada: bool, detalle: str):
        oficina = conectada and detalle == OFICINA
        if conectada == self.conectada:
            if conectada and oficina != self.en_oficina:   # VPN <-> oficina: sin aviso
                self.en_oficina = oficina
                log(f"VPN: ahora por {'la red de la oficina' if oficina else 'el túnel'}")
            return None
        self.conectada = conectada
        self.en_oficina = oficina
        log(f"VPN: {'conectada' if conectada else 'desconectada'} {detalle}".strip())
        return conectada, detalle
