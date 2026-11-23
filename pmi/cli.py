"""Interfaz de línea de comandos del sistema.

  python -m pmi.cli preflight            # ¿abre NYSE hoy? fase, entorno, salida 0=abre, 10=cerrado
  python -m pmi.cli clock                # fase actual y minutos al corte/envío
  python -m pmi.cli calendar-fetch       # descarga Forex Factory (1 vez por ejecución)
  python -m pmi.cli calendar-show        # eventos de hoy con estado PENDIENTE/PUBLICADO
  python -m pmi.cli fred-fetch           # cierres oficiales (Treasuries, VIX, WTI, SPX)
  python -m pmi.cli build                # valida work/report.json y genera out/report.html|txt
  python -m pmi.cli send --backend resend|gmail_connector [--at 08:59:15] [--kind report|test|alert]
  python -m pmi.cli record-sent --backend gmail_connector --provider-id ID
  python -m pmi.cli alert --reason "..."  # genera correo de FALLO (lo usa el vigilante)
  python -m pmi.cli status               # ¿ya se envió hoy?
Opciones globales: --date YYYY-MM-DD  --now ISO (simulación)  --work DIR  --out DIR
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import ROOT, __version__, load_config
from . import calendar_nyse as cal
from . import econ_calendar, market_data, mailer, news, render, timing
from .runlog import RunLog


def _paths(a) -> tuple[Path, Path]:
    w = Path(a.work or ROOT / "work")
    o = Path(a.out or ROOT / "out")
    w.mkdir(parents=True, exist_ok=True)
    o.mkdir(parents=True, exist_ok=True)
    return w, o


def _now(a) -> dt.datetime:
    return timing.now_et(a.now)


def _day(a) -> dt.date:
    return dt.date.fromisoformat(a.date) if a.date else _now(a).date()


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# ----------------------------------------------------------------- commands
def cmd_preflight(a) -> int:
    w, o = _paths(a)
    log = RunLog(w / "runlog.jsonl")
    day, now = _day(a), _now(a)
    info = cal.session_info(day)
    out = {
        "date_ny": day.isoformat(), "session": info, "clock": timing.phase(now),
        "send_target": timing.send_target_mx_label(day),
        "calendar_coverage_ok": cal.coverage_ok(day),
        "env": {"RESEND_API_KEY": bool(os.environ.get("RESEND_API_KEY")),
                "PMI_RECIPIENT": bool(os.environ.get("PMI_RECIPIENT"))},
        "already_sent_today": mailer.marker_path(o, day.isoformat(), "report").exists(),
        "version": __version__,
    }
    if info["open"]:
        out["previous_trading_day"] = cal.previous_trading_day(day).isoformat()
        out["news_window_from"] = f"Cierre del {out['previous_trading_day']} 16:00 ET"
    log.add("preflight", open=info["open"], reason=info["reason"], phase=out["clock"]["phase"])
    _print(out)
    if info["open"] is None:
        return 20  # fuera de cobertura: verificar nyse.com manualmente
    return 0 if info["open"] else 10


def cmd_clock(a) -> int:
    _print(timing.phase(_now(a)))
    return 0


def cmd_calendar_fetch(a) -> int:
    w, _ = _paths(a)
    log = RunLog(w / "runlog.jsonl")
    res = econ_calendar.fetch_feed(w / "ff_week.json", wait_on_ratelimit=a.wait)
    log.add("forexfactory_fetch", **res)
    _print(res)
    return 0 if res["ok"] else 2


def cmd_calendar_show(a) -> int:
    w, _ = _paths(a)
    rep = _load_report(w, required=False)
    res = econ_calendar.events_for_day(w / "ff_week.json", _day(a), _now(a),
                                       rep.get("calendar_updates"), rep.get("calendar_extra"))
    if a.usd_only:
        res["rows"] = [r for r in res["rows"] if r["country"] == "USD"]
    _print(res)
    return 0 if res["ok"] else 2


def cmd_fred_fetch(a) -> int:
    w, _ = _paths(a)
    res = market_data.fetch_fred(w / "fred.json", _day(a))
    RunLog(w / "runlog.jsonl").add("fred_fetch", ok=sorted(res["series"]), errors=res["errors"])
    _print({k: {"value": v["value"], "date": v["date"], "change": v["change"]}
            for k, v in res["series"].items()} | {"errors": res["errors"]})
    return 0 if res["series"] else 2


def _load_report(w: Path, required=True) -> dict:
    p = w / "report.json"
    if not p.exists():
        if required:
            raise SystemExit(f"No existe {p}")
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _market_rows(rep: dict, w: Path) -> tuple[list, list]:
    rows, warns = [], []
    for m in rep.get("market", []):
        need = ("label", "value", "timestamp", "source")
        miss = [k for k in need if not m.get(k)]
        if miss:
            warns.append(f"Indicador omitido por falta de {miss}: {m.get('label', '?')}")
            continue
        rows.append({"group": m.get("group", "Premarket / tiempo cercano"), **m})
    rows += market_data.fred_rows(w / "fred.json")
    return rows, warns


def build_context(a, w: Path, o: Path) -> dict:
    cfg = load_config()
    day, now = _day(a), _now(a)
    rep = _load_report(w)
    log = RunLog(w / "runlog.jsonl")
    tri = news.triage(rep.get("news", []), rep.get("unconfirmed", []))
    mrows, mwarn = _market_rows(rep, w)
    calres = econ_calendar.events_for_day(w / "ff_week.json", day, now, rep.get("calendar_updates"),
                                          rep.get("calendar_extra"))
    warnings = tri["warnings"] + mwarn + [f"Actualización de calendario sin coincidencia: {u.get('match')}"
                                          for u in calres.get("unmatched_updates", [])]
    cutoff = dt.datetime.fromisoformat(rep["cutoff_et"]) if rep.get("cutoff_et") else now
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timing.ET)
    partial = bool(rep.get("partial"))
    pf = log.first("preflight")
    ff = log.last("forexfactory_fetch")
    fr = log.last("fred_fetch")
    sch = cfg["schedule"]
    log_lines = [
        f"Programación: tarea diaria {sch['task_start_et']} ET · corte objetivo {sch['info_cutoff_et']} ET · "
        f"envío objetivo {sch['send_target_et'][:5]} ET (zona America/New_York; DST automático).",
        f"Inicio de sesión: {pf['et'] if pf else 'N/D'} ({pf['cdmx'] + ' CDMX' if pf else ''}).",
        f"Forex Factory: {'OK' if ff and ff.get('ok') else 'FALLÓ — ' + str(ff.get('error') if ff else 'no ejecutado')}.",
        f"FRED: {'OK ' + ','.join(fr['ok']) if fr and fr.get('ok') else 'sin datos'}"
        + (f"; errores {list(fr['errors'])}" if fr and fr.get('errors') else "") + ".",
        f"Noticias: {sum(tri['counts'][k] for k in ('CRÍTICO', 'ALTO', 'MODERADO'))} confirmadas, "
        f"{tri['counts']['no_confirmadas']} no confirmadas, {len(tri['merge_log'])} fusiones de duplicados.",
        f"Fuentes consultadas: {rep.get('sources_consulted_count', 'N/D')}. Fuentes con fallo: "
        f"{', '.join(rep.get('sources_failed', [])) or 'ninguna reportada'}.",
        f"Generado: {timing.fmt_pair(now)} · advertencias de validación: {len(warnings)}.",
    ]
    log_lines += [str(n) for n in rep.get("notes", [])]
    subj = render.subject(cfg["email"]["subject_template"], day, partial)
    if a.kind == "test":
        subj = "[PRUEBA] " + subj
    return {"report": rep, "triage": tri, "date": day, "partial": partial, "session": cal.session_info(day),
            "market_rows": mrows, "calendar": calres, "warnings": warnings, "log_lines": log_lines,
            "generated_label": timing.fmt_pair(now), "cutoff_label": timing.fmt_pair(cutoff),
            "open_label": f"09:30 ET / {timing.to_mx(timing.at_et(day, '09:30')):%H:%M} CDMX"
                          + (" · cierre 13:00 ET" if cal.session_info(day).get("reason") == "CIERRE_ANTICIPADO" else ""),
            "subject": subj, "version": __version__}


def cmd_build(a) -> int:
    w, o = _paths(a)
    ctx = build_context(a, w, o)
    html = render.render_html(ctx)
    # Gmail recorta >102 KB: degradar a formato compacto por niveles (moderado, luego alto)
    for levels in (("MODERADO",), ("MODERADO", "ALTO"), ("MODERADO", "ALTO", "CRÍTICO")):
        if len(html.encode("utf-8")) / 1024 <= 92:
            break
        ctx["compact_levels"] = levels
        html = render.render_html(ctx)
        ctx["warnings"].append(f"Formato compacto aplicado a {', '.join(levels)} por tamaño")
    text = render.render_text(ctx)
    (o / "report.html").write_text(html, encoding="utf-8")
    (o / "report.txt").write_text(text, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    if size_kb > 100:
        ctx["warnings"].append(f"HTML de {size_kb:.0f} KB: Gmail puede recortarlo; acortar resúmenes")
    summary = {"subject": ctx["subject"], "html_kb": round(size_kb, 1), "counts": ctx["triage"]["counts"],
               "calendar_rows": len(ctx["calendar"].get("rows", [])), "market_rows": len(ctx["market_rows"]),
               "partial": ctx["partial"], "warnings": ctx["warnings"], "merges": ctx["triage"]["merge_log"],
               "html": str(o / "report.html"), "text": str(o / "report.txt")}
    (o / "build.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    RunLog(w / "runlog.jsonl").add("build", html_kb=summary["html_kb"], counts=summary["counts"],
                                   warnings=len(summary["warnings"]))
    _print(summary)
    return 0


def cmd_send(a) -> int:
    w, o = _paths(a)
    log = RunLog(w / "runlog.jsonl")
    cfg = load_config()
    day = _day(a).isoformat()
    marker = mailer.marker_path(o, day, a.kind)
    if marker.exists() and not a.force:
        _print({"ok": True, "skipped": "ya enviado en esta sesión", "marker": str(marker)})
        return 0
    to = mailer.recipient(a.to)
    html_p, text_p = o / ("alert.html" if a.kind == "alert" else "report.html"), \
        o / ("alert.txt" if a.kind == "alert" else "report.txt")
    if not html_p.exists():
        raise SystemExit("Primero ejecuta build (o alert)")
    subj = json.loads((o / ("alert.json" if a.kind == "alert" else "build.json")).read_text(encoding="utf-8"))["subject"]
    if a.at:
        waited = mailer.wait_until(timing.at_et(_day(a), a.at))
        log.add("send_wait", target=a.at, waited_s=round(waited, 1))
    deadline = timing.at_et(_day(a), cfg["schedule"]["hard_deadline_et"]) + dt.timedelta(minutes=15)
    if a.backend == "resend":
        log.add("send_attempt", backend="resend", kind=a.kind)
        res = mailer.send_resend(to=to, subject=subj, html=html_p.read_text(encoding="utf-8"),
                                 text=text_p.read_text(encoding="utf-8"),
                                 idem_key=f"pmi-{day}-{a.kind}" + ("-force" if a.force else ""),
                                 deadline=deadline)
        rec = log.add("send_result", **res)
        if res.get("ok"):
            marker.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        _print(rec)
        return 0 if res.get("ok") else 3
    p = mailer.prepare_connector_request(o, to=to, subject=subj, html_path=html_p, text_path=text_p, kind=a.kind)
    log.add("send_prepared", backend="gmail_connector", kind=a.kind)
    _print(json.loads(p.read_text(encoding="utf-8")))
    return 0


def cmd_record_sent(a) -> int:
    w, o = _paths(a)
    rec = RunLog(w / "runlog.jsonl").add("send_result", ok=True, backend=a.backend, provider_id=a.provider_id,
                                         kind=a.kind)
    mailer.marker_path(o, _day(a).isoformat(), a.kind).write_text(json.dumps(rec, ensure_ascii=False),
                                                                  encoding="utf-8")
    _print(rec)
    return 0


def cmd_alert(a) -> int:
    w, o = _paths(a)
    day = _day(a)
    now = _now(a)
    subj = f"⚠ FALLO | PREMARKET S&P 500 | {render.fecha_corta(day)} | reporte no entregado"
    body = (f"El reporte PREMARKET INTELLIGENCE del {render.fecha_larga(day)} no se confirmó como enviado "
            f"a las {timing.fmt_pair(now)}.\n\nMotivo detectado: {a.reason}\n\n"
            "Revisa la ejecución de la tarea programada en Claude. Este aviso lo genera el vigilante.")
    html = (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#14202B;'
            f'max-width:640px;border-left:4px solid #B42318;padding:12px 16px;">'
            f'<b style="color:#B42318;">PREMARKET INTELLIGENCE — FALLO DE ENTREGA</b><br><br>'
            f'{render.e(body).replace(chr(10), "<br>")}</div>')
    (o / "alert.html").write_text(html, encoding="utf-8")
    (o / "alert.txt").write_text(body, encoding="utf-8")
    (o / "alert.json").write_text(json.dumps({"subject": subj}, ensure_ascii=False), encoding="utf-8")
    RunLog(w / "runlog.jsonl").add("alert_built", reason=a.reason)
    _print({"subject": subj, "html": str(o / "alert.html")})
    return 0


def cmd_addendum(a) -> int:
    """Adenda breve de ÚLTIMA HORA (work/addendum.json -> out/addendum.html|txt).

    Se envía como respuesta en el hilo del reporte cuando entre el borrador y el
    corte final aparece información material. Mismas reglas de verificación.
    """
    w, o = _paths(a)
    cfg = load_config()
    day, now = _day(a), _now(a)
    data = json.loads((w / "addendum.json").read_text(encoding="utf-8"))
    tri = news.triage(data.get("news", []))
    items = [x for lvl in ("CRÍTICO", "ALTO", "MODERADO") for x in tri["by_level"][lvl]]
    cutoff = data.get("cutoff_et") or now.isoformat()
    ct = dt.datetime.fromisoformat(cutoff)
    ct = ct if ct.tzinfo else ct.replace(tzinfo=timing.ET)
    subj = cfg["email"]["addendum_subject_template"].format(date=render.fecha_corta(day))
    head = (f'<tr><td style="background:{render.C["CRÍTICO"]};padding:14px 24px;color:#FFFFFF;font-size:16px;'
            f'font-weight:bold;">ÚLTIMA HORA — PREMARKET INTELLIGENCE<div style="font-size:12px;font-weight:normal;'
            f'padding-top:4px;">Actualización posterior al reporte principal · corte {render.e(timing.fmt_pair(ct))}'
            f'</div></td></tr>')
    if data.get("note"):
        head += f'<tr><td style="padding:12px 24px 0 24px;font-size:14px;">{render.e(data["note"])}</td></tr>'
    cards = "".join(render._news_card(it) for it in items)
    html = (f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"></head><body style="margin:0;background:{render.C["bg"]};">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:700px;'
            f'background:#FFFFFF;font-family:{render.FONT};color:{render.C["ink"]};">{head}{cards}'
            f'<tr><td style="padding:16px 24px;font-size:11px;color:{render.C["muted"]};">Contexto, no recomendación.'
            f'</td></tr></table></body></html>').replace(f"font-family:{render.FONT};", "", 0)
    html = html.replace("font-family:Arial,Helvetica,sans-serif;font-size:", "font-size:")
    text = "ÚLTIMA HORA — PREMARKET INTELLIGENCE\n" + f"Corte: {timing.fmt_pair(ct)}\n\n" + "\n\n".join(
        f"[{x['level']}] {x['title']}\n{x.get('summary', '')}\nPor qué importa: {x.get('why_it_matters', '')}\n"
        f"Sesgo: {x['bias']}\n" + "\n".join(f"Fuente: {s['name']} {s['url']}" for s in x["sources"]) for x in items)
    (o / "addendum.html").write_text(html, encoding="utf-8")
    (o / "addendum.txt").write_text(text, encoding="utf-8")
    RunLog(w / "runlog.jsonl").add("addendum_built", items=len(items), warnings=len(tri["warnings"]))
    _print({"subject": subj, "items": len(items), "unconfirmed_dropped": len(tri["unconfirmed"]),
            "warnings": tri["warnings"], "html": str(o / "addendum.html"), "text": str(o / "addendum.txt")})
    return 0 if items else 4


def cmd_status(a) -> int:
    w, o = _paths(a)
    day = _day(a).isoformat()
    _print({"date": day, "report_sent": mailer.marker_path(o, day, "report").exists(),
            "log": RunLog(w / "runlog.jsonl").read()[-12:]})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pmi")
    ap.add_argument("--date")
    ap.add_argument("--now")
    ap.add_argument("--work")
    ap.add_argument("--out")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    sub.add_parser("clock")
    p = sub.add_parser("calendar-fetch")
    p.add_argument("--wait", type=float, default=75)
    p = sub.add_parser("calendar-show")
    p.add_argument("--usd-only", action="store_true")
    sub.add_parser("fred-fetch")
    p = sub.add_parser("build")
    p.add_argument("--kind", default="report", choices=["report", "test"])
    p = sub.add_parser("send")
    p.add_argument("--backend", default="resend", choices=["resend", "gmail_connector"])
    p.add_argument("--to")
    p.add_argument("--at", help="HH:MM[:SS] ET; espera hasta esa hora si es futura")
    p.add_argument("--kind", default="report", choices=["report", "test", "alert"])
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("record-sent")
    p.add_argument("--backend", default="gmail_connector")
    p.add_argument("--provider-id", default="")
    p.add_argument("--kind", default="report", choices=["report", "test", "alert"])
    p = sub.add_parser("alert")
    p.add_argument("--reason", required=True)
    sub.add_parser("status")
    sub.add_parser("addendum")
    a = ap.parse_args(argv)
    a.kind = getattr(a, "kind", "report")
    fn = {"preflight": cmd_preflight, "clock": cmd_clock, "calendar-fetch": cmd_calendar_fetch,
          "calendar-show": cmd_calendar_show, "fred-fetch": cmd_fred_fetch, "build": cmd_build,
          "send": cmd_send, "record-sent": cmd_record_sent, "alert": cmd_alert, "status": cmd_status,
          "addendum": cmd_addendum}[a.cmd]
    return fn(a)


if __name__ == "__main__":
    sys.exit(main())
