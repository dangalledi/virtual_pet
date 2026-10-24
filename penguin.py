"""El pingüino: animaciones, ratón, teclado, menú, globos y bandeja del sistema.
La lógica de trabajo (Woffu, VPN, calendario, Rocket.Chat) está en otros módulos."""
import math
import random
import datetime
import threading
from collections import deque

import requests
from PyQt5.QtWidgets import (QWidget, QLabel, QMenu, QDesktopWidget, QApplication,
                             QMessageBox, QSystemTrayIcon)
from PyQt5.QtGui import (QPixmap, QTransform, QIcon, QImage, QPainter, QRegion, QBitmap,
                         QDesktopServices)
from PyQt5.QtCore import Qt, QTimer, QPoint, QUrl, pyqtSignal

from utils import BASE_DIR, env_int, log, load_settings, save_settings
import calendario
import dosfa
import rocketchat
import vpn
from asistente import AsistenteWorker
from estado_rc import EstadoAuto
from globo import BubbleLabel

# Tamaño del pingüino en píxeles (el sprite original es de 200)
PENGUIN_SIZE = env_int("PENGUIN_SIZE", 100)
# Minutos que el pingüino se esconde en la barra con doble click
HIDE_MINUTES = env_int("HIDE_MINUTES", 30)
IMAGES_DIR = BASE_DIR / "images"

# Cómo se presenta cada tipo de aviso: (animación, tema del globo, duración ms; 0 = hasta click)
AVISOS = {
    "reunion": ("atack", None,                    0),
    "fichaje": ("atack", None,                    0),
    "resumen": ("jump",  BubbleLabel.THEME_OK,    0),
    "mensaje": ("jump",  BubbleLabel.THEME_MSG,   0),
    "pausa":   ("jump",  BubbleLabel.THEME_CALM,  0),
    "vpn_off": ("atack", BubbleLabel.THEME_ERROR, 0),
    "vpn_on":  (None,    BubbleLabel.THEME_OK,    4000),
    "jornada": ("jump",  None,                    6000),
    "comida":  ("jump",  None,                    15000),
    "bano":    ("atack", None,                    8000),
}

# Velocidad de la animación (ms entre imágenes): quieto va más lento para gastar menos
FRAME_MS_QUIETO = 250
FRAME_MS_MOVIMIENTO = 120

# Valor de cada opción del menú mientras no la cambies (se guarda en settings.json)
OPCIONES_POR_DEFECTO = {
    "avisos_reuniones": True,
    "avisos_dm":        True,
    "pausas":           True,
    "estado_auto":      False,   # cambiar tu estado de Rocket.Chat solo es opcional
}

# Si al código 2FA le quedan menos de estos segundos, se espera al siguiente
DOSFA_MARGEN = 5


