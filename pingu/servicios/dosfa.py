"""Código 2FA (TOTP) — lo mismo que el alias `my2fa` del .bashrc:
    oathtool --totp -b "$(cat ~/.ssh/.2fa_secret)"
El secreto se pasa a oathtool por stdin para que no aparezca en la lista de procesos.

Solo se ofrece si TOTP_SECRET_FILE está en el .env, el fichero tiene un secreto
base32 válido y oathtool está instalado. Si no, la opción no aparece en el menú."""
import os
import re
import time
import shutil
import subprocess
from pathlib import Path

from pingu.utils import env, log

PERIODO = 30   # segundos que dura cada código TOTP
_BASE32 = re.compile(r"^[A-Z2-7]{16,}=*$")
_ultimo_motivo = None


def secret_file():
    """Ruta del fichero del secreto, o None si TOTP_SECRET_FILE no está en el .env."""
    ruta = env("TOTP_SECRET_FILE")
    return Path(os.path.expanduser(ruta)) if ruta else None


def motivo_desactivado() -> str:
    """"" si el 2FA se puede usar; si no, por qué (para el log)."""
    ruta = secret_file()
    if ruta is None:
        return "TOTP_SECRET_FILE no está en el .env"
    if not ruta.is_file():
        return f"no existe {ruta}"
    try:
        secreto = "".join(ruta.read_text().split()).upper()
    except OSError as e:
        return f"no puedo leer {ruta}: {e.strerror}"
    if not _BASE32.match(secreto):
        return f"{ruta} no tiene un secreto TOTP en base32"
    if shutil.which("oathtool") is None:
        return "falta oathtool (sudo apt install oathtool)"
    return ""


def configurado() -> bool:
    """¿Se ofrece la opción del 2FA? Si no, deja el motivo en el log (una vez)."""
    global _ultimo_motivo
    motivo = motivo_desactivado()
    if motivo != _ultimo_motivo:
        _ultimo_motivo = motivo
        log(f"[2FA] {'Disponible' if not motivo else 'Desactivado: ' + motivo}")
    return not motivo


def segundos_restantes() -> int:
    return PERIODO - int(time.time()) % PERIODO


def codigo() -> str:
    """Código TOTP actual. Lanza RuntimeError si algo falla."""
    if secret_file() is None:
        raise RuntimeError("TOTP_SECRET_FILE no está en el .env")
    try:
        secret = secret_file().read_text().strip()
    except OSError as e:
        raise RuntimeError(f"No puedo leer {secret_file()}: {e.strerror}") from None
    out = subprocess.run(["oathtool", "--totp", "-b", "-"], input=secret,
                         capture_output=True, text=True, timeout=5)
    code = out.stdout.strip()
    if out.returncode != 0 or not code.isdigit():
        raise RuntimeError(f"oathtool falló: {out.stderr.strip()[:100]}")
    return code
