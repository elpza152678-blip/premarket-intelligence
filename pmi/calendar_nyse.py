"""Calendario oficial de la sesión regular de NYSE.

Fuente: https://www.nyse.com/markets/hours-calendars (verificado 2026-11-23)
y contrastado contra la librería exchange_calendars (XNYS): coinciden.

Mantenimiento: cada diciembre, añadir el año siguiente+2 desde la página
oficial. `coverage_ok()` avisa cuando la tabla está por agotarse.
Cierres extraordinarios (p. ej. duelo nacional) se añaden a EXTRAORDINARY.
"""
from __future__ import annotations

import datetime as dt

HOLIDAYS = {
    # 2026
    "2026-01-01": "New Year's Day",
    "2026-01-19": "Martin Luther King, Jr. Day",
    "2026-02-16": "Washington's Birthday",
    "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving Day",
    "2026-12-25": "Christmas Day",
    # 2027
    "2027-01-01": "New Year's Day",
    "2027-01-18": "Martin Luther King, Jr. Day",
    "2027-02-15": "Washington's Birthday",
    "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth (observed)",
    "2027-07-05": "Independence Day (observed)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving Day",
    "2027-12-24": "Christmas Day (observed)",
    # 2028 (Año Nuevo cae en sábado: no se observa)
    "2028-01-17": "Martin Luther King, Jr. Day",
    "2028-02-21": "Washington's Birthday",
    "2028-04-14": "Good Friday",
    "2028-05-29": "Memorial Day",
    "2028-06-19": "Juneteenth",
    "2028-07-04": "Independence Day",
    "2028-09-04": "Labor Day",
    "2028-11-23": "Thanksgiving Day",
    "2028-12-25": "Christmas Day",
}

# Sesión regular termina a la 1:00 p.m. ET (sí hay apertura a las 9:30: se envía reporte)
EARLY_CLOSES = {
    "2026-11-27": "Día después de Thanksgiving",
    "2026-12-24": "Nochebuena",
    "2027-11-26": "Día después de Thanksgiving",
    "2028-07-03": "Víspera de Independence Day",
    "2028-11-24": "Día después de Thanksgiving",
}

# Cierres no programados anunciados por NYSE (añadir manualmente si ocurren)
EXTRAORDINARY: dict[str, str] = {}

COVERED_THROUGH = dt.date(2028, 12, 31)


def _key(d: dt.date) -> str:
    return d.isoformat()


def session_info(d: dt.date) -> dict:
    """Describe la sesión regular de NYSE para la fecha d (fecha de Nueva York)."""
    k = _key(d)
    if d > COVERED_THROUGH:
        return {"date": k, "open": None, "reason": "FUERA_DE_COBERTURA",
                "detail": "Tabla de festivos no cubre esta fecha; verificar nyse.com"}
    if d.weekday() >= 5:
        return {"date": k, "open": False, "reason": "FIN_DE_SEMANA", "detail": d.strftime("%A")}
    if k in EXTRAORDINARY:
        return {"date": k, "open": False, "reason": "CIERRE_EXTRAORDINARIO", "detail": EXTRAORDINARY[k]}
    if k in HOLIDAYS:
        return {"date": k, "open": False, "reason": "FESTIVO", "detail": HOLIDAYS[k]}
    early = k in EARLY_CLOSES
    return {"date": k, "open": True, "reason": "CIERRE_ANTICIPADO" if early else "SESION_REGULAR",
            "detail": EARLY_CLOSES.get(k, ""), "open_et": "09:30",
            "close_et": "13:00" if early else "16:00"}


def is_trading_day(d: dt.date) -> bool:
    return bool(session_info(d)["open"])


def previous_trading_day(d: dt.date) -> dt.date:
    x = d - dt.timedelta(days=1)
    while not is_trading_day(x):
        x -= dt.timedelta(days=1)
    return x


def next_trading_day(d: dt.date) -> dt.date:
    x = d + dt.timedelta(days=1)
    while not is_trading_day(x):
        x += dt.timedelta(days=1)
    return x


def coverage_ok(today: dt.date, margin_days: int = 60) -> bool:
    return (COVERED_THROUGH - today).days > margin_days
