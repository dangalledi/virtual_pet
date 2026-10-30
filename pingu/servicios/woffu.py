"""Cliente de Woffu: login, fichajes de hoy, horas trabajadas y fichar."""
import datetime
import threading

import requests

from pingu.utils import env, log, hm


class WoffuClient:
    # Jornada intensiva: automática del 21-jun al 15-sep (igual que el whisperer)
    INTENSIVA_START = (6, 21)
    INTENSIVA_END   = (9, 15)

    def __init__(self):
        self.url      = env("WOFFU_URL").rstrip("/")   # https://tu_empresa.woffu.com
        self.email    = env("WOFFU_EMAIL")
        self.password = env("WOFFU_PASSWORD")
        self.horas_normal    = float(env("WOFFU_HOURS", "7"))
        self.horas_intensiva = float(env("WOFFU_HOURS_INTENSIVA", "6.5"))
        self.intensiva_date  = None    # jornada intensiva activada a mano (solo ese día)
        self.token   = None
        self.user_id = None
        self.clocked_in = None         # último estado conocido (None = desconocido)
        self.error = ""                # por qué falló el último login (para enseñarlo)
        self.session = requests.Session()
        self._lock   = threading.Lock()   # lo usan el hilo del asistente y los del menú

    # --- Autenticación ---
    def auth(self) -> bool:
        if not self.url or not self.email or not self.password:
            self.error = "falta WOFFU_URL / WOFFU_EMAIL / WOFFU_PASSWORD en el .env"
            log(f"Woffu: {self.error}")
            return False
        try:
            resp = requests.post(f"{self.url}/token",
                                 data={"grant_type": "password",
                                       "username": self.email,
                                       "password": self.password},
                                 timeout=10)
            if not resp.ok:
                log(f"Woffu auth HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code in (400, 401):
                    self.error = ("email o contraseña incorrectos\n"
                                  "(revisa WOFFU_EMAIL y WOFFU_PASSWORD en el .env)")
                elif resp.status_code == 404:
                    self.error = f"no encuentro Woffu en {self.url}\n(revisa WOFFU_URL)"
                else:
                    self.error = f"Woffu respondió con error {resp.status_code}"
                return False
            self.token = resp.json().get("access_token")
            if not self.token:
                self.error = "Woffu no devolvió sesión (¿WOFFU_URL correcta?)"
                log(f"Woffu: {self.error}")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

            me = self.session.get(f"{self.url}/api/users", timeout=10)
            me.raise_for_status()
            users = me.json()
            if isinstance(users, list):
                match = next((u for u in users
                              if str(u.get("Email", "")).lower() == self.email.lower()),
                             users[0] if users else None)
                self.user_id = (match.get("UserId") or match.get("userId")) if match else None
            else:
                self.user_id = users.get("UserId") or users.get("userId")
            if not self.user_id:
                self.error = "no pude saber tu usuario de Woffu"
                log(f"Woffu: {self.error}")
                return False
            self.error = ""
            log(f"Woffu autenticado (userId={self.user_id})")
            return True
        except requests.RequestException as e:
            self.error = "no puedo conectar con Woffu (¿red o WOFFU_URL?)"
            log(f"Woffu auth error: {e}")
            return False
        except Exception as e:
            self.error = "respuesta rara de Woffu (mira pingu.log)"
            log(f"Woffu auth error: {e}")
            return False

    def conectado(self) -> bool:
        return bool(self.token) or self.auth()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Petición con reintento de login si el token ha caducado (401)."""
        resp = self.session.request(method, f"{self.url}{path}", timeout=10, **kwargs)
        if resp.status_code == 401 and self.auth():
            resp = self.session.request(method, f"{self.url}{path}", timeout=10, **kwargs)
        return resp

    # --- Jornada ---
    def es_verano(self) -> bool:
        today = datetime.date.today()
        return self.INTENSIVA_START <= (today.month, today.day) <= self.INTENSIVA_END

    def es_intensiva(self) -> bool:
        return self.es_verano() or self.intensiva_date == datetime.date.today()

    def horas_jornada(self) -> float:
        return self.horas_intensiva if self.es_intensiva() else self.horas_normal

    def jornada_texto(self) -> str:
        return f"{self.horas_jornada():g}h".replace(".5h", "h 30min")

    # --- Fichajes ---
    def fichajes_hoy(self) -> list:
        """Horas de los fichajes de hoy, ordenadas. Lanza excepción si falla.
        Número impar = sigues dentro (el último fichaje fue una entrada)."""
        today = datetime.date.today()
        with self._lock:
            resp = self._request("GET", "/api/signs", params={"date": today.isoformat()})
        resp.raise_for_status()
        raw = resp.json()
        signs = raw if isinstance(raw, list) else (
            raw.get("signs") or raw.get("Signs") or raw.get("data") or raw.get("Data") or [])

        def parse_time(s):
            campo = (s.get("time") or s.get("Time") or s.get("hour") or s.get("Hour") or
                     s.get("date") or s.get("Date") or "")
            if not campo:
                return None
            campo = campo.replace("Z", "").split("T")[-1][:8]
            return datetime.datetime.combine(today, datetime.time.fromisoformat(campo))

        times = sorted(filter(None, (parse_time(s) for s in signs)))
        self.clocked_in = len(times) % 2 == 1
        return times

    @staticmethod
    def trabajado(times: list) -> float:
        """Segundos trabajados hoy a partir de los fichajes."""
        total = datetime.timedelta()
        for i in range(0, len(times) - 1, 2):
            total += times[i + 1] - times[i]
        if len(times) % 2 == 1:
            total += datetime.datetime.now() - times[-1]
        return total.total_seconds()

    def salida_estimada(self, times: list):
        """Hora aproximada de salida si sigues dentro; None si no aplica."""
        if not times or len(times) % 2 == 0:
            return None
        restante = self.horas_jornada() * 3600 - self.trabajado(times)
        return datetime.datetime.now() + datetime.timedelta(seconds=max(0, restante))

    def horas_detalle(self) -> str:
        """Resumen completo del día para la burbuja (como /horas del whisperer)."""
        if not self.conectado():
            return f"⚪ Woffu: {self.error or 'sin conexión'}"
        try:
            times = self.fichajes_hoy()
        except Exception as e:
            log(f"Woffu horas_detalle error: {e}")
            return "❌ No pude consultar los fichajes de Woffu."
        if not times:
            return "📋 Hoy no hay fichajes."

        worked   = self.trabajado(times)
        restante = self.horas_jornada() * 3600 - worked
        lineas = [
            "⏱ Horas de hoy" + (" (intensiva)" if self.es_intensiva() else ""),
            f"Estado: {'🟢 Dentro' if self.clocked_in else '🔴 Fuera'}",
            f"Entrada: {times[0].strftime('%H:%M')}",
            f"Trabajado: {hm(worked)}",
        ]
        if restante > 0:
            lineas.append(f"Restante: {hm(restante)}")
            salida = self.salida_estimada(times)
            if salida:
                lineas.append(f"Salida aprox: {salida.strftime('%H:%M')}")
        else:
            lineas.append(f"✅ Jornada completada (+{hm(restante)} extra)")
        return "\n".join(lineas)

    def fichar(self) -> tuple:
        """Registra un fichaje en Woffu. Devuelve (mensaje, ok, fue_salida)."""
        try:
            if not self.conectado():
                return f"❌ Woffu: {self.error or 'sin conexión'}", False, False
            with self._lock:
                resp = self._request("POST", "/api/signs", json={"UserId": self.user_id})
            resp.raise_for_status()
            self.fichajes_hoy()   # actualiza clocked_in
            log(f"Woffu: fichaje registrado ({'entrada' if self.clocked_in else 'salida'})")
            if self.clocked_in:
                return "✅ Entrada fichada.", True, False
            return "✅ Salida fichada.", True, True
        except Exception as e:
            log(f"Woffu fichar error: {e}")
            return "❌ No se pudo registrar el fichaje en Woffu.", False, False
