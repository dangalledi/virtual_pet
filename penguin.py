import sys
import random
import math
from PyQt5.QtWidgets import QWidget, QLabel, QMenu, QDesktopWidget, QApplication
from PyQt5.QtGui import QPixmap, QTransform
from PyQt5.QtCore import Qt, QTimer, QPoint

class PenguinCharacter(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)  # Para que se active el menú contextual
        self.initUI()
        self.loadAnimations()
        self.current_state = "idle"
        self.current_frame_index = 0
        self.facing = "right"  # "right" o "left"
        self.speed = 10  # píxeles de movimiento por actualización
        self.moving_right = False
        self.moving_left = False
        
        # Variables para controlar el movimiento de "slide"
        self.slide_dx = 0
        self.slide_dy = 0
        
        self.setupTimer()

    def initUI(self):
        # Fondo transparente y ventana sin bordes
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.move(1600, 800)  # Posición inicial

        # Fijar un tamaño constante (por ejemplo, 200x200)
        fixed_size = 200
        self.setFixedSize(fixed_size, fixed_size)
        self.label.setFixedSize(fixed_size, fixed_size)

    def loadImage(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            print(f"[DEBUG] Error al cargar {path}")
            return None
        # Escalar todas las imágenes a un tamaño fijo (200x200 en este caso)
        scaled_pix = pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return scaled_pix

    def loadAnimations(self):
        self.animations = {}

        # Animación idle: 4 sprites (ej. penguin_idle_01.png a penguin_idle_04.png)
        idle_frames = []
        for i in range(1, 5):
            pix = self.loadImage(f"images/penguin_idle_{i:02d}.png")
            if pix:
                idle_frames.append(pix)
        self.animations["idle"] = idle_frames if idle_frames else [self.loadImage("images/penguin_idle_01.png")]

        # Animación de caminar: 8 frames
        walk_frames = []
        for i in range(1, 9):
            pix = self.loadImage(f"images/penguin_walk_{i:02d}.png")
            if pix:
                walk_frames.append(pix)
        self.animations["walk"] = walk_frames

        # Animación de saltar: 3 frames
        jump_frames = []
        for i in range(1, 4):
            pix = self.loadImage(f"images/penguin_jump_{i:02d}.png")
            if pix:
                jump_frames.append(pix)
        self.animations["jump"] = jump_frames

        # Animación de atacar: 3 frames
        atack_frames = []
        for i in range(1, 4):
            pix = self.loadImage(f"images/penguin_atack_{i:02d}.png")
            if pix:
                atack_frames.append(pix)
        self.animations["atack"] = atack_frames

        # Animación de pre-slide: solo un fotograma (o podrías tener más)
        preslide_frames = []
        pix = self.loadImage("images/penguin_preslide_01.png")
        if pix:
            preslide_frames.append(pix)
        self.animations["pre_slide"] = preslide_frames

        # Animación de slide: los fotogramas continuos de deslizamiento (diagonales)
        slide_frames = []
        for i in range(1, 4):
            pix = self.loadImage(f"images/penguin_slide_{i:02d}.png")
            if pix:
                slide_frames.append(pix)
        self.animations["slide"] = slide_frames

        # Estado inicial: idle
        self.current_frames = self.animations["idle"]
        self.current_frame_index = 0
        if self.current_frames:
            self.label.setPixmap(self.current_frames[self.current_frame_index])
            print("[DEBUG] Animación inicial 'idle' cargada")

    def setupTimer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateAnimation)
        self.timer.start(200)  # Actualiza cada 120 ms
        print("[DEBUG] Timer iniciado: actualización cada 120ms")

    def updateAnimation(self):
        self.setFocus()  # Mantener el foco

        if not self.current_frames:
            return

        # Actualizar el índice de fotograma
        self.current_frame_index = (self.current_frame_index + 1) % len(self.current_frames)
        current_pix = self.current_frames[self.current_frame_index]

        # Reflejar la imagen si el pingüino mira a la izquierda
        if self.facing == "left":
            current_pix = current_pix.transformed(QTransform().scale(-1, 1))

        self.label.setPixmap(current_pix)

        # Debug de la animación y posición
        # print(f"[DEBUG] Estado: {self.current_state}, Frame: {self.current_frame_index}, Posición: ({self.x()}, {self.y()})")

        # Si estamos en pre_slide y llegamos al final, pasamos a slide
        if self.current_state == "pre_slide" and self.current_frame_index == len(self.current_frames) - 1:
            self.setState("slide")
        
        # Movimiento en estado "walk"
        if self.current_state == "walk":
            if self.facing == "right":
                self.move(self.x() + self.speed, self.y())
            elif self.facing == "left":
                self.move(self.x() - self.speed, self.y())

        # Simulación simple de salto: sube en el primer frame y baja en el último
        if self.current_state == "jump":
            if self.current_frame_index == 0:
                self.move(self.x(), self.y() - self.speed)
            elif self.current_frame_index == len(self.current_frames) - 1:
                self.move(self.x(), self.y() + self.speed)
            if self.current_frame_index == len(self.current_frames) - 1:
                self.setState("idle")

        # Movimiento en estado "slide"
        if self.current_state == "slide":
            # Obtener dimensiones de la pantalla
            desktop = QDesktopWidget()
            screen_rect = desktop.screenGeometry()
            screen_width = screen_rect.width()
            screen_height = screen_rect.height()

            # Calcular nueva posición
            new_x = self.x() + self.slide_dx
            new_y = self.y() + self.slide_dy

            # Colisión lateral: al chocar con las "murallas" horizontales,
            # se invierte dx y se actualiza la orientación
            if new_x < 0:
                new_x = 0
                self.slide_dx = -self.slide_dx
                self.facing = "right"
                print("[DEBUG] Rebote en pared izquierda, cambiando orientación a 'right'")
            elif new_x + self.width() > screen_width:
                new_x = screen_width - self.width()
                self.slide_dx = -self.slide_dx
                self.facing = "left"
                print("[DEBUG] Rebote en pared derecha, cambiando orientación a 'left'")

            # Colisión vertical: simplemente se invierte dy (no afecta la orientación)
            if new_y < 0:
                new_y = 0
                self.slide_dy = -self.slide_dy
                print("[DEBUG] Rebote en el techo")
            elif new_y + self.height() > screen_height:
                new_y = screen_height - self.height()
                self.slide_dy = -self.slide_dy
                print("[DEBUG] Rebote en el suelo")

            self.move(new_x, new_y)

        # Al finalizar la animación de "atack", volver a idle
        if self.current_state == "atack":
            if self.current_frame_index == len(self.current_frames) - 1:
                self.setState("idle")

    def setState(self, state):
        print(f"[DEBUG] Cambio de estado: {self.current_state} -> {state}")
        self.current_state = state
        
        if state == "pre_slide":
            # En pre_slide, solo se usa el fotograma de pre-slide (sin movimiento)
            self.current_frames = self.animations["pre_slide"]
            self.current_frame_index = 0
            # No generamos dx, dy aún; se hará al pasar a "slide"

        # Si es slide, generar dirección aleatoria
        elif state == "slide":
            # Elegir uno de los 4 ángulos diagonales (en grados)
            angulo_grados = random.choice([45, 135, 225, 315])
            angulo = math.radians(angulo_grados)
            slide_speed = 50  # Velocidad de deslizamiento

            # Calcula dx y dy de forma que sean iguales en valor absoluto
            self.slide_dx = int(slide_speed * math.cos(angulo))
            self.slide_dy = int(slide_speed * math.sin(angulo))
            
            # Establecer la orientación del pingüino según el signo de dx
            self.facing = "right" if self.slide_dx > 0 else "left"
            print(f"[DEBUG] Slide: ángulo {angulo_grados}°, dx={self.slide_dx}, dy={self.slide_dy}")
            
        else:
            # Reset por si acaso
            self.slide_dx = 0
            self.slide_dy = 0

        if state in self.animations and self.animations[state]:
            self.current_frames = self.animations[state]
        else:
            self.current_frames = self.animations["idle"]

        self.current_frame_index = 0
        current_pix = self.current_frames[self.current_frame_index]
        if self.facing == "left":
            current_pix = current_pix.transformed(QTransform().scale(-1, 1))
        self.label.setPixmap(current_pix)
        print(f"[DEBUG] Animación '{state}' iniciada")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            if event.isAutoRepeat():
                return
            self.moving_right = True
            self.facing = "right"
            if self.current_state not in ["walk", "jump", "slide", "pre_slide"]:
                self.setState("walk")
            print("[DEBUG] Tecla derecha presionada")
        elif event.key() == Qt.Key_Left:
            if event.isAutoRepeat():
                return
            self.moving_left = True
            self.facing = "left"
            if self.current_state not in ["walk", "jump", "slide", "pre_slide"]:
                self.setState("walk")
            print("[DEBUG] Tecla izquierda presionada")
        elif event.key() == Qt.Key_Up:
            if not event.isAutoRepeat() and self.current_state != "jump":
                self.setState("jump")
                print("[DEBUG] Tecla arriba presionada: salto")
        elif event.key() == Qt.Key_Down:
            if not event.isAutoRepeat() and self.current_state not in ["pre_slide", "slide"]:
                # Al presionar la tecla, iniciamos pre_slide
                self.setState("pre_slide")
                print("[DEBUG] Tecla abajo presionada: pre-slide")
        elif event.key() == Qt.Key_A:
            if not event.isAutoRepeat() and self.current_state != "atack":
                self.setState("atack")
                print("[DEBUG] Tecla A presionada: ataque")
        else:
            super().keyPressEvent(event)


    def keyReleaseEvent(self, event):
        # Ignorar eventos de auto repetición en la liberación
        if event.isAutoRepeat():
            return

        if event.key() == Qt.Key_Right:
            self.moving_right = False
            print("[DEBUG] Tecla derecha liberada")
        elif event.key() == Qt.Key_Left:
            self.moving_left = False
            print("[DEBUG] Tecla izquierda liberada")
        elif event.key() == Qt.Key_Down:
            if self.current_state in ["pre_slide", "slide"]:
                self.setState("idle")
                print("[DEBUG] Tecla abajo liberada: fin slide")
        # Solo si ninguna tecla lateral está presionada, se cambia a idle (para walk)
        if not (self.moving_right or self.moving_left) and self.current_state == "walk":
            self.setState("idle")
            print("[DEBUG] No se mantienen teclas laterales: volver a idle")
        else:
            super().keyReleaseEvent(event)

    # Métodos para permitir arrastrar la ventana con el mouse
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)        

    def closeEvent(self, event):
        print("[DEBUG] Cerrando el programa")
        QApplication.instance().quit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        saludar_action = menu.addAction("Saludar")
        cerrar_action = menu.addAction("Cerrar")
        action = menu.exec_(event.globalPos())
        if action == saludar_action:
            print("¡Hola! Saludo desde el menú contextual.")
        elif action == cerrar_action:
            self.close() # Cierra la ventana