"""Utilidades comunes: .env, log, preferencias guardadas e inactividad del usuario."""
import os
import json
import getpass
import datetime
import subprocess
from pathlib import Path

from dotenv import load_dotenv

# Raíz del proyecto (aquí están .env, notas.json, settings.json, images/…)
BASE_DIR = Path(__file__).resolve().parent.parent
# interpolate=False: que un "$" en una contraseña no se tome como una variable
load_dotenv(BASE_DIR / ".env", interpolate=False)

SETTINGS_FILE = BASE_DIR / "settings.json"


def log(message: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [DEBUG] {message}", flush=True)


def env(name: str, default: str = "") -> str:
    """Lee una variable del .env. Los comentarios del final ("valor   # comentario") ya los
    quita python-dotenv; aquí no se corta en "#" para no romper contraseñas como "abc#123"."""
    return os.getenv(name, default).strip()


def usuario() -> str:
    """Tu usuario de la empresa (LDAP): LDAP_USER del .env o, si no está, el de este Linux."""
    return env("LDAP_USER") or getpass.getuser()


def con_usuario(texto: str) -> str:
    """Cambia {usuario} por tu usuario LDAP (en URLs de calendario, comando de la VPN…)."""
    return texto.replace("{usuario}", usuario())


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        log(f"{name} no es un número; uso {default}")
        return default


def zoom_general() -> float:
    """Zoom general aplicado al arrancar (menús, ventanas, globos). La mascota y los
    post-its tienen su propio tamaño y lo compensan para no agrandarse dos veces."""
    try:
        return float(os.environ.get("QT_SCALE_FACTOR") or 1)
    except ValueError:
        return 1.0


def tamano_elegido(settings: dict, clave: str) -> float:
    """Tamaño elegido para la mascota o los post-its (1 = normal). Si no se ha elegido
    nunca, el del zoom general, para que no cambien de golpe."""
    return settings.get(clave) or settings.get("zoom") or 1


def load_settings() -> dict:
    """Preferencias que se cambian desde el menú y se recuerdan entre reinicios."""
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except OSError as e:
        log(f"No se pudo guardar {SETTINGS_FILE.name}: {e}")


def idle_seconds():
    """Segundos sin tocar teclado ni ratón, según GNOME (Mutter). None si no se puede saber."""
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.gnome.Mutter.IdleMonitor",
             "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
             "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
            capture_output=True, text=True, timeout=3)
        if out.returncode != 0:
            return None
        # Respuesta: "(uint64 12345,)" en milisegundos
        ms = int(out.stdout.strip().strip("(),").split()[-1])
        return ms / 1000
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def hm(secs: float) -> str:
    """Segundos → '6h 31min'."""
    secs = abs(int(secs))
    return f"{secs // 3600}h {(secs % 3600) // 60}min"


# Títulos de ventana de navegadores (para traerlos al frente sin abrir pestañas)
NAVEGADORES = ("Mozilla Firefox", "Google Chrome", "Chromium", "Brave", "Microsoft Edge")


def activar_ventana(*patrones: str) -> bool:
    """Trae al frente la primera ventana cuyo título contenga alguno de los patrones,
    probándolos en orden. Usa wmctrl (X11). True si encontró alguna."""
    try:
        out = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    ventanas = []
    for line in out.stdout.splitlines():
        partes = line.split(None, 3)
        if len(partes) == 4:
            ventanas.append((partes[0], partes[3]))
    for patron in patrones:
        for wid, titulo in ventanas:
            if patron.lower() in titulo.lower():
                subprocess.run(["wmctrl", "-ia", wid], timeout=2)
                return True
    return False
