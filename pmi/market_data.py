"""Datos de mercado de referencia (cierres oficiales vía FRED).

Son CIERRES del día hábil previo, no tiempo real, y se etiquetan así.
Las cotizaciones de premarket (futuros ES/NQ, DXY, etc.) las aporta el agente
en report.json con valor, instrumento, timestamp y fuente verificables.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
from pathlib import Path

from . import load_config
from .httpget import get


def fetch_fred(out: Path, today: dt.date) -> dict:
    cfg = load_config()
    start = (today - dt.timedelta(days=20)).isoformat()
    result, errors = {}, {}
    for sid, label in cfg["fred_series"].items():
        url = cfg["sources"]["fred_csv"].format(series=sid, start=start)
        try:
            _, body = get(url, timeout=20, retries=2)
            rows = [r for r in csv.reader(io.StringIO(body.decode("utf-8")))][1:]
            obs = [(d, float(v)) for d, v in rows if v not in ("", ".")]
            if not obs:
                raise ValueError("sin observaciones")
            (d1, v1) = obs[-1]
            chg = round(v1 - obs[-2][1], 4) if len(obs) > 1 else None
            result[sid] = {"label": label, "value": v1, "date": d1, "change": chg,
                           "prev_date": obs[-2][0] if len(obs) > 1 else None,
                           "source": "FRED (St. Louis Fed)",
                           "url": f"https://fred.stlouisfed.org/series/{sid}"}
        except Exception as e:  # noqa: BLE001
            errors[sid] = str(e)
    payload = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "series": result,
               "errors": errors}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def fred_rows(path: Path) -> list[dict]:
    """Filas de 'cierre previo oficial' para el termómetro."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    unit = {"DGS10": "%", "DGS2": "%", "VIXCLS": "", "DCOILWTICO": " USD", "SP500": ""}
    for sid, s in data.get("series", {}).items():
        chg = s.get("change")
        if sid in ("DGS10", "DGS2") and chg is not None:
            chg_txt = f"{chg * 100:+.0f} pb"
        elif chg is not None:
            chg_txt = f"{chg:+.2f}"
        else:
            chg_txt = "N/D"
        rows.append({
            "group": "Cierre previo oficial",
            "label": s["label"],
            "value": f"{s['value']:,.2f}{unit.get(sid, '')}",
            "change": chg_txt,
            "timestamp": f"Cierre {s['date']}",
            "source": s["source"],
            "url": s["url"],
            "realtime": False,
        })
    # 2s10s si existen ambos
    ser = data.get("series", {})
    if "DGS10" in ser and "DGS2" in ser and ser["DGS10"]["date"] == ser["DGS2"]["date"]:
        spread = (ser["DGS10"]["value"] - ser["DGS2"]["value"]) * 100
        rows.append({"group": "Cierre previo oficial", "label": "Pendiente 2s10s",
                     "value": f"{spread:+.0f} pb", "change": "—",
                     "timestamp": f"Cierre {ser['DGS10']['date']}", "source": "Cálculo sobre FRED",
                     "url": "https://fred.stlouisfed.org/series/T10Y2Y", "realtime": False})
    return rows
