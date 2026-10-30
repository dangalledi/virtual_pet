"""El pingüino: animaciones, ratón, teclado, menú, globos y bandeja del sistema.
La lógica de trabajo (Woffu, VPN, calendario, Rocket.Chat) está en otros módulos."""
import math
import os
import sys
import random
import datetime
import threading
from collections import deque
from urllib.parse import urlparse

from PyQt5.QtWidgets import (QWidget, QLabel, QMenu, QDesktopWidget, QApplication,
                             QMessageBox, QSystemTrayIcon)
from PyQt5.QtGui import QPixmap, QTransform, QIcon, QImage, QPainter, QRegion, QBitmap
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal

from pingu import chistes, notas
from pingu.asistente import AsistenteWorker
from pingu.interfaz import configuracion, mascotas, postits
from pingu.interfaz.globo import BubbleLabel
from pingu.servicios import calendario, dosfa, rocketchat, vpn
from pingu.servicios.estado_rc import EstadoAuto
from pingu.utils import (BASE_DIR, NAVEGADORES, activar_ventana, env, env_int, log,
                         load_settings, save_settings, tamano_elegido, zoom_general)

# Tamaño del pingüino en píxeles (el sprite original es de 200)
PENGUIN_SIZE = env_int("PENGUIN_SIZE", 100)
# Alto de las otras mascotas (gato, pollo, pato): su dibujo ocupa todo el alto y el del
# pingüino no (su PNG tiene mucho margen), así que con un 60 % quedan de un tamaño parecido
MASCOTA_SIZE = env_int("MASCOTA_SIZE", PENGUIN_SIZE * 60 // 100)
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
    "nota":    ("jump",  None,                    0),
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
    "postits_siempre":  False,   # post-its siempre a la vista (si no, solo con Pingu en foco)
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
        self._config = None           # ventana de configuración abierta (o None)
        self.notas = notas.cargar()   # antes que la barra, que las pone en su menú
        self.woffu_status_text = "Woffu: cargando..."

        self.setupTimer()
        self._start_rocketchat()
        self._start_asistente()
        self._setup_tray()
        self._start_notas()

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
        # A la resolución real de la pantalla (con zoom), para que no se vea borroso
        dpr = QApplication.instance().devicePixelRatio()
        lado = round(self._lado_pingu() * dpr)
        pix = pix.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        return pix

    def _frames(self, prefix: str, count: int) -> list:
        frames = [self.loadImage(f"penguin_{prefix}_{i:02d}.png") for i in range(1, count + 1)]
        return [f for f in frames if f]

    def mascota_actual(self) -> tuple:
        """(clave, color) de la mascota elegida en el menú; ("pingu", "") por defecto."""
        clave, _, color = self._ajustes().get("mascota", mascotas.PINGU).partition(":")
        if clave != mascotas.PINGU and clave not in mascotas.CATALOGO:
            return mascotas.PINGU, ""
        return clave, color

    def _ajustes(self) -> dict:
        return getattr(self, "settings", None) or load_settings()

    def _escala(self, clave: str) -> float:
        """Tamaño elegido (tam_mascota / tam_postits), descontando el zoom general, que
        ya agranda todo lo de Qt: así en pantalla sale justo el tamaño elegido."""
        return tamano_elegido(self._ajustes(), clave) / zoom_general()

    def _lado_pingu(self) -> int:
        return max(20, round(PENGUIN_SIZE * self._escala("tam_mascota")))

    def _alto_mascota(self) -> int:
        return max(12, round(MASCOTA_SIZE * self._escala("tam_mascota")))

    def loadAnimations(self):
        clave, color = self.mascota_actual()
        cargada = (mascotas.cargar(clave, color, self._alto_mascota(),
                                   QApplication.instance().devicePixelRatio())
                   if clave != mascotas.PINGU else None)
        self.mascota_cargada = clave if cargada else mascotas.PINGU
        if cargada:
            self.animations, self.margen_arriba, ancho = cargada
            alto = self._alto_mascota()
        else:
            ancho = alto = self._lado_pingu()
            if clave != mascotas.PINGU:
                log(f"[MASCOTA] No pude cargar {clave} {color}: vuelvo al pingüino")
            self.animations = {
                "idle":      self._frames("idle", 4),
                "walk":      self._frames("walk", 8),
                "jump":      self._frames("jump", 3),
                "atack":     self._frames("atack", 3),
                "pre_slide": self._frames("preslide", 1),
                "slide":     self._frames("slide", 3),
            }
            # El sprite tiene margen transparente arriba (65 px a tamaño 200)
            self.margen_arriba = 65 * self._lado_pingu() // 200
        # La ventana se ajusta a la mascota sin moverla: mismo centro y mismo suelo
        if (ancho, alto) != (self.width(), self.height()):
            self.move(self.x() - (ancho - self.width()) // 2, self.y() - (alto - self.height()))
            self.setFixedSize(ancho, alto)
            self.label.setFixedSize(ancho, alto)
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
        self.activateWindow()   # coger el foco: así se ven los post-its
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
        self._parar_hilos()
        QApplication.instance().quit()

    def _parar_hilos(self):
        """Para los hilos de fondo antes de salir: si Qt los encuentra en marcha al
        cerrar, aborta el programa ("QThread: Destroyed while thread is still running")."""
        hilos = [getattr(self, "asistente", None), getattr(self, "rc_worker", None)]
        for hilo in filter(None, hilos):
            hilo.stop()
        for hilo in filter(None, hilos):
            hilo.wait(3000)   # si está a mitad de una consulta, main.py sale igualmente

    # =======================================================================
    # Menú (click derecho)
    # =======================================================================
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        self._llenar_menu(menu, en_barra=False)
        menu.exec_(event.globalPos())

    def _llenar_menu(self, menu: QMenu, en_barra: bool):
        """Opciones del pingüino. Las usan el click derecho y el icono de la barra
        (en_barra=True: con "Volver ahora" y sin "Esconderme")."""
        a = self.asistente
        w = a.woffu

        def item(texto, func, checked=None, enabled=True, parent=menu):
            act = parent.addAction(texto)
            if checked is not None:
                act.setCheckable(True)
                act.setChecked(checked)
            act.setEnabled(enabled)
            if en_barra:
                # Tras usar una opción, el menú de la barra se rehace (marcas, textos…)
                act.triggered.connect(lambda _=False: (func(), QTimer.singleShot(0, self._rehacer_menu_barra)))
            else:
                act.triggered.connect(lambda _=False: func())
            return act

        if en_barra:
            item("🐧 Volver ahora", self.show_from_tray)
            menu.addSeparator()
        estado = menu.addAction(f"⏱ {self.woffu_status_text}")
        estado.setEnabled(False)
        menu.addSeparator()

        # --- Consultas del día ---
        item("📋 Resumen del día", lambda: self._run_and_show(a.resumen_texto, "resumen"))
        item("⏱ Horas de hoy", lambda: self._run_and_show(w.horas_detalle))
        item({True: "🕒 Fichar salida…", False: "🕒 Fichar entrada…"}.get(w.clocked_in, "🕒 Fichar…"),
             self._fichar)
        if calendario.sogo_configurado():
            item("📅 Reuniones de hoy", lambda: self._run_and_show(a.reuniones_texto))
        if calendario.ausencias_configurado():
            sub = menu.addMenu("🏖️ Ausencias del equipo")
            item("Hoy", lambda: self._run_and_show(a.ausentes_texto), parent=sub)
            item("Esta semana", lambda: self._run_and_show(lambda: a.ausencias_semana_texto(0)),
                 parent=sub)
            item("Próxima semana", lambda: self._run_and_show(lambda: a.ausencias_semana_texto(1)),
                 parent=sub)

        # --- Herramientas ---
        menu.addSeparator()
        self._menu_notas(menu.addMenu("📝 Notas y recordatorios"), item)
        if self.rc_client:
            sub = menu.addMenu("🟢 Cambiar estado en Rocket.Chat")
            for status, (emoji, nombre) in rocketchat.ESTADOS.items():
                item(f"{emoji} {nombre}", lambda s=status: self._set_estado_manual(s), parent=sub)
        if dosfa.configurado():
            item("🔐 Copiar código 2FA", self.copiar_2fa)
        if vpn.comando_conexion():
            item("🔌 Conectar VPN", self.conectar_vpn)
        item("📶 Comprobar VPN", self._check_vpn_now)

        # --- Pingu ---
        menu.addSeparator()
        item("😂 Cuéntame un chiste", self._fetch_joke)
        if not en_barra:
            item(f"🙈 Esconderme {HIDE_MINUTES} min", self.hide_to_tray)
        item("⚙️ Configuración…", self.abrir_configuracion)
        item("Cerrar", self.close)

    def abrir_configuracion(self):
        """Ventana de configuración (una sola: si ya está abierta, se trae delante)."""
        if self._config is None:
            self._config = configuracion.VentanaConfig(self)
            self._config.destroyed.connect(lambda: setattr(self, "_config", None))
        self._config.show()
        self._config.raise_()
        self._config.activateWindow()

    def cambiar_tamano(self, clave: str, valor: float):
        """Tamaño de la mascota (tam_mascota) o de los post-its (tam_postits), al momento."""
        self.settings[clave] = valor
        save_settings(self.settings)
        if clave == "tam_mascota":
            self.loadAnimations()
            self.setState("idle")
            self._mantener_en_pantalla()
        else:
            self.tablero.poner_escala(self._escala("tam_postits"))

    def _mantener_en_pantalla(self):
        """Si al crecer se sale por un borde, la mete dentro."""
        pantalla = QDesktopWidget().availableGeometry(self)
        x = max(pantalla.left(), min(self.x(), pantalla.right() - self.width()))
        y = max(pantalla.top(), min(self.y(), pantalla.bottom() - self.height()))
        self.move(x, y)

    def cambiar_zoom(self, zoom: float):
        """Guarda el zoom y reinicia: Qt solo lo lee al arrancar (ver main.aplicar_zoom)."""
        if zoom == self.settings.get("zoom", 1):
            return
        self.settings["zoom"] = zoom
        save_settings(self.settings)
        log(f"Zoom {zoom}: reiniciando")
        self.show_bubble(f"🔍 Me pongo al {round(zoom * 100)} %…", duration_ms=1500,
                         theme=BubbleLabel.THEME_OK)
        QTimer.singleShot(1200, self._reiniciar)

    def _reiniciar(self):
        """Vuelve a arrancar el programa en el mismo proceso (el candado se suelta solo)."""
        if self.tray:
            self.tray.hide()
        self.tablero.cerrar_todos()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def cambiar_mascota(self, clave: str, color: str):
        anterior = self.settings.get("mascota", mascotas.PINGU)
        self.settings["mascota"] = f"{clave}:{color}" if clave != mascotas.PINGU else clave
        self.loadAnimations()
        if self.mascota_cargada != clave:   # no se pudo: se queda la de antes
            self.settings["mascota"] = anterior
            self.loadAnimations()
            texto, tema = "😕 No pude cargar esa mascota\n(mira pingu.log)", BubbleLabel.THEME_ERROR
        else:
            save_settings(self.settings)
            texto = f"¡Hola! Ahora soy un {mascotas.nombre(clave, color).split(' ', 1)[1].lower()}"
            tema = None
        self.setState("idle")
        if self.tray:
            self.tray.setIcon(self._icono_mascota())
        self.show_bubble(texto, duration_ms=4000, theme=tema)

    def _menu_notas(self, sub: QMenu, item):
        item("⏰ Recuérdame…", lambda: self._nueva_nota(recordatorio=True), parent=sub)
        item("📝 Nueva nota…", lambda: self._nueva_nota(recordatorio=False), parent=sub)
        sub.addSeparator()
        if not self.notas:
            return
        item("👀 Verlas todas", lambda: self.show_bubble(notas.texto_lista(self.notas)), parent=sub)
        sub.addSeparator()
        for nota in notas.ordenadas(self.notas):
            una = sub.addMenu(notas.etiqueta(nota))
            item("👀 Ver", lambda n=nota: self.show_bubble("📝 " + n["texto"]), parent=una)
            item("✏️ Editar…", lambda n=nota: self._editar_nota(n), parent=una)
            for nombre, minutos in notas.POSPONER:
                item(f"⏰ Avisarme {nombre.lower()}",
                     lambda n=nota, m=minutos: self._avisar_nota_en(n, m), parent=una)
            if nota.get("aviso"):
                item("🔕 Quitar el aviso", lambda n=nota: self._avisar_nota_en(n, None), parent=una)
            item("✅ Hecho (borrar)", lambda n=nota: self._borrar_nota(n), parent=una)

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
            "postits_siempre":  ("📌 Post-its siempre a la vista",
                                 "📌 Post-its solo cuando me tocas"),
        }
        si, no = textos[clave]
        log(f"{clave}: {'activado' if activo else 'desactivado'}")
        self.show_bubble(si if activo else no, duration_ms=4000,
                         theme=BubbleLabel.THEME_OK if activo else None)
        if clave == "estado_auto" and activo:
            self.estado_rc.actualizar()

    def poner_opcion(self, clave: str, valor: bool):
        """Desde la ventana de configuración: activa/desactiva (si no lo estaba ya)."""
        if self.opcion(clave) != valor:
            self._toggle(clave)
            if not self.isVisible():
                self._rehacer_menu_barra()

    def poner_intensiva(self, valor: bool):
        if self.asistente.woffu.es_intensiva() != valor:
            self._toggle_intensiva()

    def opcion(self, clave: str) -> bool:
        return self.settings.get(clave, OPCIONES_POR_DEFECTO[clave])

    def _aplicar_settings(self):
        self.asistente.avisos_reuniones = self.opcion("avisos_reuniones")
        self.asistente.pausas_activas   = self.opcion("pausas")
        if self.rc_client:
            self.rc_worker.activo = self.opcion("avisos_dm")
            self.estado_rc.activo = self.opcion("estado_auto")
        if hasattr(self, "tablero"):
            self._revisar_foco()

    def _toggle_intensiva(self):
        w = self.asistente.woffu
        activa = w.intensiva_date != datetime.date.today()
        w.intensiva_date = datetime.date.today() if activa else None
        # Se guarda para que un reinicio de Pingu no la quite (vale solo para hoy)
        if activa:
            self.settings["intensiva"] = datetime.date.today().isoformat()
        else:
            self.settings.pop("intensiva", None)
        save_settings(self.settings)
        self.asistente.refrescar()   # el estado de Woffu, recalculado ya
        self.show_bubble("☀️ Hoy jornada intensiva" if activa else "Jornada normal hoy",
                         duration_ms=3000)

    def _run_and_show(self, func, tipo: str = ""):
        """Ejecuta func (hace peticiones de red) en un hilo y muestra su texto."""
        if self.isVisible():
            self.show_bubble("⏳ Consultando…", duration_ms=10000)
        threading.Thread(target=lambda: self._bubble_ready.emit(func(), tipo), daemon=True).start()

    def _show_ready(self, texto: str, tipo: str):
        """Resultado de una consulta del menú (llega desde otro hilo)."""
        self.show_bubble(texto, theme=AVISOS[tipo][1] if tipo else None)

    def _fetch_joke(self):
        """Cuenta un chiste: primero el planteamiento y, un momento después, el remate."""
        planteamiento, remate = chistes.siguiente(self.settings)
        save_settings(self.settings)
        self.show_bubble("😄 " + planteamiento + ("\n\n…" if remate else ""))
        if not remate:
            return
        globo = self.bubble

        def remata():
            # Solo si sigue a la vista el mismo globo (no lo has cerrado ni lo ha tapado otro aviso)
            if self.bubble is globo and globo is not None:
                self.show_bubble("😄 " + planteamiento + "\n\n" + remate)
        QTimer.singleShot(2500, remata)

    # =======================================================================
    # Notas y recordatorios
    # =======================================================================
    def _start_notas(self):
        self.tablero = postits.Tablero(hecho=self._borrar_nota, editar=self._editar_nota,
                                       avisar=self._avisar_nota_en,
                                       cambiado=lambda: notas.guardar(self.notas))
        self.tablero.poner_escala(self._escala("tam_postits"))
        self.tablero.sincronizar(self.notas)
        # Post-its a la vista solo mientras alguna ventana de Pingu tiene el foco.
        # Se espera un poco antes de esconderlos: al pasar el foco del pingüino a un
        # post-it (para arrastrarlo) la aplicación queda "inactiva" un instante.
        self._foco_timer = QTimer(self)
        self._foco_timer.setSingleShot(True)
        self._foco_timer.timeout.connect(self._revisar_foco)
        QApplication.instance().applicationStateChanged.connect(
            lambda _estado: self._foco_timer.start(250))
        self._revisar_foco()
        self._notas_timer = QTimer(self)
        self._notas_timer.timeout.connect(self._revisar_notas)
        self._notas_timer.start(20000)
        QTimer.singleShot(3000, self._revisar_notas)   # los que vencieron con el pingüino cerrado

    def _revisar_notas(self):
        ahora = datetime.datetime.now()
        vencidas = notas.vencidas(self.notas)
        for texto, cuando in vencidas:
            aviso = f"⏰ ¡Acuérdate!\n\n{texto}"
            if ahora - cuando > datetime.timedelta(minutes=5):
                aviso += f"\n\n(era para las {cuando.strftime('%H:%M')})"
            log(f"[NOTAS] Aviso: {texto!r}")
            self.avisar(aviso, "nota")
        if vencidas:
            self._notas_cambiadas()
        if not self.isVisible():
            self._rehacer_menu_barra()

    def _nueva_nota(self, recordatorio: bool):
        dialogo = notas.DialogoNota(recordatorio, parent=self if self.isVisible() else None)
        dialogo.activateWindow()
        if dialogo.exec_() != notas.DialogoNota.Accepted:
            return
        texto, aviso = dialogo.texto_escrito(), dialogo.aviso()
        notas.nueva(self.notas, texto, aviso, fija=not recordatorio, color=dialogo.color())
        self._notas_cambiadas()
        if aviso:
            dia = "" if aviso.date() == datetime.date.today() else "mañana "
            self.show_bubble(f"⏰ Vale, te aviso {dia}a las {aviso.strftime('%H:%M')}",
                             duration_ms=4000, theme=BubbleLabel.THEME_OK)
        else:
            self.show_bubble("📝 Apuntado", duration_ms=3000, theme=BubbleLabel.THEME_OK)

    def _editar_nota(self, nota: dict):
        dialogo = notas.DialogoNota(not nota.get("fija", True), nota=nota,
                                    parent=self if self.isVisible() else None)
        dialogo.activateWindow()
        if dialogo.exec_() != notas.DialogoNota.Accepted or nota not in self.notas:
            return
        nota["texto"] = dialogo.texto_escrito()
        if dialogo.color():
            nota["color"] = dialogo.color()
        notas.guardar(self.notas)
        self._notas_cambiadas()

    def _avisar_nota_en(self, nota: dict, minutos):
        notas.poner_aviso(self.notas, nota, notas.en_minutos(minutos) if minutos else None)
        self._notas_cambiadas()
        texto = f"⏰ Te aviso en {minutos} min" if minutos else "🔕 Aviso quitado"
        self.show_bubble(texto, duration_ms=3000, theme=BubbleLabel.THEME_OK)

    def _borrar_nota(self, nota: dict):
        notas.borrar(self.notas, nota)
        self._notas_cambiadas()
        self.show_bubble("✅ ¡Una cosa menos!", duration_ms=3000, theme=BubbleLabel.THEME_OK)

    def _revisar_foco(self):
        activa = QApplication.applicationState() == Qt.ApplicationActive
        self.tablero.mostrar(self.opcion("postits_siempre") or activa)

    def _notas_cambiadas(self):
        """Pone los post-its (y el menú de la barra) al día con la lista de notas."""
        self.tablero.sincronizar(self.notas)
        if not self.isVisible():
            self._rehacer_menu_barra()

    def conectar_vpn(self):
        """Abre una terminal con el comando de la VPN (las contraseñas las escribes tú)."""
        monitor = self.asistente.vpn.monitor
        if monitor.conectada:
            texto = ("🏢 Estás en la red de la oficina:\nno hace falta la VPN"
                     if monitor.en_oficina else "🟢 La VPN ya está conectada")
            self.show_bubble(texto, duration_ms=4000, theme=BubbleLabel.THEME_OK)
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
        """Globo del 2FA (si está escondido, show_bubble lo saca como notificación)."""
        self.show_bubble(texto, duration_ms=ms or 3000,
                         theme=BubbleLabel.THEME_ERROR if error else BubbleLabel.THEME_OK)

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
        self.tray = QSystemTrayIcon(self._icono_mascota(), self)
        self.tray.activated.connect(self._on_tray_activated)
        self._tray_menu = QMenu()   # mantener referencia
        self.tray.setContextMenu(self._tray_menu)
        self._rehacer_menu_barra()

    def _rehacer_menu_barra(self):
        """El menú del icono de la barra = el del click derecho (con lo de ahora mismo)."""
        if not self.tray:
            return
        self._tray_menu.clear()
        self._llenar_menu(self._tray_menu, en_barra=True)

    def _icono_mascota(self) -> QIcon:
        if self.mascota_cargada == mascotas.PINGU or not self.animations.get("idle"):
            return self._tray_icon(QImage(str(IMAGES_DIR / "penguin_idle_01.png")))
        return self._tray_icon(self.animations["idle"][0].toImage())

    @staticmethod
    def _tray_icon(img: QImage) -> QIcon:
        """Icono para la barra: recorta el margen transparente del sprite y lo deja
        cuadrado, para que la mascota ocupe todo el hueco del icono."""
        if img.isNull():
            return QIcon()
        img.setDevicePixelRatio(1)   # con zoom el sprite viene a más resolución: se usa tal cual
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
            self._rehacer_menu_barra()
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
        if self.settings.get("intensiva") == datetime.date.today().isoformat():
            self.asistente.woffu.intensiva_date = datetime.date.today()   # puesta hoy antes de reiniciar
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
        if not self.isVisible():
            self._rehacer_menu_barra()  # la línea de estado del menú de la barra

    def _on_vpn_changed(self, conectada: bool, detalle: str = ""):
        # El aviso contrario ya no vale: fuera de la cola y, si está a la vista, se cierra
        self._descartar_avisos("vpn_off" if conectada else "vpn_on")
        if conectada and detalle == vpn.OFICINA:
            self.avisar("🏢 Estás en la red de la oficina:\nno hace falta la VPN", "vpn_on")
        elif conectada:
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
        self.avisar(texto + "\n\n(click para ir al navegador)", "mensaje",
                    on_click=self._ir_a_rocketchat)

    def _ir_a_rocketchat(self):
        """Trae al frente tu navegador sin abrir pestañas nuevas: la ventana que
        tenga Rocket.Chat a la vista si la hay, y si no, la del navegador."""
        # Las pestañas de Rocket.Chat acaban en "- chat.empresa.com" (el dominio de
        # ROCKET_CHAT_URL), cambie como cambie el nombre del chat
        dominio = urlparse(self.rc_client.url).hostname or ""
        titulo_rc = env("ROCKET_CHAT_WINDOW_TITLE", dominio or "Rocket.Chat")
        if not activar_ventana(titulo_rc, *NAVEGADORES):
            log("[RC] No encontré la ventana del navegador")

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
        duration_ms>0 → se cierra también solo tras ese tiempo.
        Si está escondido, sale como notificación y sigue escondido (los avisos
        importantes pasan por avisar(), que sí lo hace volver)."""
        if not self.isVisible():
            if self.tray:
                icono = (QSystemTrayIcon.Warning if theme == BubbleLabel.THEME_ERROR
                         else QSystemTrayIcon.Information)
                self.tray.showMessage("Pingu", text, icono, duration_ms or 10000)
                return
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
        # La punta del piquito queda justo encima de la cabeza (el sprite tiene margen arriba)
        by = max(origin.y() - self.bubble.height() + self.margen_arriba, screen.top())
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
