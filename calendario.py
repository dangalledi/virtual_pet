"""Calendarios: reuniones de hoy (SOGo por CalDAV) y ausencias del equipo (iCal de Woffu).

Adaptado del whisperer_bot. Las funciones devuelven None si la consulta falla,
para que quien llame decida si usar la última copia buena.
"""
import os
import time
import datetime
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from icalendar import Calendar

SOGO_CACHE_TTL = 600    # segundos de validez de la copia del calendario de hoy
ICAL_CACHE_TTL = 600


def _env(name: str) -> str:
    return os.getenv(name, "").split(" #")[0].strip()


def _to_local_naive(value, end_of_day: bool = False) -> datetime.datetime:
    """Fecha/hora del iCal → datetime local sin zona, para comparar con now()."""
    if isinstance(value, datetime.datetime):
        if value.tzinfo:
            value = value.astimezone()   # a la hora local del equipo
        return value.replace(tzinfo=None)
    # Evento de día completo
    return datetime.datetime.combine(value, datetime.time.max if end_of_day else datetime.time.min)


# ---------------------------------------------------------------------------
# SOGo — reuniones
# ---------------------------------------------------------------------------
def sogo_configurado() -> bool:
    return bool(_env("SOGO_CALENDAR_URL") and _env("SOGO_USER") and _env("SOGO_PASSWORD"))


def _fetch_sogo_ical(calendar_url: str, day: datetime.date) -> bytes:
    """Descarga los eventos del día por CalDAV REPORT y los junta en un VCALENDAR.
    Se pide al servidor que expanda los eventos repetidos (reuniones semanales, etc.)."""
    user, password = _env("SOGO_USER"), _env("SOGO_PASSWORD")
    url   = calendar_url.rstrip("/") + "/"
    start = day.strftime("%Y%m%dT000000Z")
    end   = (day + datetime.timedelta(days=1)).strftime("%Y%m%dT000000Z")
    body  = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
        f'<D:prop><C:calendar-data><C:expand start="{start}" end="{end}"/></C:calendar-data></D:prop>'
        '<C:filter><C:comp-filter name="VCALENDAR">'
        f'<C:comp-filter name="VEVENT"><C:time-range start="{start}" end="{end}"/>'
        '</C:comp-filter></C:comp-filter></C:filter>'
        '</C:calendar-query>'
    )
    headers = {"Content-Type": "application/xml; charset=utf-8", "Depth": "1"}
    resp = None
    for auth in (HTTPBasicAuth(user, password), HTTPDigestAuth(user, password)):
        resp = requests.request("REPORT", url, auth=auth, headers=headers,
                                data=body.encode(), timeout=15)
        if resp.status_code != 401:
            break
    resp.raise_for_status()

    ns = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}
    root = ET.fromstring(resp.content)
    vevents = []
    for response in root.findall("D:response", ns):
        ps = response.find("D:propstat", ns)
        if ps is None:
            continue
        st = ps.find("D:status", ns)
        if st is not None and "200" not in (st.text or ""):
            continue
        cd = ps.find(".//C:calendar-data", ns)
        if cd is None or not cd.text:
            continue
        in_ev, ev_lines = False, []
        for line in cd.text.splitlines():
            if line.startswith("BEGIN:VEVENT"):
                in_ev, ev_lines = True, [line]
            elif in_ev:
                ev_lines.append(line)
                if line.startswith("END:VEVENT"):
                    vevents.append("\r\n".join(ev_lines))
                    in_ev = False

    ical = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//VirtualPet//EN\r\n"
    if vevents:
        ical += "\r\n".join(vevents) + "\r\n"
    ical += "END:VCALENDAR\r\n"
    return ical.encode()


_sogo_cache = None   # (timestamp, fecha, eventos)


