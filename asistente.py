"""Hilo del asistente: una vuelta por minuto revisando VPN, reuniones, Woffu,
resumen del día y pausas. Avisa al pingüino con señales; no toca la UI."""
import math
import datetime
import threading

from PyQt5.QtCore import QThread, pyqtSignal

import calendario
import vpn
from utils import env, env_int, log, hm, idle_seconds
from woffu import WoffuClient


class AsistenteWorker(QThread):
    # (texto, tipo). Tipos: reunion, fichaje, comida, bano, jornada, pausa, resumen
    aviso              = pyqtSignal(str, str)
    horas_actualizadas = pyqtSignal(str)        # línea de estado para el menú
    vpn_changed        = pyqtSignal(bool, str)  # (conectada, detalle)
    reunion_en_curso   = pyqtSignal(bool)
    fichaje_cambiado   = pyqtSignal(bool)       # True = has entrado, False = has salido

    def __init__(self, parent=None):
        super().__init__(parent)
        self.woffu = WoffuClient()
        self.vpn   = VpnState()
        self._running = True
        self._despertar = threading.Event()   # espera entre vueltas, interrumpible
        self._day     = None

        # Interruptores (los cambia el pingüino desde el menú)
        self.avisos_reuniones = True
        self.pausas_activas   = True
        self.resumen_date     = None   # último día en que se mostró el resumen

        # Avisos de reuniones
        self.reunion_aviso_min   = env_int("REUNION_AVISO_MIN", 10)
        self._reuniones_avisadas = set()
        self._en_reunion         = False
        self._cal_force          = False
        self._cal_error          = None

        # Recordatorios de fichaje (una vez al día, solo laborables)
        self.rec_entrada     = env("RECORDATORIO_ENTRADA", "10:00")
        self.rec_salida      = env("RECORDATORIO_SALIDA", "18:30")
        self.rec_salida_fin  = env("RECORDATORIO_SALIDA_FIN", "21:00")
        self._rec_entrada_hecho = False
        self._rec_salida_hecho  = False
        self._jornada_avisada   = False
        self._clocked_prev      = None
        self._lunch_timer       = None

        # Aviso antes de comer ("ve al baño")
        lh, lm = map(int, env("LUNCH_TIME", "13:00").split(":"))
        self.lunch_time     = datetime.time(lh, lm)
        self.bano_min       = env_int("LUNCH_REMINDER_MINUTES", 10)
        total               = lh * 60 + lm - self.bano_min
        self.bano_time      = datetime.time(total // 60, total % 60)
        self._bano_hecho    = False

        # Resumen del día
        self.resumen_desde = env("RESUMEN_DESDE", "07:00")
        self.resumen_hasta = env("RESUMEN_HASTA", "15:00")

        # Pausas: tras PAUSA_CADA_MIN de uso continuo; cuenta como pausa
        # estar PAUSA_IDLE_MIN sin tocar teclado ni ratón
        self.pausa_cada   = env_int("PAUSA_CADA_MIN", 90)
        self.pausa_idle   = env_int("PAUSA_IDLE_MIN", 5)
        self._activo_desde = None

    def stop(self):
        self._running = False
        self._despertar.set()   # sale de la espera al momento
        self.quit()

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def run(self):
        if not self.woffu.auth():
            log("Woffu: no se pudo autenticar; reintento cada 5 min (lo demás sigue)")
        last_auth_try = datetime.datetime.now()

        while self._running:
            now = datetime.datetime.now()
            if self._day != now.date():
                self._nuevo_dia(now.date())

            for paso in (self._check_vpn, self._check_reuniones, self._check_bano,
                         self._check_pausa, self._check_resumen):
                try:
                    paso()
                except Exception as e:
                    log(f"Asistente: error en {paso.__name__}: {e}")

            if not self.woffu.token and (now - last_auth_try).total_seconds() >= 300:
                last_auth_try = now
                self.woffu.auth()
            if self.woffu.token:
                try:
                    self._check_woffu()
                except Exception as e:
                    log(f"Woffu: error revisando fichajes: {e}")

            # Una vuelta por minuto (suficiente para todos los avisos); sin
            # despertar cada segundo para ahorrar batería
            self._despertar.wait(60)

    def _nuevo_dia(self, day):
        self._day = day
        self._reuniones_avisadas = set()
        self._rec_entrada_hecho = self._rec_salida_hecho = False
        self._jornada_avisada = self._bano_hecho = False

    # ------------------------------------------------------------------
    # VPN
    # ------------------------------------------------------------------
    def _check_vpn(self):
        primera = self.vpn.monitor.conectada is None
        cambio = self.vpn.monitor.comprobar()
        if cambio:
            conectada, detalle = cambio
            if conectada and self.vpn.estuvo_caida:
                self._cal_force = True   # al volver la VPN, releer el calendario
            self.vpn.estuvo_caida = not conectada
            if not (primera and conectada):   # al arrancar con VPN, no hace falta avisar
                self.vpn_changed.emit(conectada, detalle)

    # ------------------------------------------------------------------
    # Reuniones (SOGo)
    # ------------------------------------------------------------------
    def _reuniones(self, forzar: bool = False):
        """Eventos de hoy. Sin VPN usa la última copia. None si no hay datos."""
        if not calendario.sogo_configurado():
            return None
        try:
            events = calendario.reuniones_de_hoy(
                permitir_red=self.vpn.monitor.conectada is not False,
                forzar=forzar or self._cal_force)
            self._cal_force = False
            if self._cal_error:
                log("Calendario SOGo: recuperado")
                self._cal_error = None
            return events
        except Exception as e:
            if str(e) != self._cal_error:
                log(f"Calendario SOGo error: {e}")
                self._cal_error = str(e)
            return calendario.reuniones_de_hoy(permitir_red=False)

    def _check_reuniones(self):
        events = self._reuniones()
        if events is None:
            return
        now = datetime.datetime.now()
        con_hora = [ev for ev in events if not ev["all_day"]]

        # ¿Hay alguna reunión ahora mismo? (para el estado de Rocket.Chat)
        en_curso = any(ev["start"] <= now < ev["end"] for ev in con_hora)
        if en_curso != self._en_reunion:
            self._en_reunion = en_curso
            self.reunion_en_curso.emit(en_curso)

        if not self.avisos_reuniones:
            return
        for ev in con_hora:
            falta = (ev["start"] - now).total_seconds()
            if not 0 < falta <= self.reunion_aviso_min * 60:
                continue
            key = f"{ev['start'].isoformat()}|{ev['summary']}"
            if key in self._reuniones_avisadas:
                continue
            self._reuniones_avisadas.add(key)
            texto = (f"⏰ {ev['summary']}\nEmpieza en {math.ceil(falta / 60)} min "
                     f"({ev['start'].strftime('%H:%M')})")
            if ev["location"]:
                texto += f"\n📍 {ev['location']}"
            self.aviso.emit(texto, "reunion")
            log(f"Aviso de reunión: {ev['summary']}")

    def reuniones_texto(self) -> str:
        if not calendario.sogo_configurado():
            return "❌ Falta SOGO_CALENDAR_URL / SOGO_USER / SOGO_PASSWORD en el .env"
        events = self._reuniones(forzar=True)
        sin_vpn = self.vpn.monitor.conectada is False
        if events is None:
            return ("🔴 Sin VPN no puedo ver el calendario." if sin_vpn
                    else "❌ No pude consultar el calendario.")
        lineas = [f"📅 Reuniones hoy ({datetime.date.today().strftime('%d/%m')})"]
        now = datetime.datetime.now()
        for ev in events:
            if ev["all_day"]:
                lineas.append(f"• Todo el día: {ev['summary']}")
                continue
            marca = "✔ " if ev["end"] < now else "• "
            loc = f" ({ev['location']})" if ev["location"] else ""
            lineas.append(f"{marca}{ev['start'].strftime('%H:%M')}–{ev['end'].strftime('%H:%M')} "
                          f"{ev['summary']}{loc}")
        if not events:
            lineas.append("No hay nada en el calendario.")
        if sin_vpn:
            lineas.append(f"⚠️ Sin VPN: copia de las {calendario.hora_copia_reuniones()}")
        return "\n".join(lineas)

    # ------------------------------------------------------------------
    # Ausencias del equipo
    # ------------------------------------------------------------------
    @staticmethod
    def ausentes_texto() -> str:
        if not calendario.ausencias_configurado():
            return "❌ Falta WOFFU_ICAL_URL en el .env"
        try:
            nombres = calendario.ausentes_hoy()
        except Exception as e:
            log(f"Ausencias error: {e}")
            return "❌ No pude consultar las ausencias."
        if not nombres:
            return "✅ Hoy no falta nadie del equipo."
        return f"🏖️ Faltan hoy ({len(nombres)}):\n" + "\n".join(f"• {n}" for n in nombres)

    @staticmethod
    def ausencias_semana_texto(semana: int = 0) -> str:
        """Quién falta y qué días, esta semana (0) o la próxima (1)."""
        if not calendario.ausencias_configurado():
            return "❌ Falta WOFFU_ICAL_URL en el .env"
        try:
            ausencias = calendario.ausencias_semana(semana)
        except Exception as e:
            log(f"Ausencias error: {e}")
            return "❌ No pude consultar las ausencias."
        lunes   = calendario.lunes_de(semana)
        viernes = lunes + datetime.timedelta(days=4)
        titulo  = "esta semana" if semana == 0 else "la próxima semana"
        cabecera = f"🏖️ Ausencias {titulo} ({lunes.strftime('%d/%m')}–{viernes.strftime('%d/%m')})"
        if not ausencias:
            return f"{cabecera}\n✅ No falta nadie."
        lineas = [cabecera]
        pendientes = False
        for nombre, dias in ausencias.items():
            if len(dias) == 5:
                texto = "toda la semana"
            else:
                texto = ", ".join(DIAS_CORTOS[d.weekday()] for d, _ in dias)
            if any(p for _, p in dias):
                texto += " *"
                pendientes = True
            lineas.append(f"• {nombre}: {texto}")
        if pendientes:
            lineas.append("* pendiente de aprobar")
        return "\n".join(lineas)

    # ------------------------------------------------------------------
    # Woffu: jornada y recordatorios de fichaje
    # ------------------------------------------------------------------
    def _check_woffu(self):
        times = self.woffu.fichajes_hoy()
        clocked_in = self.woffu.clocked_in
        if self._clocked_prev is not None and clocked_in != self._clocked_prev:
            self.fichaje_cambiado.emit(clocked_in)
        self._clocked_prev = clocked_in

        self._check_recordatorios_fichaje(times)
        if not times:
            self.horas_actualizadas.emit("🔴 Sin fichar hoy")
            return

        worked   = self.woffu.trabajado(times)
        restante = self.woffu.horas_jornada() * 3600 - worked
        if restante <= 0:
            if not self._jornada_avisada:
                self._jornada_avisada = True
                msg = f"🎉 ¡{self.woffu.jornada_texto()} completadas!"
                if -restante >= 60:
                    msg += f" (+{hm(restante)} extra)"
                self.aviso.emit(msg, "jornada")
            self.horas_actualizadas.emit(f"✅ Jornada completada ({hm(worked)})")
            return

        texto = f"{'🟢 Fichado' if clocked_in else '🔴 Fuera'} | {hm(worked)} | Resta: {hm(restante)}"
        salida = self.woffu.salida_estimada(times)
        if salida:
            texto += f" | Salida ~{salida.strftime('%H:%M')}"
        self.horas_actualizadas.emit(texto)

    def _check_recordatorios_fichaje(self, times: list):
        """A media mañana sin fichar entrada, o a última hora todavía dentro → aviso."""
        now  = datetime.datetime.now()
        hora = now.strftime("%H:%M")
        if now.weekday() >= 5:
            return
        if not self._rec_entrada_hecho and self.rec_entrada <= hora < "12:00":
            self._rec_entrada_hecho = True
            if not times:
                self.aviso.emit(f"⏰ Son las {hora} y no has fichado la entrada.\n"
                                "Click derecho → Fichar", "fichaje")
        if (not self._rec_salida_hecho and self.rec_salida <= hora < self.rec_salida_fin
                and len(times) % 2 == 1):
            self._rec_salida_hecho = True
            self.aviso.emit(f"🌙 Son las {hora} y sigues fichado desde las "
                            f"{times[-1].strftime('%H:%M')}.\n¿Se te olvidó la salida?", "fichaje")

    def fichar(self) -> tuple:
        """Ficha (lo llama el menú desde otro hilo) y avisa si cambia entrada/salida."""
        msg, ok, fue_salida = self.woffu.fichar()
        if ok:
            if not fue_salida:
                self.cancel_lunch_timer()   # has vuelto: ya no hace falta el aviso
            self._clocked_prev = self.woffu.clocked_in
            self.fichaje_cambiado.emit(self.woffu.clocked_in)
        return msg, ok, fue_salida

    # ------------------------------------------------------------------
    # Comida
    # ------------------------------------------------------------------
    def _check_bano(self):
        now = datetime.datetime.now().time().replace(second=0, microsecond=0)
        if not self._bano_hecho and self.bano_time <= now < self.lunch_time:
            self._bano_hecho = True
            self.aviso.emit(f"🚽 En {self.bano_min} min son las "
                            f"{self.lunch_time.strftime('%H:%M')} — ¡ve al baño!", "bano")

    def start_lunch_timer(self, minutos: int = 30):
        self.cancel_lunch_timer()
        self._lunch_timer = threading.Timer(minutos * 60, lambda: self.aviso.emit(
            f"🍽️ Han pasado {minutos} min — ¡puedes volver cuando quieras!", "comida"))
        self._lunch_timer.daemon = True
        self._lunch_timer.start()
        log(f"Timer de comida iniciado ({minutos} min)")

    def cancel_lunch_timer(self):
        if self._lunch_timer and self._lunch_timer.is_alive():
            self._lunch_timer.cancel()

    # ------------------------------------------------------------------
    # Pausas
    # ------------------------------------------------------------------
    def _check_pausa(self):
        if not self.pausas_activas or self.woffu.clocked_in is False:
            self._activo_desde = None   # fuera del trabajo no cuenta
            return
        idle = idle_seconds()
        if idle is None:
            return
        now = datetime.datetime.now()
        if idle >= self.pausa_idle * 60:
            self._activo_desde = None   # ya estás descansando
            return
        if self._activo_desde is None:
            self._activo_desde = now - datetime.timedelta(seconds=idle)
            return
        seguido = (now - self._activo_desde).total_seconds()
        if seguido >= self.pausa_cada * 60 and not self._en_reunion:
            self._activo_desde = now
            self.aviso.emit(f"🧘 Llevas {hm(seguido)} sin parar.\n"
                            "Levántate, estira las piernas y descansa la vista unos minutos.",
                            "pausa")
            log("Recordatorio de pausa")

    # ------------------------------------------------------------------
    # Resumen del día
    # ------------------------------------------------------------------
    def _check_resumen(self):
        now = datetime.datetime.now()
        hora = now.strftime("%H:%M")
        if (self.resumen_date == now.date().isoformat() or now.weekday() >= 5
                or not self.resumen_desde <= hora < self.resumen_hasta):
            return
        # Solo cuando estás delante del ordenador (si se puede saber)
        idle = idle_seconds()
        if idle is not None and idle > 120:
            return
        self.resumen_date = now.date().isoformat()
        self.aviso.emit(self.resumen_texto(), "resumen")
        log("Resumen del día mostrado")

    def resumen_texto(self) -> str:
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        today = datetime.date.today()
        lineas = [f"☀️ Buenos días — {dias[today.weekday()]} {today.strftime('%d/%m')}"]

        # Woffu
        if self.woffu.conectado():
            try:
                times = self.woffu.fichajes_hoy()
                if not times:
                    lineas.append("🕒 Aún no has fichado la entrada")
                else:
                    salida = self.woffu.salida_estimada(times)
                    linea = f"🕒 Entrada {times[0].strftime('%H:%M')}"
                    if salida:
                        linea += f" · salida aprox {salida.strftime('%H:%M')}"
                    lineas.append(linea + (" (intensiva)" if self.woffu.es_intensiva() else ""))
            except Exception as e:
                log(f"Resumen: Woffu error: {e}")

        # Reuniones que quedan hoy
        events = self._reuniones()
        if events is not None:
            now = datetime.datetime.now()
            pendientes = [ev for ev in events if not ev["all_day"] and ev["end"] > now]
            if pendientes:
                lineas.append("📅 Reuniones:")
                lineas += [f"   {ev['start'].strftime('%H:%M')} {ev['summary']}" for ev in pendientes[:5]]
                if len(pendientes) > 5:
                    lineas.append(f"   … y {len(pendientes) - 5} más")
            else:
                lineas.append("📅 Sin reuniones hoy")

        # Ausencias: hoy; los lunes, la semana; los viernes, la que viene
        if calendario.ausencias_configurado():
            try:
                nombres = calendario.ausentes_hoy()
                lineas.append(f"🏖️ Hoy faltan: {', '.join(nombres)}" if nombres
                              else "🏖️ Hoy no falta nadie")
            except Exception as e:
                log(f"Resumen: ausencias error: {e}")
            if today.weekday() == 0:
                lineas += ["", self.ausencias_semana_texto(0)]
            elif today.weekday() == 4:
                lineas += ["", self.ausencias_semana_texto(1)]

        return "\n".join(lineas)


DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


class VpnState:
    """Monitor de VPN + si estuvo caída (para releer el calendario al volver)."""
    def __init__(self):
        self.monitor = vpn.VpnMonitor()
        self.estuvo_caida = False
