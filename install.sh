#!/usr/bin/env bash
# =============================================================================
#  Virtual Pet — Instalador
# =============================================================================
set -euo pipefail

# --- Colores ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}${BOLD}[·]${NC} $*"; }
success() { echo -e "${GREEN}${BOLD}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}${BOLD}[!]${NC} $*"; }
error()   { echo -e "${RED}${BOLD}[✗]${NC} $*"; exit 1; }
ask()     { echo -e "${YELLOW}${BOLD}[?]${NC} $*"; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${BOLD}🐧  Virtual Pet — Instalador${NC}"
echo "    $(echo "$INSTALL_DIR")"
echo "────────────────────────────────────────"
echo ""

# =============================================================================
# 1. Comprobar dependencias del sistema
# =============================================================================
info "Comprobando dependencias del sistema..."

command -v python3 &>/dev/null || error "Python 3 no encontrado. Instálalo con: sudo apt install python3"

PY_VERSION=$(python3 -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,6) else 1)' \
    || error "Se requiere Python 3.6 o superior (encontrado: $PY_VERSION)"

command -v pip3 &>/dev/null || command -v pip &>/dev/null \
    || error "pip no encontrado. Instálalo con: sudo apt install python3-pip"

success "Python 3 disponible"

# Verificar que hay display (necesario para PyQt5)
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    warn "No se detectó entorno gráfico (DISPLAY vacío). PyQt5 necesita un display."
fi

# =============================================================================
# 2. Crear entorno virtual
# =============================================================================
info "Creando entorno virtual en .venv..."

if [ -d "$INSTALL_DIR/.venv" ]; then
    warn "El entorno virtual ya existe, se reutilizará."
else
    python3 -m venv "$INSTALL_DIR/.venv"
    success "Entorno virtual creado"
fi

# Activar venv
# shellcheck disable=SC1091
source "$INSTALL_DIR/.venv/bin/activate"

# =============================================================================
# 3. Instalar dependencias Python
# =============================================================================
info "Instalando dependencias Python..."
pip install --quiet --upgrade pip
pip install --quiet -r "$INSTALL_DIR/requirements.txt"
success "Dependencias instaladas"

# =============================================================================
# 4. Configurar .env
# =============================================================================
echo ""
echo -e "${BOLD}── Configuración de Woffu ──────────────────${NC}"

if [ -f "$INSTALL_DIR/.env" ]; then
    warn "Ya existe un archivo .env."
    ask "¿Sobreescribir? (s/N): "
    read -r OVERWRITE
    [[ "$OVERWRITE" =~ ^[sS]$ ]] || { info "Manteniendo .env existente."; SKIP_ENV=1; }
fi

if [ "${SKIP_ENV:-0}" != "1" ]; then
    ask "Email de Woffu (ej: nombre.apellido@bsc.es):"
    read -r WOFFU_EMAIL

    ask "Contraseña de Woffu:"
    read -rs WOFFU_PASSWORD
    echo ""

    ask "Horas de jornada (Enter = 7):"
    read -r WOFFU_HOURS
    WOFFU_HOURS="${WOFFU_HOURS:-7}"

    ask "Hora de comida (Enter = 13:00):"
    read -r LUNCH_TIME
    LUNCH_TIME="${LUNCH_TIME:-13:00}"

    ask "Minutos de aviso previo a la comida (Enter = 10):"
    read -r LUNCH_REMINDER_MINUTES
    LUNCH_REMINDER_MINUTES="${LUNCH_REMINDER_MINUTES:-10}"

    ask "Interfaz VPN — OpenFortiVPN usa ppp0 (Enter = ppp0):"
    read -r VPN_INTERFACE
    VPN_INTERFACE="${VPN_INTERFACE:-ppp0}"

    cat > "$INSTALL_DIR/.env" <<EOF
# Woffu
WOFFU_URL=https://bsc.woffu.com
WOFFU_EMAIL=${WOFFU_EMAIL}
WOFFU_PASSWORD=${WOFFU_PASSWORD}
WOFFU_HOURS=${WOFFU_HOURS}

# Aviso de comida
LUNCH_TIME=${LUNCH_TIME}
LUNCH_REMINDER_MINUTES=${LUNCH_REMINDER_MINUTES}

# VPN — interfaz de red que crea OpenFortiVPN
VPN_INTERFACE=${VPN_INTERFACE}
# VPN — máquinas internas que se prueban por SSH (caída solo si fallan todas)
VPN_CHECK_HOSTS=opswebres01.bsc.es:22,opswebhpc01.bsc.es:22
EOF
    success ".env creado"
fi

# =============================================================================
# 5. Crear script de arranque
# =============================================================================
info "Creando script de arranque (run.sh)..."

cat > "$INSTALL_DIR/run.sh" <<EOF
#!/usr/bin/env bash
cd "\$(dirname "\$0")"
source .venv/bin/activate
python3 main.py "\$@"
EOF
chmod +x "$INSTALL_DIR/run.sh"
success "run.sh creado"

# =============================================================================
# 6. (Opcional) Crear entrada de autoarranque al iniciar sesión
# =============================================================================
echo ""
echo -e "${BOLD}── Autoarranque ────────────────────────────${NC}"
ask "¿Iniciar el pingüino automáticamente al abrir sesión? (s/N):"
read -r AUTOSTART

if [[ "$AUTOSTART" =~ ^[sS]$ ]]; then
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"

    cat > "$AUTOSTART_DIR/virtual-pet.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Virtual Pet
Comment=Animated desktop penguin
Exec=bash ${INSTALL_DIR}/run.sh
Icon=${INSTALL_DIR}/images/penguin_idle_01.png
X-GNOME-Autostart-enabled=true
Hidden=false
NoDisplay=false
EOF
    success "Autoarranque configurado (~/.config/autostart/virtual-pet.desktop)"
else
    info "Sin autoarranque. Puedes iniciarlo manualmente con: ./run.sh"
fi

# =============================================================================
# 7. (Opcional) Crear acceso directo en el escritorio
# =============================================================================
echo ""
DESKTOP_DIR="$HOME/Desktop"
[ -d "$HOME/Escritorio" ] && DESKTOP_DIR="$HOME/Escritorio"

if [ -d "$DESKTOP_DIR" ]; then
    ask "¿Crear acceso directo en el escritorio? (s/N):"
    read -r CREATE_SHORTCUT

    if [[ "$CREATE_SHORTCUT" =~ ^[sS]$ ]]; then
        cat > "$DESKTOP_DIR/Virtual Pet.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Virtual Pet
Comment=Animated desktop penguin
Exec=bash ${INSTALL_DIR}/run.sh
Icon=${INSTALL_DIR}/images/penguin_idle_01.png
Terminal=false
EOF
        chmod +x "$DESKTOP_DIR/Virtual Pet.desktop"
        success "Acceso directo creado en el escritorio"
    fi
fi

# =============================================================================
# Resumen final
# =============================================================================
echo ""
echo "────────────────────────────────────────"
echo -e "${GREEN}${BOLD}🐧  ¡Instalación completada!${NC}"
echo ""
echo -e "  Iniciar:      ${BOLD}./run.sh${NC}"
echo -e "  Controles:    ← → saltar, ↑ saltar, ↓ slide, A atacar"
echo -e "  Doble click:  chiste aleatorio"
echo -e "  Click derecho: menú (horas Woffu, VPN, cerrar)"
echo ""
