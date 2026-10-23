#!/usr/bin/env bash
# Arranca el pingüino con el Python del entorno virtual (sin depender de "activate",
# que guarda la ruta absoluta de cuando se creó el .venv).
# Con --autostart (inicio de sesión) el log va a pingu.log en vez de a la terminal.
cd "$(dirname "$0")"
if [ "$1" = "--autostart" ]; then
    shift
    exec .venv/bin/python main.py "$@" > pingu.log 2>&1
fi
exec .venv/bin/python main.py "$@"
