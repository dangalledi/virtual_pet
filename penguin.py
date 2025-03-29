import sys
from PyQt5.QtWidgets import QWidget, QLabel, QMessageBox, QMenu
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
        self.speed = 50  # píxeles de movimiento por actualización
        self.moving_right = False
        self.moving_left = False
        self.setupTimer()

    def initUI(self):
        # Fondo transparente
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.move(100, 100)  # Posición inicial

    def loadImage(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            print(f"Error al cargar {path}")
            return None
        # Escalar la imagen al 50% de su tamaño original
        scaled_pix = pix.scaled(pix.width() // 2, pix.height() // 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

        # Animación de deslizarse: 1 frame pre-deslizamiento + 3 frames deslizando
        slide_frames = []
        pre_slide = self.loadImage("images/penguin_preslide_01.png")
        if pre_slide:
            slide_frames.append(pre_slide)
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
            self.resize(self.current_frames[self.current_frame_index].size())

    def setupTimer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateAnimation)
        self.timer.start(200)  # Actualiza cada 100 ms

    def updateAnimation(self):
        # Mantener el foco para que no se pierda durante las animaciones
        self.setFocus()

        if not self.current_frames:
            return

        self.current_frame_index = (self.current_frame_index + 1) % len(self.current_frames)
        current_pix = self.current_frames[self.current_frame_index]

        # Reflejar la imagen si el pingüino mira a la izquierda
        if self.facing == "left":
            current_pix = current_pix.transformed(QTransform().scale(-1, 1))

        self.label.setPixmap(current_pix)

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

        # Al finalizar las animaciones de "atack" y "slide" se vuelve a idle
        if self.current_state in ["atack", "slide"]:
            if self.current_frame_index == len(self.current_frames) - 1:
                self.setState("idle")

    def setState(self, state):
        self.current_state = state
        
        if state in self.animations:
            self.current_frames = self.animations[state]
        else:
            self.current_frames = self.animations["idle"]
            
        self.current_frame_index = 0
        current_pix = self.current_frames[self.current_frame_index]
        
        if self.facing == "left":
            current_pix = current_pix.transformed(QTransform().scale(-1, 1))
            
        self.label.setPixmap(current_pix)
        self.resize(self.current_frames[self.current_frame_index].size())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.moving_right = True
            self.facing = "right"
            self.setState("walk")
            
        elif event.key() == Qt.Key_Left:
            self.moving_left = True
            self.facing = "left"
            self.setState("walk")
            
        elif event.key() == Qt.Key_Up:
            self.setState("jump")
        elif event.key() == Qt.Key_Down:
            self.setState("slide")
        elif event.key() == Qt.Key_A:
            self.setState("atack")
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.moving_right = False
        elif event.key() == Qt.Key_Left:
            self.moving_left = False

        # Si ya no se mantiene pulsada ninguna tecla de movimiento, volvemos a idle
        if not (self.moving_right or self.moving_left) and self.current_state == "walk":
            self.setState("idle")
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

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        saludar_action = menu.addAction("Saludar")
        cerrar_action = menu.addAction("Cerrar")
        action = menu.exec_(event.globalPos())
        if action == saludar_action:
            print("¡Hola! Saludo desde el menú contextual.")
        elif action == cerrar_action:
            self.close()