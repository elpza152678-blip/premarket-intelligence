"""Reloj del sistema: horas ET/CDMX, fases de la ejecución y fechas límite.

Toda la lógica horaria se basa en zoneinfo (IANA), por lo que los cambios
EDT<->EST se aplican solos. CDMX no tiene horario de verano desde 2022.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from . import load_config

ET = ZoneInfo("America/New_York")
MX = ZoneInfo("America/Mexico_City")
UTC = dt.timezone.utc


def now_et(override: str | None = None) -> dt.datetime:
    """Hora actual en ET. `override` (ISO) permite simular en pruebas."""
    if override:
        t = dt.datetime.fromisoformat(override)
        if t.tzinfo is None:
            t = t.replace(tzinfo=ET)
        return t.astimezone(ET)
    return dt.datetime.now(UTC).astimezone(ET)


def at_et(day: dt.date, hhmm: str) -> dt.datetime:
    parts = [int(p) for p in hhmm.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return dt.datetime(day.year, day.month, day.day, *parts, tzinfo=ET)


def to_mx(t: dt.datetime) -> dt.datetime:
    return t.astimezone(MX)


def fmt_pair(t: dt.datetime) -> str:
    """'08:58 ET (EST) / 07:58 CDMX'."""
    e = t.astimezone(ET)
    m = t.astimezone(MX)
    return f"{e:%H:%M} ET ({e.tzname()}) / {m:%H:%M} CDMX"


def schedule_for(day: dt.date) -> dict[str, dt.datetime]:
    sch = load_config()["schedule"]
    return {k.removesuffix("_et"): at_et(day, v) for k, v in sch.items()}


PHASES = [
    ("start", "INICIO: preflight, calendario económico, datos FRED"),
    ("research_until", "INVESTIGACIÓN AMPLIA (noticias desde el cierre anterior)"),
    ("macro_release_check", "ESPERAR/CAPTURAR datos de las 8:30 ET"),
    ("compose_by", "REDACTAR report.json y build (versión enviable)"),
    ("draft_by", "BARRIDO final de última hora; actualizar report.json y rebuild"),
    ("info_cutoff", "CORTE: build final y lanzar send --at 08:59:15"),
    ("send_target", "ENVIAR ahora (send sin --at)"),
    ("hard_deadline", "ENVÍO TARDÍO: enviar de inmediato (marcar retraso)"),
]


def phase(now: dt.datetime | None = None) -> dict:
    now = now or now_et()
    s = schedule_for(now.date())
    s["start"] = s.pop("task_start")
    order = ["start", "research_until", "macro_release_check", "compose_by", "draft_by",
             "info_cutoff", "send_target", "hard_deadline"]
    current = "antes_de_inicio"
    label = "Antes de la hora programada"
    nxt = order[0]
    for i, key in enumerate(order):
        if now >= s[key]:
            current = key
            label = dict(PHASES)[key]
            nxt = order[i + 1] if i + 1 < len(order) else None
    out = {
        "now": fmt_pair(now),
        "now_iso": now.isoformat(),
        "tz_et": now.tzname(),
        "phase": current,
        "instruction": label,
        "next_milestone": nxt,
    }
    if nxt:
        out["minutes_to_next"] = round((s[nxt] - now).total_seconds() / 60, 1)
    out["minutes_to_cutoff"] = round((s["info_cutoff"] - now).total_seconds() / 60, 1)
    out["minutes_to_send"] = round((s["send_target"] - now).total_seconds() / 60, 1)
    return out


def send_target_mx_label(day: dt.date) -> str:
    """Etiqueta del objetivo de envío 9:00 ET en ambos husos (para el reporte)."""
    return fmt_pair(at_et(day, "09:00"))
