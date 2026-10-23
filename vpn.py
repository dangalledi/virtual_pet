"""Detección de VPN en dos pasos:
1) la interfaz del túnel (ppp0) está UP y con IP;
2) alguna máquina interna responde por SSH (sin login).
Así se detecta también el caso "túnel levantado pero sin tráfico".
"""
import re
import shlex
import shutil
import socket
import subprocess

from utils import env, log


def interfaz() -> str:
    return env("VPN_INTERFACE", "ppp0")


def hosts() -> list:
    """Lista de (host, puerto) desde VPN_CHECK_HOSTS (host:puerto,host:puerto)."""
    raw = env("VPN_CHECK_HOSTS", "opswebres01.bsc.es:22,opswebhpc01.bsc.es:22")
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


def estado_ahora() -> tuple:
    """Comprobación completa e inmediata (prueba todos los hosts).
    Devuelve (conectada, detalle)."""
    iface = interfaz()
    if iface and not interfaz_activa(iface):
        return False, f"La interfaz {iface} no está activa."
    hs = hosts()
    if not hs:
        return True, ""
    failed = [h for h, p in hs if not ssh_responde(h, p)]
    if len(failed) < len(hs):
        return True, ""
    return False, "No responde: " + ", ".join(failed)


def comando_conexion() -> str:
    """Comando para conectar la VPN (VPN_CONNECT_CMD en el .env)."""
    return env("VPN_CONNECT_CMD")


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
    Caída = interfaz abajo, o todos los hosts han fallado en su última prueba."""

    def __init__(self):
        self.conectada = None      # None = desconocido (primer arranque)
        self._results  = {}        # host -> último resultado
        self._index    = 0

    def comprobar(self):
        """Devuelve (conectada, detalle) si el estado ha cambiado; None si sigue igual."""
        iface = interfaz()
        if iface and not interfaz_activa(iface):
            self._results.clear()
            return self._cambiar(False, f"La interfaz {iface} no está activa.")

        hs = hosts()
        if not hs:
            return self._cambiar(True, "") if iface else None

        host, port = hs[self._index % len(hs)]
        self._index += 1
        ok = ssh_responde(host, port)
        if self._results.get(host) != ok:
            log(f"VPN check {host}:{port} -> {'OK' if ok else 'FALLO'}")
        self._results[host] = ok

        if ok:
            return self._cambiar(True, "")
        if all(h in self._results for h, _ in hs) and not any(self._results[h] for h, _ in hs):
            return self._cambiar(False, "No responde: " + ", ".join(h for h, _ in hs))
        return None

    def _cambiar(self, conectada: bool, detalle: str):
        if conectada == self.conectada:
            return None
        self.conectada = conectada
        log(f"VPN: {'conectada' if conectada else 'desconectada'} {detalle}".strip())
        return conectada, detalle
