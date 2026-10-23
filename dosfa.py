"""Código 2FA (TOTP) — lo mismo que el alias `my2fa` del .bashrc:
    oathtool --totp -b "$(cat ~/.ssh/.2fa_secret)"
El secreto se pasa a oathtool por stdin para que no aparezca en la lista de procesos."""
import os
import time
import shutil
import subprocess
from pathlib import Path

from utils import env

PERIODO = 30   # segundos que dura cada código TOTP


def secret_file() -> Path:
    return Path(os.path.expanduser(env("TOTP_SECRET_FILE", "~/.ssh/.2fa_secret")))


def configurado() -> bool:
    return shutil.which("oathtool") is not None and secret_file().is_file()


def segundos_restantes() -> int:
    return PERIODO - int(time.time()) % PERIODO


def codigo() -> str:
    """Código TOTP actual. Lanza RuntimeError si algo falla."""
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