def reuniones_de_hoy(permitir_red: bool = True, forzar: bool = False):
    """Eventos de hoy ordenados: [{summary, start, end, location}].
    Usa una copia de SOGO_CACHE_TTL segundos. Con permitir_red=False (VPN caída)
    solo devuelve la copia de hoy si la hay. None si no hay datos."""
    global _sogo_cache
    today  = datetime.date.today()
    cached = _sogo_cache[2] if _sogo_cache and _sogo_cache[1] == today else None
    if cached is not None and not forzar and time.time() - _sogo_cache[0] < SOGO_CACHE_TTL:
        return cached
    if not permitir_red or not sogo_configurado():
        return cached

    cal = Calendar.from_ical(_fetch_sogo_ical(_env("SOGO_CALENDAR_URL"), today))
    events = []
    for comp in cal.walk("VEVENT"):
        dtstart = comp.get("DTSTART")
        if not dtstart:
            continue
        dtend = comp.get("DTEND")
        s = _to_local_naive(dtstart.dt)
        e = _to_local_naive(dtend.dt, end_of_day=True) if dtend else s
        if s.date() != today:
            continue
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        events.append({
            "summary":  str(comp.get("SUMMARY", "Sin título")).strip(),
            "start":    s,
            "end":      e,
            "location": str(comp.get("LOCATION", "")).strip(),
            "all_day":  not isinstance(dtstart.dt, datetime.datetime),
        })
    events.sort(key=lambda x: x["start"])
    _sogo_cache = (time.time(), today, events)
    return events


def hora_copia_reuniones():
    """Hora (HH:MM) de la última copia buena del calendario de hoy, o None."""
    if _sogo_cache and _sogo_cache[1] == datetime.date.today():
        return datetime.datetime.fromtimestamp(_sogo_cache[0]).strftime("%H:%M")
    return None


# ---------------------------------------------------------------------------
# Woffu — ausencias del equipo (iCal)
# ---------------------------------------------------------------------------
_ical_cache = None   # (timestamp, eventos)

# Tipos de evento del iCal de Woffu que cuentan como ausencia
AUSENCIA            = "Ausencia"
AUSENCIA_PENDIENTE  = "Procesando Ausencia"   # pedida, aún sin aprobar


def ausencias_configurado() -> bool:
    return bool(_env("WOFFU_ICAL_URL"))


def _eventos_ausencia() -> list:
    """[{nombre, dia, pendiente}] del iCal de Woffu (un evento por persona y día).
    Cacheado ICAL_CACHE_TTL segundos. Lanza excepción si falla la descarga."""
    global _ical_cache
    if _ical_cache and time.time() - _ical_cache[0] < ICAL_CACHE_TTL:
        return _ical_cache[1]
    resp = requests.get(_env("WOFFU_ICAL_URL"), timeout=30)
    resp.raise_for_status()
    events = []
    for comp in Calendar.from_ical(resp.content).walk("VEVENT"):
        dtstart = comp.get("DTSTART")
        nombre  = str(comp.get("SUMMARY", "")).strip()
        if not dtstart or not nombre:
            continue
        desc = str(comp.get("DESCRIPTION", "")).strip()
        tipo = desc.splitlines()[-1].strip() if desc else ""
        if tipo not in (AUSENCIA, AUSENCIA_PENDIENTE):
            continue
        dia = dtstart.dt.date() if isinstance(dtstart.dt, datetime.datetime) else dtstart.dt
        events.append({"nombre": nombre.split()[0], "dia": dia,
                       "pendiente": tipo == AUSENCIA_PENDIENTE})
    _ical_cache = (time.time(), events)
    return events


def ausentes_hoy():
    """Nombres (solo el primero) de quien falta hoy. None si no está configurado."""
    if not ausencias_configurado():
        return None
    today = datetime.date.today()
    return sorted({e["nombre"] for e in _eventos_ausencia() if e["dia"] == today})


def lunes_de(semana: int = 0) -> datetime.date:
    """Lunes de esta semana (0) o de la siguiente (1). En fin de semana,
    "esta semana" es la que empieza el lunes (la que acaba ya no interesa)."""
    today = datetime.date.today()
    if today.weekday() >= 5:
        semana += 1
    return today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=semana)


def ausencias_semana(semana: int = 0) -> dict:
    """{nombre: [(día, pendiente), ...]} de lunes a viernes de esa semana."""
    lunes   = lunes_de(semana)
    viernes = lunes + datetime.timedelta(days=4)
    result = {}
    for e in _eventos_ausencia():
        if lunes <= e["dia"] <= viernes:
            result.setdefault(e["nombre"], set()).add((e["dia"], e["pendiente"]))
    return {n: sorted(d) for n, d in sorted(result.items())}
