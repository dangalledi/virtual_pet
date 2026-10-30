"""Calendarios: reuniones de hoy (SOGo por CalDAV) y ausencias del equipo (iCal de Woffu).
SOGO_CALENDAR_URL admite varios calendarios separados por comas: se juntan sus reuniones.

Adaptado del whisperer_bot. Las funciones devuelven None si la consulta falla,
para que quien llame decida si usar la última copia buena.
"""
import time
import datetime
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from icalendar import Calendar

from pingu.utils import con_usuario, env, log, usuario

SOGO_CACHE_TTL = 600    # segundos de validez de la copia del calendario de hoy
ICAL_CACHE_TTL = 600


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
def sogo_urls() -> list:
    """Calendarios de SOGO_CALENDAR_URL (uno o varios separados por comas)."""
    return [con_usuario(u.strip()) for u in env("SOGO_CALENDAR_URL").split(",") if u.strip()]


def sogo_configurado() -> bool:
    return bool(sogo_urls() and env("SOGO_PASSWORD"))


def sogo_user() -> str:
    """Usuario de SOGo: SOGO_USER si lo pones; si no, tu usuario LDAP."""
    return env("SOGO_USER") or usuario()


def _sogo_request(method: str, url: str, body: str, depth: str) -> requests.Response:
    """Petición CalDAV con tu usuario de SOGo (Basic y, si no vale, Digest)."""
    user, password = sogo_user(), env("SOGO_PASSWORD")
    headers = {"Content-Type": "application/xml; charset=utf-8", "Depth": depth}
    resp = None
    for auth in (HTTPBasicAuth(user, password), HTTPDigestAuth(user, password)):
        resp = requests.request(method, url, auth=auth, headers=headers,
                                data=body.encode(), timeout=15)
        if resp.status_code != 401:
            break
    resp.raise_for_status()
    return resp


_nombres = {}   # url -> nombre del calendario


def nombre_calendario(url: str) -> str:
    """Nombre del calendario en SOGo (p. ej. "Support"). Si no se puede saber, el
    dueño que sale en la URL (…/dav/<dueño>/Calendar/…)."""
    if url in _nombres:
        return _nombres[url]
    partes = url.rstrip("/").split("/")
    nombre = partes[partes.index("dav") + 1] if "dav" in partes[:-1] else partes[-1]
    try:
        body = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<D:propfind xmlns:D="DAV:"><D:prop><D:displayname/></D:prop></D:propfind>')
        resp = _sogo_request("PROPFIND", url.rstrip("/") + "/", body, "0")
        dn = ET.fromstring(resp.content).find(".//{DAV:}displayname")
        if dn is not None and dn.text and dn.text.strip():
            # "Support (DAVID VICENTE <…>)" → "Support"
            nombre = dn.text.strip().split(" (")[0]
    except Exception as e:
        log(f"Calendario {url}: no pude leer su nombre ({e})")
    _nombres[url] = nombre
    return nombre


def _fetch_sogo_ical(calendar_url: str, day: datetime.date) -> bytes:
    """Descarga los eventos del día por CalDAV REPORT y los junta en un VCALENDAR.
    Se pide al servidor que expanda los eventos repetidos (reuniones semanales, etc.)."""
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
    resp = _sogo_request("REPORT", url, body, "1")

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
    """Eventos de hoy de todos los calendarios, ordenados:
    [{summary, start, end, location, all_day, calendario}].
    Usa una copia de SOGO_CACHE_TTL segundos. Con permitir_red=False (VPN caída)
    solo devuelve la copia de hoy si la hay. None si no hay datos.
    Si falla algún calendario se usan los demás; si fallan todos, lanza el error."""
    global _sogo_cache
    today  = datetime.date.today()
    cached = _sogo_cache[2] if _sogo_cache and _sogo_cache[1] == today else None
    if cached is not None and not forzar and time.time() - _sogo_cache[0] < SOGO_CACHE_TTL:
        return cached
    if not permitir_red or not sogo_configurado():
        return cached

    events, vistos, errores = [], set(), []
    urls = sogo_urls()
    for url in urls:
        try:
            cal = Calendar.from_ical(_fetch_sogo_ical(url, today))
        except Exception as e:
            errores.append(e)
            log(f"Calendario {url}: {e}")
            continue
        nombre = nombre_calendario(url) if len(urls) > 1 else ""
        for ev in _eventos_de_hoy(cal, today):
            clave = (ev.pop("uid") or ev["summary"], ev["start"])
            if clave in vistos:   # la misma reunión en dos calendarios
                continue
            vistos.add(clave)
            ev["calendario"] = nombre
            events.append(ev)
    if errores and len(errores) == len(urls):
        raise errores[0]
    events.sort(key=lambda x: x["start"])
    _sogo_cache = (time.time(), today, events)
    return events


def _eventos_de_hoy(cal, today: datetime.date) -> list:
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
            "uid":      str(comp.get("UID", "")),
        })
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
    return bool(env("WOFFU_ICAL_URL"))


def _eventos_ausencia() -> list:
    """[{nombre, dia, pendiente}] del iCal de Woffu (un evento por persona y día).
    Cacheado ICAL_CACHE_TTL segundos. Lanza excepción si falla la descarga."""
    global _ical_cache
    if _ical_cache and time.time() - _ical_cache[0] < ICAL_CACHE_TTL:
        return _ical_cache[1]
    resp = requests.get(env("WOFFU_ICAL_URL"), timeout=30)
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
