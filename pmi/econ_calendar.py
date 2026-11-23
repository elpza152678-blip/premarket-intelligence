"""Calendario económico: feed JSON oficial de Forex Factory + actualizaciones verificadas.

El feed `ff_calendar_thisweek.json` publica título, país/moneda, hora, impacto,
pronóstico y dato anterior. NO incluye el dato real: los datos reales los
aporta el agente desde la fuente oficial (BLS, BEA, DOL, Census, etc.) en
`report.json -> calendar_updates`. Sin dato verificado => "N/D", nunca estimado.

El feed tiene límite de peticiones; se hace una sola descarga por ejecución,
con reintento espaciado, y se guarda en caché local.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from . import load_config
from .httpget import FetchError, get
from .timing import ET, MX

IMPACT_ES = {"High": "ALTO", "Medium": "MEDIO", "Low": "BAJO", "Holiday": "FERIADO",
             "Non-Economic": "NO ECON."}


def fetch_feed(cache: Path, *, wait_on_ratelimit: float = 75, attempts: int = 3) -> dict:
    url = load_config()["sources"]["forexfactory_feed"]
    err = None
    for i in range(attempts):
        try:
            status, body = get(url, retries=0, timeout=25)
            txt = body.decode("utf-8", "replace").strip()
            if not txt.startswith("["):
                raise FetchError("Respuesta no-JSON (probable 'Rate Limited')")
            events = json.loads(txt)
            payload = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                       "source": url, "events": events}
            cache.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            return {"ok": True, "count": len(events), "cache": str(cache)}
        except Exception as e:  # noqa: BLE001
            err = str(e)
            if i < attempts - 1:
                time.sleep(wait_on_ratelimit)
    return {"ok": False, "error": err}


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().replace("m/m", "mom").replace("y/y", "yoy").split())


def events_for_day(cache: Path, day: dt.date, now: dt.datetime, updates: list | None = None,
                   extra: list | None = None, min_impact: tuple = ("High", "Medium", "Low")) -> dict:
    """Filas del calendario para el día (fecha de Nueva York) con estado PENDIENTE/PUBLICADO."""
    if not cache.exists():
        return {"ok": False, "rows": [], "error": "Sin caché de Forex Factory",
                "source_note": "Forex Factory no disponible en esta ejecución"}
    data = json.loads(cache.read_text(encoding="utf-8"))
    updates = updates or []
    rows = []
    for ev in data["events"]:
        try:
            t = dt.datetime.fromisoformat(ev["date"]).astimezone(ET)
        except Exception:  # noqa: BLE001
            continue
        if t.date() != day or ev.get("impact") not in min_impact:
            continue
        # Ruido: eventos de impacto bajo fuera de EE. UU. no se muestran
        if ev.get("impact") == "Low" and ev.get("country") != "USD":
            continue
        rows.append(_row(ev.get("country", ""), ev.get("title", ""), t, ev.get("impact", ""),
                         ev.get("previous", ""), ev.get("forecast", ""), "Forex Factory"))
    for ex in extra or []:  # eventos verificados que el feed no trae (subastas, Fed speakers...)
        t = dt.datetime.fromisoformat(ex["time_et"]).replace(tzinfo=ET) if "T" in ex["time_et"] \
            else dt.datetime.combine(day, dt.time.fromisoformat(ex["time_et"]), tzinfo=ET)
        r = _row(ex.get("country", "USD"), ex["title"], t, ex.get("impact", "Medium"),
                 ex.get("previous", ""), ex.get("forecast", ""), ex.get("source", "Oficial"))
        r["url"] = ex.get("url", "")
        rows.append(r)
    applied = set()
    for r in rows:
        for j, u in enumerate(updates):
            if _norm(u.get("match")) in _norm(r["event"]) and \
                    (not u.get("country") or u["country"].upper() == r["country"].upper()):
                if u.get("actual") not in (None, ""):
                    r["actual"] = str(u["actual"])
                    r["actual_source"] = u.get("source", "")
                    r["url"] = u.get("url", r.get("url", ""))
                if u.get("forecast_override"):
                    r["consensus"] = str(u["forecast_override"])
                if u.get("surprise"):
                    r["surprise"] = u["surprise"]
                applied.add(j)
    for r in rows:
        t = dt.datetime.fromisoformat(r["time_et_iso"])
        if r.get("all_day"):
            r["status"] = "TODO EL DÍA"
        elif t > now:
            r["status"] = "PENDIENTE"
        elif r["actual"] != "N/D":
            r["status"] = "PUBLICADO"
        else:
            r["status"] = "PUBLICADO · real N/D"
    rows.sort(key=lambda r: (r["time_et_iso"], r["country"]))
    unmatched = [u for j, u in enumerate(updates) if j not in applied]
    return {"ok": True, "rows": rows, "fetched_at": data.get("fetched_at"),
            "unmatched_updates": unmatched,
            "source_note": f"Forex Factory (feed oficial), descargado {data.get('fetched_at', '')[:16]}Z"}


def _row(country, title, t, impact, previous, forecast, src) -> dict:
    all_day = t.hour == 0 and t.minute == 0
    return {
        "time_et": "Todo el día" if all_day else t.strftime("%H:%M"),
        "time_mx": "—" if all_day else t.astimezone(MX).strftime("%H:%M"),
        "time_et_iso": t.isoformat(),
        "all_day": all_day,
        "country": country,
        "event": title,
        "impact": IMPACT_ES.get(impact, impact or "N/D"),
        "previous": previous or "N/D",
        "consensus": forecast or "N/D",
        "actual": "N/D",
        "source": src,
    }