class PenguinCharacter(QWidget):
    _bubble_ready  = pyqtSignal(str, str)         # hilo → UI: (texto, tipo de aviso o "")
    _fichaje_hecho = pyqtSignal(str, bool, bool)  # hilo → UI: (mensaje, ok, fue_salida)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.initUI()
        self.loadAnimations()
        self.current_state = "idle"
        self.current_frame_index = 0
        self.facing = "right"  # "right" o "left"
        self.speed = 10        # píxeles de movimiento por actualización
        self.moving_right = False
        self.moving_left = False
        self.slide_dx = 0
        self.slide_dy = 0

        # Burbuja de texto flotante y cola de avisos pendientes
        self.bubble = None
        self.bubble_active = False   # cuando True, no robamos el foco
        self.bubble_sticky = False   # el globo actual es un aviso que espera tu click
        self._avisos_pendientes = deque()
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self._hide_bubble)

        # Detección de clicks múltiples (1=drag, 2=esconderse, 3=chiste)
        self._click_count = 0
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(350)
        self._click_timer.timeout.connect(self._on_click_timeout)

        self._bubble_ready.connect(self._show_ready)
        self._fichaje_hecho.connect(self._on_fichaje_hecho)

        self.settings = load_settings()
        self.woffu_status_text = "Woffu: cargando..."

        self.setupTimer()
        self._start_rocketchat()
        self._start_asistente()
        self._setup_tray()

    # =======================================================================
    # Ventana y animaciones
    # =======================================================================
    def initUI(self):
        # Fondo transparente y ventana sin bordes
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel(self)
        # El label es transparente al ratón para que los clicks lleguen al widget
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.move(100, 800)  # Posición inicial
        self.setFixedSize(PENGUIN_SIZE, PENGUIN_SIZE)
        self.label.setFixedSize(PENGUIN_SIZE, PENGUIN_SIZE)

    def loadImage(self, name):
        pix = QPixmap(str(IMAGES_DIR / name))
        if pix.isNull():
            log(f"Error al cargar {name}")
            return None
        return pix.scaled(PENGUIN_SIZE, PENGUIN_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _frames(self, prefix: str, count: int) -> list:
        frames = [self.loadImage(f"penguin_{prefix}_{i:02d}.png") for i in range(1, count + 1)]
        return [f for f in frames if f]

    def loadAnimations(self):
        self.animations = {
            "idle":      self._frames("idle", 4),
            "walk":      self._frames("walk", 8),
            "jump":      self._frames("jump", 3),
            "atack":     self._frames("atack", 3),
            "pre_slide": self._frames("preslide", 1),
            "slide":     self._frames("slide", 3),
        }
        self.current_frames = self.animations["idle"]
        self.current_frame_index = 0
        if self.current_frames:
            self.label.setPixmap(self.current_frames[0])

    def setupTimer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateAnimation)
        self.timer.start(FRAME_MS_QUIETO)

    def updateAnimation(self):
        if not self.bubble_active:
            self.setFocus()  # Mantener el foco solo cuando no hay burbuja abierta

        if not self.current_frames:
            return

        self.current_frame_index = (self.current_frame_index + 1) % len(self.current_frames)
        current_pix = self.current_frames[self.current_frame_index]
        if self.facing == "left":
            current_pix = current_pix.transformed(QTransform().scale(-1, 1))
        self.label.setPixmap(current_pix)

        last = self.current_frame_index == len(self.current_frames) - 1

        # Si estamos en pre_slide y llegamos al final, pasamos a slide
        if self.current_state == "pre_slide" and last:
            self.setState("slide")

        if self.current_state == "walk":
            self.move(self.x() + (self.speed if self.facing == "right" else -self.speed), self.y())

        # Salto simple: sube en el primer frame y baja en el último
        if self.current_state == "jump":
            if self.current_frame_index == 0:
                self.move(self.x(), self.y() - self.speed)
            elif last:
                self.move(self.x(), self.y() + self.speed)
                self.setState("idle")

        if self.current_state == "slide":
            self._slide_step()

        if self.current_state == "atack" and last:
            self.setState("idle")

    def _slide_step(self):
        """Desliza en diagonal rebotando en los bordes de la pantalla."""
        screen = QDesktopWidget().screenGeometry()
        new_x = self.x() + self.slide_dx
        new_y = self.y() + self.slide_dy

        if new_x < 0:
            new_x = 0
            self.slide_dx = -self.slide_dx
            self.facing = "right"
        elif new_x + self.width() > screen.width():
            new_x = screen.width() - self.width()
            self.slide_dx = -self.slide_dx
            self.facing = "left"

        if new_y < 0:
            new_y = 0
            self.slide_dy = -self.slide_dy
        elif new_y + self.height() > screen.height():
            new_y = screen.height() - self.height()
            self.slide_dy = -self.slide_dy

        self.move(new_x, new_y)

    def setState(self, state):
        self.current_state = state
        self.timer.setInterval(FRAME_MS_QUIETO if state == "idle" else FRAME_MS_MOVIMIENTO)

        if state == "slide":
            # Uno de los 4 ángulos diagonales
            angulo = math.radians(random.choice([45, 135, 225, 315]))
            slide_speed = 50
            self.slide_dx = int(slide_speed * math.cos(angulo))
            self.slide_dy = int(slide_speed * math.sin(angulo))
            self.facing = "right" if self.slide_dx > 0 else "left"
        elif state != "pre_slide":
            self.slide_dx = 0
            self.slide_dy = 0

        self.current_frames = self.animations.get(state) or self.animations["idle"]
        self.current_frame_index = 0
        current_pix = self.current_frames[0]
        if self.facing == "left":
            current_pix = current_pix.transformed(QTransform().scale(-1, 1))
        self.label.setPixmap(current_pix)

    # =======================================================================
    # Teclado
    # =======================================================================
    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_Left):
            if event.isAutoRepeat():
                return
            if key == Qt.Key_Right:
                self.moving_right, self.facing = True, "right"
            else:
                self.moving_left, self.facing = True, "left"
            if self.current_state not in ["walk", "jump", "slide", "pre_slide"]:
                self.setState("walk")
        elif key == Qt.Key_Up:
            if not event.isAutoRepeat() and self.current_state != "jump":
                self.setState("jump")
        elif key == Qt.Key_Down:
            if not event.isAutoRepeat() and self.current_state not in ["pre_slide", "slide"]:
                self.setState("pre_slide")
        elif key == Qt.Key_A:
            if not event.isAutoRepeat() and self.current_state != "atack":
                self.setState("atack")
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key_Right:
            self.moving_right = False
        elif event.key() == Qt.Key_Left:
            self.moving_left = False
        elif event.key() == Qt.Key_Down and self.current_state in ["pre_slide", "slide"]:
            self.setState("idle")
        # Si no queda ninguna tecla lateral pulsada, deja de andar
        if not (self.moving_right or self.moving_left) and self.current_state == "walk":
            self.setState("idle")
        else:
            super().keyReleaseEvent(event)

    # =======================================================================
    # Ratón: arrastrar, 2 clicks = esconderse, 3 clicks = chiste
    # =======================================================================
    def mouseDoubleClickEvent(self, event):
        # En Linux Qt dispara este evento en vez del segundo mousePressEvent
        self.mousePressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            self._click_count += 1
            self._click_timer.start()   # reinicia la ventana de tiempo
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def _on_click_timeout(self):
        n, self._click_count = self._click_count, 0
        if n == 2:
            self.hide_to_tray()
        elif n >= 3:
            self._fetch_joke()

    def focusOutEvent(self, event):
        if self.bubble_active and not self.bubble_sticky:
            self._hide_bubble()
        super().focusOutEvent(event)

    def closeEvent(self, event):
        log("Cerrando el programa")
        QApplication.instance().quit()

    # =======================================================================
    # Menú (click derecho)
    # =======================================================================
    def contextMenuEvent(self, event):
        a = self.asistente
        w = a.woffu
        menu = QMenu(self)
        acciones = {}   # QAction → función a ejecutar

        def item(texto, func, checked=None, enabled=True, parent=menu):
            act = parent.addAction(texto)
            if checked is not None:
                act.setCheckable(True)
                act.setChecked(checked)
            act.setEnabled(enabled)
            acciones[act] = func
            return act

        estado = menu.addAction(f"⏱ {self.woffu_status_text}")
        estado.setEnabled(False)
        menu.addSeparator()

        # --- Woffu ---
        item("📋 Resumen del día", lambda: self._run_and_show(a.resumen_texto, "resumen"))
        item("⏱ Horas de hoy", lambda: self._run_and_show(w.horas_detalle))
        item({True: "🕒 Fichar salida…", False: "🕒 Fichar entrada…"}.get(w.clocked_in, "🕒 Fichar…"),
             self._fichar)
        item("☀️ Jornada intensiva hoy", self._toggle_intensiva,
             checked=w.es_intensiva(), enabled=not w.es_verano())   # en verano va sola
        if calendario.ausencias_configurado():
            sub = menu.addMenu("🏖️ Ausencias del equipo")
            item("Hoy", lambda: self._run_and_show(a.ausentes_texto), parent=sub)
            item("Esta semana", lambda: self._run_and_show(lambda: a.ausencias_semana_texto(0)),
                 parent=sub)
            item("Próxima semana", lambda: self._run_and_show(lambda: a.ausencias_semana_texto(1)),
                 parent=sub)

        # --- Reuniones ---
        if calendario.sogo_configurado():
            menu.addSeparator()
            item("📅 Reuniones de hoy", lambda: self._run_and_show(a.reuniones_texto))
            item(f"🔔 Avisarme {a.reunion_aviso_min} min antes de reuniones",
                 lambda: self._toggle("avisos_reuniones"), checked=a.avisos_reuniones)

        # --- Rocket.Chat ---
        if self.rc_client:
            menu.addSeparator()
            item("💬 Avisarme de mensajes y menciones",
                 lambda: self._toggle("avisos_dm"), checked=self.rc_worker.activo)
            item("🤖 Estado automático en Rocket.Chat",
                 lambda: self._toggle("estado_auto"), checked=self.estado_rc.activo)
            sub = menu.addMenu("🟢 Cambiar estado en Rocket.Chat")
            for status, (emoji, nombre) in rocketchat.ESTADOS.items():
                item(f"{emoji} {nombre}", lambda s=status: self._set_estado_manual(s), parent=sub)

        # --- Bienestar y otros ---
        menu.addSeparator()
        if dosfa.configurado():
            item("🔐 Copiar código 2FA", self.copiar_2fa)
        item(f"🧘 Recordarme hacer pausas (cada {a.pausa_cada} min)",
             lambda: self._toggle("pausas"), checked=a.pausas_activas)
        if vpn.comando_conexion():
            item("🔌 Conectar VPN", self.conectar_vpn)
        item("📶 Comprobar VPN", self._check_vpn_now)
        item("😂 Cuéntame un chiste", self._fetch_joke)
        item(f"🙈 Esconderme {HIDE_MINUTES} min", self.hide_to_tray)
        item("Cerrar", self.close)

        action = menu.exec_(event.globalPos())
        if action in acciones:
            acciones[action]()

    def _toggle(self, clave: str):
        """Activa/desactiva una opción del menú y la guarda en settings.json."""
        activo = not self.opcion(clave)
        self.settings[clave] = activo
        save_settings(self.settings)
        self._aplicar_settings()
        textos = {
            "avisos_reuniones": ("🔔 Te avisaré antes de cada reunión", "🔕 Sin avisos de reuniones"),
            "avisos_dm":        ("💬 Te avisaré de mensajes y menciones", "🔕 Sin avisos de mensajes"),
            "estado_auto":      ("🤖 Cambiaré tu estado de Rocket.Chat solo:\n"
                                 "reunión → No molestar · escondido o fuera → Ausente",
                                 "Estado de Rocket.Chat solo a mano"),
            "pausas":           ("🧘 Te recordaré hacer pausas", "Sin recordatorios de pausas"),
        }
        si, no = textos[clave]
        log(f"{clave}: {'activado' if activo else 'desactivado'}")
        self.show_bubble(si if activo else no, duration_ms=4000,
                         theme=BubbleLabel.THEME_OK if activo else None)
        if clave == "estado_auto" and activo:
            self.estado_rc.actualizar()

    def opcion(self, clave: str) -> bool:
        return self.settings.get(clave, OPCIONES_POR_DEFECTO[clave])

    def _aplicar_settings(self):
        self.asistente.avisos_reuniones = self.opcion("avisos_reuniones")
        self.asistente.pausas_activas   = self.opcion("pausas")
        if self.rc_client:
            self.rc_worker.activo = self.opcion("avisos_dm")
            self.estado_rc.activo = self.opcion("estado_auto")

    def _toggle_intensiva(self):
        w = self.asistente.woffu
        activa = w.intensiva_date != datetime.date.today()
        w.intensiva_date = datetime.date.today() if activa else None
        self.show_bubble("☀️ Hoy jornada intensiva" if activa else "Jornada normal hoy",
                         duration_ms=3000)

    def _run_and_show(self, func, tipo: str = ""):
        """Ejecuta func (hace peticiones de red) en un hilo y muestra su texto."""
        self.show_bubble("⏳ Consultando…", duration_ms=10000)
        threading.Thread(target=lambda: self._bubble_ready.emit(func(), tipo), daemon=True).start()

    def _show_ready(self, texto: str, tipo: str):
        """Resultado de una consulta del menú (llega desde otro hilo)."""
        self.show_bubble(texto, theme=AVISOS[tipo][1] if tipo else None)

    def _fetch_joke(self):
        """Pide un chiste a la API en un hilo y lo muestra en la burbuja."""
        def fetch():
            try:
                resp = requests.get("https://v2.jokeapi.dev/joke/Any",
                                    params={"lang": "es", "type": "single", "safe-mode": "",
                                            "blacklistFlags": "nsfw,sexist,explicit"},
                                    timeout=5)
                resp.raise_for_status()
                data = resp.json()
                if data.get("error"):
                    raise ValueError(data.get("message", "API error"))
                joke = data.get("joke") or f"{data.get('setup', '')}\n\n— {data.get('delivery', '')}"
            except Exception as e:
                log(f"[JOKE] Error: {e}")
                joke = "😅 No pude cargar un chiste... ¡pero tú eres gracioso/a!"
            self._bubble_ready.emit(joke, "")
        threading.Thread(target=fetch, daemon=True).start()

    def conectar_vpn(self):
        """Abre una terminal con el comando de la VPN (las contraseñas las escribes tú)."""
        if self.asistente.vpn.monitor.conectada:
            self.show_bubble("🟢 La VPN ya está conectada", duration_ms=4000,
                             theme=BubbleLabel.THEME_OK)
            return
        if vpn.conexion_en_marcha():
            self.show_bubble("⏳ Ya hay una conexión de VPN en marcha\n(mira la ventana «VPN»)",
                             duration_ms=5000)
            return
        error = vpn.conectar_en_terminal()
        if error:
            self.show_bubble(f"❌ {error}", duration_ms=6000, theme=BubbleLabel.THEME_ERROR)
            return
        texto = "🔌 Te he abierto la terminal de la VPN:\nescribe ahí tus contraseñas."
        if dosfa.configurado():
            self.show_bubble(texto + "\n\n🔐 Si te pide el código 2FA,\nclick aquí para copiarlo",
                             duration_ms=60000, theme=BubbleLabel.THEME_OK,
                             on_click=self.copiar_2fa)
        else:
            self.show_bubble(texto, duration_ms=8000, theme=BubbleLabel.THEME_OK)

    def copiar_2fa(self):
        """Copia el código 2FA al portapapeles (como `my2fa`). Si está a punto de
        caducar, espera al siguiente para que te dé tiempo a pegarlo."""
        quedan = dosfa.segundos_restantes()
        if quedan < DOSFA_MARGEN:
            self._aviso_2fa(f"⏳ El código cambia en {quedan} s, espero al siguiente…", 0)
            QTimer.singleShot((quedan + 1) * 1000, self.copiar_2fa)
            return
        try:
            code = dosfa.codigo()
        except RuntimeError as e:
            log(f"[2FA] {e}")
            self._aviso_2fa(f"❌ No pude generar el código 2FA\n{e}", 5000, error=True)
            return
        QApplication.clipboard().setText(code)
        self._2fa_code = code
        log("[2FA] Código copiado al portapapeles")
        self._aviso_2fa(f"🔐 {code} copiado\nPégalo con Ctrl+V · caduca en {quedan} s", quedan * 1000)
        # Al caducar, si sigue en el portapapeles, se borra
        QTimer.singleShot(quedan * 1000 + 500, self._limpiar_2fa)

    def _aviso_2fa(self, texto: str, ms: int, error: bool = False):
        """Globo del 2FA; si el pingüino está escondido, sale como notificación."""
        if self.isVisible():
            self.show_bubble(texto, duration_ms=ms or 3000,
                             theme=BubbleLabel.THEME_ERROR if error else BubbleLabel.THEME_OK)
        elif self.tray:
            self.tray.showMessage("Código 2FA", texto,
                                  QSystemTrayIcon.Warning if error else QSystemTrayIcon.Information,
                                  ms or 3000)

    def _limpiar_2fa(self):
        clip = QApplication.clipboard()
        if getattr(self, "_2fa_code", None) and clip.text() == self._2fa_code:
            clip.clear()
            log("[2FA] Código caducado: borrado del portapapeles")
        self._2fa_code = None

    def _check_vpn_now(self):
        def check():
            conectada, detalle = vpn.estado_ahora()
            self.asistente.vpn_changed.emit(conectada, detalle)
        threading.Thread(target=check, daemon=True).start()

    # =======================================================================
    # Esconderse en la barra de arriba (junto al reloj)
    # =======================================================================
    def _setup_tray(self):
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.show_from_tray)

        self.tray = None
        self._tray_intentos = 0
        self._crear_tray()

    def _crear_tray(self):
        # Al iniciar sesión la barra de GNOME puede tardar: se reintenta 2 min
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_intentos += 1
            if self._tray_intentos <= 24:
                QTimer.singleShot(5000, self._crear_tray)
            else:
                log("[TRAY] No hay bandeja del sistema (¿extensión AppIndicator desactivada?)")
            return
        self.tray = QSystemTrayIcon(self._tray_icon(str(IMAGES_DIR / "penguin_idle_01.png")), self)
        self.tray.activated.connect(self._on_tray_activated)
        menu = QMenu()
        menu.addAction("🐧 Volver ahora", self.show_from_tray)
        if dosfa.configurado():
            menu.addAction("🔐 Copiar código 2FA", self.copiar_2fa)
        menu.addAction("Cerrar", self.close)
        self.tray.setContextMenu(menu)
        self._tray_menu = menu   # mantener referencia

    @staticmethod
    def _tray_icon(path: str) -> QIcon:
        """Icono para la barra: recorta el margen transparente del sprite y lo deja
        cuadrado, para que el pingüino ocupe todo el hueco del icono."""
        img = QImage(path)
        if img.isNull():
            return QIcon()
        box = QRegion(QBitmap.fromImage(img.createAlphaMask())).boundingRect()
        if box.isEmpty():
            return QIcon(QPixmap.fromImage(img))
        side = max(box.width(), box.height())
        square = QImage(side, side, QImage.Format_ARGB32)
        square.fill(Qt.transparent)
        painter = QPainter(square)
        painter.drawImage((side - box.width()) // 2, (side - box.height()) // 2, img.copy(box))
        painter.end()
        return QIcon(QPixmap.fromImage(square))

    def hide_to_tray(self):
        if self.bubble_sticky and self.bubble:
            self._avisos_pendientes.appendleft(self._bubble_args)
        self.hide()             # primero esconder: así la cola no lo hace volver
        self._hide_bubble()
        self.timer.stop()       # sin animar mientras no se ve (ahorra batería)
        self.setState("idle")
        self._hide_timer.start(HIDE_MINUTES * 60 * 1000)
        vuelta = (datetime.datetime.now() + datetime.timedelta(minutes=HIDE_MINUTES)).strftime("%H:%M")
        if self.tray:
            self.tray.setToolTip(f"Pingüino escondido — vuelve a las {vuelta}")
            self.tray.show()
        if self.rc_client:
            self.estado_rc.actualizar(escondido=True)
        log(f"[TRAY] Escondido {HIDE_MINUTES} min (vuelve a las {vuelta})")

    def show_from_tray(self):
        self._hide_timer.stop()
        if self.tray:
            self.tray.hide()
        if not self.isVisible():
            self.timer.start()
            self.show()
            self.raise_()
            self.setFocus()
            if self.rc_client:
                self.estado_rc.actualizar(escondido=False)
            log("[TRAY] El pingüino vuelve")
            QTimer.singleShot(500, self._siguiente_aviso)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_from_tray()

    # =======================================================================
    # Asistente (Woffu, VPN, reuniones, pausas, resumen)
    # =======================================================================
    def _start_asistente(self):
        self.asistente = AsistenteWorker(self)
        self.asistente.resumen_date = self.settings.get("resumen_date")
        self.asistente.aviso.connect(self._on_aviso)
        self.asistente.horas_actualizadas.connect(self._on_horas_actualizadas)
        self.asistente.vpn_changed.connect(self._on_vpn_changed)
        self.asistente.reunion_en_curso.connect(self._on_reunion_en_curso)
        self.asistente.fichaje_cambiado.connect(self._on_fichaje_cambiado)
        self._aplicar_settings()
        self.asistente.start()

    def _on_aviso(self, texto: str, tipo: str):
        log(f"Aviso ({tipo}): {texto.splitlines()[0]}")
        if tipo == "resumen":
            self.settings["resumen_date"] = self.asistente.resumen_date
            save_settings(self.settings)
        self.avisar(texto, tipo)

    def _on_horas_actualizadas(self, texto: str):
        self.woffu_status_text = texto  # visible en el menú contextual

    def _on_vpn_changed(self, conectada: bool, detalle: str = ""):
        # El aviso contrario ya no vale: fuera de la cola y, si está a la vista, se cierra
        self._descartar_avisos("vpn_off" if conectada else "vpn_on")
        if conectada:
            self.avisar("🟢 VPN conectada", "vpn_on")
        else:
            texto = "🔴 VPN desconectada"
            if detalle:
                texto += f"\n{detalle}"
            if vpn.comando_conexion():
                self.avisar(texto + "\n\n(click aquí para conectarla)", "vpn_off",
                            on_click=self.conectar_vpn)
            else:
                self.avisar(texto + "\n¿Estás en la oficina o conectada a la VPN?", "vpn_off")

    def _on_reunion_en_curso(self, en_curso: bool):
        log(f"Reunión en curso: {en_curso}")
        if self.rc_client:
            self.estado_rc.actualizar(en_reunion=en_curso)

    def _on_fichaje_cambiado(self, dentro: bool):
        log(f"Fichaje: {'dentro' if dentro else 'fuera'}")
        if self.rc_client:
            self.estado_rc.actualizar(fuera=not dentro)

    def _fichar(self):
        estado = {True: "la salida", False: "la entrada"}.get(self.asistente.woffu.clocked_in, "")
        pregunta = f"¿Fichar {estado} ahora en Woffu?" if estado else "¿Fichar ahora en Woffu?"
        resp = QMessageBox.question(self, "Fichar", pregunta,
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        self.show_bubble("⏳ Fichando…", duration_ms=10000)
        threading.Thread(target=lambda: self._fichaje_hecho.emit(*self.asistente.fichar()),
                         daemon=True).start()

    def _on_fichaje_hecho(self, mensaje: str, ok: bool, fue_salida: bool):
        self.show_bubble(mensaje, duration_ms=5000,
                         theme=BubbleLabel.THEME_OK if ok else BubbleLabel.THEME_ERROR)
        if ok:
            self.setState("jump")
        if ok and fue_salida:
            resp = QMessageBox.question(self, "Comida", "¿Sales a comer? Te aviso a los 30 min.",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp == QMessageBox.Yes:
                self.asistente.start_lunch_timer(30)
                self.show_bubble("🍽️ ¡Que aproveche! Te aviso en 30 min.", duration_ms=4000)

    # =======================================================================
    # Rocket.Chat
    # =======================================================================
    def _start_rocketchat(self):
        self.rc_client = None
        if not rocketchat.configurado():
            log("Rocket.Chat no configurado: sin avisos de mensajes ni estado automático")
            return
        self.rc_client = rocketchat.RocketChatClient()
        self.estado_rc = EstadoAuto(self.rc_client)
        self.rc_worker = rocketchat.RocketChatWorker(self.rc_client, self)
        self.rc_worker.mensajes_nuevos.connect(self._on_mensaje)
        self.rc_worker.start()

    def _on_mensaje(self, texto: str, url: str):
        self.avisar(texto + "\n\n(click aquí para abrirlo)", "mensaje",
                    on_click=lambda: QDesktopServices.openUrl(QUrl(url)))

    def _set_estado_manual(self, status: str):
        emoji, nombre = rocketchat.ESTADOS[status]

        def run():
            ok = self.estado_rc.manual(status)
            self._bubble_ready.emit(f"{emoji} Estado: {nombre}" if ok
                                    else "❌ No pude cambiar el estado", "")
        threading.Thread(target=run, daemon=True).start()

    # =======================================================================
    # Globos de texto
    # =======================================================================
    def avisar(self, texto: str, tipo: str, on_click=None):
        """Aviso de los hilos de trabajo. Si ya hay un aviso esperando tu click,
        este se pone en cola y sale cuando cierres el anterior."""
        if self.bubble_sticky and self.bubble:
            self._avisos_pendientes.append((texto, tipo, on_click))
            return
        anim, theme, duration = AVISOS.get(tipo, (None, None, 0))
        if not self.isVisible():
            self.show_from_tray()   # un aviso le hace volver antes de tiempo
        if anim:
            self.setState(anim)
        self.show_bubble(texto, duration_ms=duration, theme=theme, on_click=on_click,
                         sticky=duration == 0)
        self._bubble_args = (texto, tipo, on_click)

    def show_bubble(self, text: str, duration_ms: int = 0, theme: tuple = None,
                    on_click=None, sticky: bool = False):
        """Muestra un globo encima del pingüino.
        duration_ms=0 → se cierra al hacer click (en él o fuera del pingüino).
        duration_ms>0 → se cierra también solo tras ese tiempo."""
        if not self.isVisible():
            self.show_from_tray()

        # Si había un aviso esperando click y esto lo tapa, se guarda para luego
        if self.bubble_sticky and self.bubble and not sticky:
            self._avisos_pendientes.appendleft(self._bubble_args)
        self._close_bubble_widget()

        self.bubble = BubbleLabel(text, theme=theme, on_click=on_click, on_close=self._hide_bubble)
        self.bubble.fit()
        self.bubble_sticky = sticky

        # Centrado encima del pingüino, sin salirse de la pantalla
        origin = self.mapToGlobal(QPoint(0, 0))
        screen = QDesktopWidget().screenGeometry(self)
        bx = origin.x() + (self.width() - self.bubble.width()) // 2
        bx = max(screen.left(), min(bx, screen.right() - self.bubble.width()))
        # El sprite tiene margen transparente arriba (65 px a tamaño 200):
        # la punta del piquito queda justo encima de la cabeza
        by = max(origin.y() - self.bubble.height() + 65 * PENGUIN_SIZE // 200, screen.top())
        # El piquito apunta al centro del pingüino aunque el globo se haya desplazado
        self.bubble.tail_x = origin.x() + self.width() // 2 - bx
        self.bubble.move(bx, by)
        self.bubble.show()

        self.bubble_active = True
        if duration_ms > 0:
            self.bubble_timer.start(duration_ms)
        else:
            self.bubble_timer.stop()

    def _close_bubble_widget(self):
        self.bubble_timer.stop()
        if self.bubble:
            self.bubble.hide()
            self.bubble.deleteLater()
            self.bubble = None

    def _hide_bubble(self):
        self._close_bubble_widget()
        self.bubble_active = False
        self.bubble_sticky = False
        self.setFocus()
        self._siguiente_aviso()

    def _siguiente_aviso(self):
        """Muestra el siguiente aviso de la cola en un momento, si para entonces
        no hay otro globo a la vista (p. ej. el que abre el click en un aviso)."""
        QTimer.singleShot(300, self._mostrar_siguiente)

    def _mostrar_siguiente(self):
        if self._avisos_pendientes and self.isVisible() and not self.bubble:
            self.avisar(*self._avisos_pendientes.popleft())

    def _descartar_avisos(self, tipo: str):
        """Quita de la cola los avisos de ese tipo y cierra el actual si es de ese tipo."""
        self._avisos_pendientes = deque(a for a in self._avisos_pendientes if a[1] != tipo)
        if self.bubble and self.bubble_sticky and self._bubble_args[1] == tipo:
            self._hide_bubble()

    # =======================================================================
    # Movimiento automático
    # =======================================================================
    def setupAutoMoveTimer(self):
        self.auto_move_timer = QTimer(self)
        self.auto_move_timer.timeout.connect(self.triggerAutoMove)
        self.auto_move_timer.start(60 * 1000)  # cada minuto

    def triggerAutoMove(self):
        if self.bubble_active or not self.isVisible():
            return   # quieto mientras enseña un globo, para que no se separe de él
        action = random.choice(["walk", "jump", "slide"])
        if action == "walk":
            self.facing = random.choice(["left", "right"])
            self.setState("walk")
            QTimer.singleShot(3000, lambda: self.setState("idle"))
        elif action == "jump":
            self.setState("jump")   # vuelve solo a idle
        else:
            self.setState("pre_slide")
            QTimer.singleShot(5000, lambda: self.setState("idle"))
