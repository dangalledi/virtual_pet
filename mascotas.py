"""Mascotas de vscode-pets (https://github.com/tonybaloney/vscode-pets).

Los GIF se leen de la extensión de VS Code instalada (~/.vscode/extensions/tonybaloney.vscode-pets-*).
Si no está, el pollo y el pato se descargan del repo a mascotas_cache/; el gato no se
puede descargar (el repo lo guarda cifrado por su licencia), hace falta la extensión.
Los dibujos son de sus autores (ver créditos en el readme): no se copian a este repo.
"""
import glob
import os
import re
from pathlib import Path

import requests
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBitmap, QImage, QMovie, QPainter, QPixmap, QRegion

from utils import BASE_DIR, env, log

PINGU = "pingu"

# clave -> (nombre en el menú, carpeta en media/, colores, ¿se puede descargar?)
CATALOGO = {
    "gato":  ("🐱 Gato",  "cat",         ["brown", "white", "black", "gray", "orange", "lightbrown"], False),
    "pollo": ("🐔 Pollo", "chicken",     ["white", "brown", "gray"], True),
    "pato":  ("🦆 Pato",  "rubber-duck", ["yellow"], True),
}

COLORES = {"brown": "marrón", "white": "blanco", "black": "negro", "gray": "gris",
           "orange": "naranja", "lightbrown": "canela", "yellow": "amarillo"}

# Estado del pingüino -> animación de vscode-pets
ANIMACIONES = {
    "idle":      "idle",
    "walk":      "walk",
    "jump":      "run",
    "atack":     "swipe",
    "pre_slide": "walk_fast",
    "slide":     "walk_fast",
}

CACHE_DIR = BASE_DIR / "mascotas_cache"
RAW_URL = "https://raw.githubusercontent.com/tonybaloney/vscode-pets/main/media"


def _version(ruta: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", ruta.rsplit("-", 1)[-1]))


def media_extension():
    """Carpeta media/ de la extensión vscode-pets más nueva instalada, o None."""
    propia = env("VSCODE_PETS_MEDIA")
    if propia:
        return Path(propia).expanduser()
    candidatas = []
    for editor in (".vscode", ".vscode-oss", ".vscode-server", ".cursor", ".windsurf"):
        candidatas += glob.glob(os.path.expanduser(f"~/{editor}/extensions/tonybaloney.vscode-pets-*"))
    candidatas = [c for c in candidatas if os.path.isdir(os.path.join(c, "media"))]
    if not candidatas:
        return None
    return Path(max(candidatas, key=_version)) / "media"


def _gif(carpeta: str, color: str, anim: str, descargar: bool):
    """Ruta del GIF: de la extensión o de la caché (descargándolo si hace falta)."""
    nombre = f"{color}_{anim}_8fps.gif"
    media = media_extension()
    if media and (media / carpeta / nombre).exists():
        return media / carpeta / nombre
    cache = CACHE_DIR / carpeta / nombre
    if cache.exists():
        return cache
    if not descargar:
        return None
    try:
        resp = requests.get(f"{RAW_URL}/{carpeta}/{nombre}", timeout=15)
        resp.raise_for_status()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(resp.content)
        log(f"[MASCOTA] Descargado {carpeta}/{nombre}")
        return cache
    except Exception as e:
        log(f"[MASCOTA] No pude descargar {carpeta}/{nombre}: {e}")
        return None


def disponible(clave: str) -> bool:
    """¿Se puede usar? (el gato necesita la extensión instalada)."""
    if clave == PINGU:
        return True
    _, carpeta, colores, descargable = CATALOGO[clave]
    media = media_extension()
    return descargable or bool(media and (media / carpeta / f"{colores[0]}_idle_8fps.gif").exists())


def _leer_gif(ruta) -> list:
    movie = QMovie(str(ruta))
    frames = []
    for i in range(movie.frameCount()):
        movie.jumpToFrame(i)
        frames.append(movie.currentImage().convertToFormat(QImage.Format_ARGB32))
    return frames


def cargar(clave: str, color: str, tam: int):
    """Animaciones de una mascota de tam px de alto (más ancha si el dibujo lo pide).
    Devuelve ({estado: [QPixmap]}, margen_arriba, ancho) o None si falta algo.

    Las animaciones tienen lienzos de distinto tamaño: se apoyan todas abajo y
    centradas, se recorta el hueco vacío común y se escalan con el mismo factor,
    para que la mascota no cambie de tamaño al cambiar de animación."""
    _, carpeta, colores, descargable = CATALOGO[clave]
    if color not in colores:
        color = colores[0]

    gifs = {}
    for anim in set(ANIMACIONES.values()):
        ruta = _gif(carpeta, color, anim, descargable)
        frames = _leer_gif(ruta) if ruta else []
        if not frames:
            log(f"[MASCOTA] Falta {carpeta}/{color}_{anim}")
            return None
        gifs[anim] = frames

    ancho = max(f.width() for fs in gifs.values() for f in fs)
    alto = max(f.height() for fs in gifs.values() for f in fs)

    def apoyar(img: QImage) -> QImage:
        lienzo = QImage(ancho, alto, QImage.Format_ARGB32)
        lienzo.fill(Qt.transparent)
        p = QPainter(lienzo)
        p.drawImage((ancho - img.width()) // 2, alto - img.height(), img)
        p.end()
        return lienzo

    apoyados = {a: [apoyar(f) for f in fs] for a, fs in gifs.items()}

    # Caja que ocupa el dibujo en todas las animaciones juntas
    caja = None
    for fs in apoyados.values():
        for f in fs:
            r = QRegion(QBitmap.fromImage(f.createAlphaMask())).boundingRect()
            caja = r if caja is None else caja.united(r)
    if caja is None or caja.isEmpty():
        return None

    # Se escala por la altura: así una animación muy alargada (correr) no encoge a la mascota
    escala = tam / caja.height()
    modo = Qt.SmoothTransformation if escala < 1 else Qt.FastTransformation   # pixel art nítido
    w, h = round(caja.width() * escala), tam
    total = max(tam, w)
    x0 = (total - w) // 2

    def a_tamano(img: QImage) -> QPixmap:
        final = QImage(total, tam, QImage.Format_ARGB32)
        final.fill(Qt.transparent)
        p = QPainter(final)
        p.drawImage(x0, 0, img.copy(caja).scaled(w, h, Qt.IgnoreAspectRatio, modo))
        p.end()
        return QPixmap.fromImage(final)

    listos = {a: [a_tamano(f) for f in fs] for a, fs in apoyados.items()}
    animaciones = {estado: listos[anim] for estado, anim in ANIMACIONES.items()}
    animaciones["pre_slide"] = animaciones["pre_slide"][:1]   # un instante antes de deslizarse

    # Dónde empieza la cabeza en reposo: ahí apunta el piquito del globo
    arriba = min(QRegion(QBitmap.fromImage(p.toImage().createAlphaMask())).boundingRect().top()
                 for p in animaciones["idle"])
    return animaciones, arriba, total


def nombre(clave: str, color: str = "") -> str:
    if clave == PINGU:
        return "🐧 Pingüino"
    texto, _, colores, _ = CATALOGO[clave]
    return f"{texto} {COLORES.get(color, color)}" if len(colores) > 1 and color else texto
