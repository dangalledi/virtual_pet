"""Ventana de configuración: las opciones que se activan y se dejan puestas
(avisos, jornada, post-its, mascota y tamaño). El menú del pingüino queda para
las acciones rápidas. Los cambios se aplican al momento (salvo el tamaño, que
reinicia a Pingu y va con su botón)."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

import calendario
import mascotas

ZOOMS = [1, 1.25, 1.5, 1.75, 2, 2.5]   # opciones de tamaño (zoom de todo)


class VentanaConfig(QDialog):
    def __init__(self, pingu):
        super().__init__()
        self.pingu = pingu
        a = pingu.asistente
        w = a.woffu
        self.setWindowTitle("⚙️ Configuración de Pingu")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)

        # --- Avisos ---
        avisos = QVBoxLayout()
        if calendario.sogo_configurado():
            avisos.addWidget(self._casilla(f"🔔 Avisarme {a.reunion_aviso_min} min antes de las reuniones",
                                           "avisos_reuniones"))
        if pingu.rc_client:
            avisos.addWidget(self._casilla("💬 Avisarme de mensajes y menciones", "avisos_dm"))
        avisos.addWidget(self._casilla(f"🧘 Recordarme hacer pausas (cada {a.pausa_cada} min)", "pausas"))
        layout.addWidget(self._grupo("Avisos", avisos))

        # --- Rocket.Chat ---
        if pingu.rc_client:
            rc = QVBoxLayout()
            rc.addWidget(self._casilla("🤖 Cambiar mi estado solo (reunión → No molestar, "
                                       "fuera → Ausente)", "estado_auto"))
            layout.addWidget(self._grupo("Rocket.Chat", rc))

        # --- Jornada ---
        jornada = QVBoxLayout()
        intensiva = QCheckBox("☀️ Hoy hago jornada intensiva")
        intensiva.setChecked(w.es_intensiva())
        if w.es_verano():
            intensiva.setEnabled(False)
            intensiva.setToolTip("En verano (21-jun a 15-sep) es intensiva todos los días")
        intensiva.toggled.connect(pingu.poner_intensiva)
        jornada.addWidget(intensiva)
        layout.addWidget(self._grupo("Jornada", jornada))

        # --- Notas ---
        postits = QVBoxLayout()
        postits.addWidget(self._casilla("📌 Post-its siempre a la vista "
                                        "(si no, solo al tocar a Pingu)", "postits_siempre"))
        layout.addWidget(self._grupo("Notas", postits))

        # --- Apariencia ---
        forma = QFormLayout()
        forma.addRow("🐾 Mascota:", self._combo_mascota())
        forma.addRow("🔍 Tamaño:", self._fila_zoom())
        aviso = QLabel("El tamaño agranda todo (mascota, globos, menús, post-its). "
                       "Pingu se reinicia para aplicarlo.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: gray; font-size: 11px;")
        forma.addRow(aviso)
        layout.addWidget(self._grupo("Apariencia", forma))

        botones = QDialogButtonBox(QDialogButtonBox.Close)
        botones.rejected.connect(self.close)
        layout.addWidget(botones)

    # --- Piezas ---
    @staticmethod
    def _grupo(titulo: str, contenido) -> QGroupBox:
        caja = QGroupBox(titulo)
        caja.setLayout(contenido)
        return caja

    def _casilla(self, texto: str, clave: str) -> QCheckBox:
        casilla = QCheckBox(texto)
        casilla.setChecked(self.pingu.opcion(clave))
        casilla.toggled.connect(lambda si: self.pingu.poner_opcion(clave, si))
        return casilla

    def _combo_mascota(self) -> QComboBox:
        combo = QComboBox()
        opciones = [(mascotas.PINGU, "")]
        for clave, (_, _, colores, _) in mascotas.CATALOGO.items():
            opciones += [(clave, color) for color in colores]
        actual = self.pingu.mascota_actual()
        if actual[0] != mascotas.PINGU and not actual[1]:
            actual = (actual[0], mascotas.CATALOGO[actual[0]][2][0])
        for i, (clave, color) in enumerate(opciones):
            ok = mascotas.disponible(clave)
            combo.addItem(mascotas.nombre(clave, color) + ("" if ok else "  (instala vscode-pets)"))
            if not ok:
                combo.model().item(i).setEnabled(False)
            if (clave, color) == actual:
                combo.setCurrentIndex(i)
        combo.currentIndexChanged.connect(lambda i: self.pingu.cambiar_mascota(*opciones[i]))
        return combo

    def _fila_zoom(self) -> QHBoxLayout:
        combo = QComboBox()
        actual = self.pingu.settings.get("zoom", 1)
        for zoom in ZOOMS:
            combo.addItem(f"{round(zoom * 100)} %" + (" (normal)" if zoom == 1 else ""), zoom)
        combo.setCurrentIndex(ZOOMS.index(actual) if actual in ZOOMS else 0)
        aplicar = QPushButton("Aplicar")
        aplicar.setEnabled(False)
        combo.currentIndexChanged.connect(lambda _: aplicar.setEnabled(combo.currentData() != actual))
        aplicar.clicked.connect(lambda: self.pingu.cambiar_zoom(combo.currentData()))
        fila = QHBoxLayout()
        fila.addWidget(combo, 1)
        fila.addWidget(aplicar)
        return fila
