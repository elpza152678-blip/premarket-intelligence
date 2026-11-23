"""Render del correo: HTML responsive con estilos inline (compatible con Gmail) + texto plano.

Notas de compatibilidad:
- Solo tablas y estilos inline; sin <style>, sin JS, sin imágenes, sin web fonts.
- Gmail recorta mensajes de más de ~102 KB ("Mensaje recortado"): `build` avisa
  si el HTML se acerca a ese límite y el HTML se minimiza.
"""
from __future__ import annotations

import datetime as dt
import html
import re

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

C = {
    "ink": "#14202B", "muted": "#5B6B7B", "line": "#E3E8EE", "bg": "#F3F5F7", "card": "#FFFFFF",
    "navy": "#0B1F33", "gold": "#B8925A",
    "CRÍTICO": "#B42318", "ALTO": "#B54708", "MODERADO": "#1D4E89",
    "Alcista": "#067647", "Bajista": "#B42318", "Mixto / incierto": "#475467",
    "link": "#1D4E89", "warn_bg": "#FFF8EC", "warn_line": "#F2D7A6",
}
FONT = "Arial,Helvetica,sans-serif"


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def safe_url(u: str) -> str:
    u = str(u or "").strip()
    return e(u) if u.startswith(("http://", "https://")) else ""


def fecha_larga(d: dt.date) -> str:
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]} de {d.year}"


def fecha_corta(d: dt.date) -> str:
    return f"{d.day:02d}-{MESES[d.month - 1][:3].upper()}-{d.year}"


def subject(template: str, d: dt.date, partial: bool) -> str:
    s = template.format(date=fecha_corta(d))
    return s + (" | PARCIAL" if partial else "")


# ---------------------------------------------------------------- HTML helpers
def _h2(num: str, title: str) -> str:
    return (f'<tr><td style="padding:26px 24px 8px 24px;font-family:{FONT};">'
            f'<div style="font-size:11px;letter-spacing:2px;color:{C["gold"]};font-weight:bold;">{e(num)}</div>'
            f'<div style="font-size:18px;color:{C["navy"]};font-weight:bold;border-bottom:2px solid {C["navy"]};'
            f'padding-bottom:6px;">{e(title)}</div></td></tr>')


def _p(text: str, size=14, color=None, extra="") -> str:
    return (f'<div style="font-family:{FONT};font-size:{size}px;line-height:1.55;color:{color or C["ink"]};{extra}">'
            f'{e(text)}</div>')


def _badge(text: str, color: str) -> str:
    return (f'<span style="display:inline-block;font-family:{FONT};font-size:10px;font-weight:bold;'
            f'letter-spacing:1px;color:#FFFFFF;background:{color};padding:2px 7px;border-radius:3px;">{e(text)}</span>')


def _pill(text: str, color: str) -> str:
    return (f'<span style="display:inline-block;font-family:{FONT};font-size:11px;font-weight:bold;'
            f'color:{color};border:1px solid {color};padding:1px 6px;border-radius:3px;">{e(text)}</span>')


def _row(inner: str, pad="6px 24px") -> str:
    return f'<tr><td style="padding:{pad};">{inner}</td></tr>'


def _bullets(items: list[str], color: str) -> str:
    if not items:
        return _p("Sin elementos destacados.", 13, C["muted"])
    lis = "".join(f'<tr><td valign="top" style="width:14px;padding:3px 0;font-family:{FONT};font-size:14px;'
                  f'color:{color};font-weight:bold;">&#9632;</td><td style="padding:3px 0;font-family:{FONT};'
                  f'font-size:14px;line-height:1.5;color:{C["ink"]};">{e(i)}</td></tr>' for i in items)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{lis}</table>'


def _links(sources: list[dict]) -> str:
    parts = []
    for s in sources:
        u = safe_url(s.get("url"))
        name = e(s.get("name", "Fuente"))
        when = f' <span style="color:{C["muted"]};">({e(s["published"])})</span>' if s.get("published") else ""
        parts.append(f'<a href="{u}" style="color:{C["link"]};text-decoration:underline;">{name}</a>{when}'
                     if u else f"{name}{when}")
    return " · ".join(parts) if parts else "N/D"


def _news_card(it: dict) -> str:
    lvl = it["level"]
    meta_rows = [
        ("Estado", e(it["status"]) + (f' — {e(it["update_note"])}' if it.get("update_note") else "")),
        ("Fecha y hora", e(it.get("event_time") or "N/D") +
         (f' · publicada {e(it["published_time"])}' if it.get("published_time") else "")),
        ("Fuente(s)", _links(it.get("sources", []))),
        ("Confianza", f'Hecho: <b>{e(it["confidence_fact"])}</b> · Impacto bursátil: <b>{e(it["confidence_impact"])}</b>'),
    ]
    meta = "<br>".join(f'<span style="color:{C["muted"]};">{k}:</span> {v}' for k, v in meta_rows)
    bias_c = C.get(it["bias"], C["muted"])
    bias_detail = f' <span style="color:{C["ink"]};">{e(it["bias_detail"])}</span>' if it.get("bias_detail") else ""
    return (
        f'<tr><td style="padding:8px 24px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{C["card"]};border:1px solid {C["line"]};border-left:4px solid {C[lvl]};">'
        f'<tr><td style="padding:14px 16px 4px 16px;">{_badge(lvl, C[lvl])}'
        f'{" &nbsp;" + _pill(it["category"], C["muted"]) if it.get("category") else ""}</td></tr>'
        f'<tr><td style="padding:4px 16px 0 16px;font-family:{FONT};font-size:16px;font-weight:bold;'
        f'color:{C["navy"]};line-height:1.35;">{e(it.get("title"))}</td></tr>'
        f'<tr><td style="padding:8px 16px 0 16px;">{_p(it.get("summary", ""))}</td></tr>'
        f'<tr><td style="padding:10px 16px 0 16px;font-family:{FONT};font-size:13px;line-height:1.5;color:{C["ink"]};">'
        f'<b style="color:{C["navy"]};">¿Por qué le importa al S&amp;P 500?</b> {e(it.get("why_it_matters", ""))}</td></tr>'
        f'<tr><td style="padding:8px 16px 0 16px;font-family:{FONT};font-size:13px;line-height:1.5;">'
        f'<b style="color:{C["navy"]};">Sesgo potencial:</b> {_pill(it["bias"], bias_c)}{bias_detail}</td></tr>'
        f'<tr><td style="padding:10px 16px 14px 16px;"><div style="border-top:1px solid {C["line"]};padding-top:8px;'
        f'font-size:12px;line-height:1.55;color:{C["ink"]};">{meta}</div></td></tr>'
        f'</table></td></tr>')


def _news_compact(it: dict) -> str:
    """Versión ligera (mismos campos, menos marcado) para días con muchas noticias."""
    lvl = it["level"]
    upd = f' — {e(it["update_note"])}' if it.get("update_note") else ""
    return (f'<tr><td style="padding:6px 24px;"><div style="border-left:3px solid {C[lvl]};padding:2px 0 2px 10px;'
            f'font-size:13px;line-height:1.5;"><b style="color:{C["navy"]};font-size:14px;">{e(it.get("title"))}</b>'
            f'<br>{e(it.get("summary", ""))}<br><b>Por qué importa:</b> {e(it.get("why_it_matters", ""))}'
            f'<br><b>Sesgo:</b> <span style="color:{C.get(it["bias"], C["muted"])};font-weight:bold;">'
            f'{e(it["bias"])}</span> {e(it.get("bias_detail", ""))}'
            f'<br><span style="color:{C["muted"]};font-size:12px;">{e(lvl)} · {e(it["status"])}{upd} · '
            f'{e(it.get("event_time") or "N/D")} · Confianza hecho {e(it["confidence_fact"])}/impacto '
            f'{e(it["confidence_impact"])} · </span><span style="font-size:12px;">{_links(it.get("sources", []))}'
            f'</span></div></td></tr>')


def _table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None, raw=False) -> str:
    aligns = aligns or ["left"] * len(headers)
    th = "".join(f'<th align="{a}" style="font-size:11px;padding:6px;">{e(h)}</th>' for h, a in zip(headers, aligns))
    trs = []
    for i, r in enumerate(rows):
        bg = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
        tds = "".join(f'<td{" align=" + chr(34) + a + chr(34) if a != "left" else ""} valign="top" style="padding:6px;'
                      f'border-bottom:1px solid {C["line"]};{"white-space:nowrap;" if a == "right" else ""}">'
                      f'{c if raw else e(c)}</td>' for c, a in zip(r, aligns))
        trs.append(f'<tr style="background:{bg};">{tds}</tr>' if i % 2 else f'<tr>{tds}</tr>')
    return (f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
            f'border:1px solid {C["line"]};font-size:12px;line-height:1.35;"><tr style="background:{C["navy"]};'
            f'color:#FFFFFF;">{th}</tr>{"".join(trs)}</table>')


def _section_empty(text: str) -> str:
    return _row(_p(text, 13, C["muted"], "font-style:italic;"))


# ---------------------------------------------------------------- main renderer
def render_html(ctx: dict) -> str:
    r = ctx["report"]
    tri = ctx["triage"]
    d: dt.date = ctx["date"]
    out = []
    partial = ctx["partial"]
    status_badge = _badge("REPORTE PARCIAL", C["CRÍTICO"]) if partial else _badge("REPORTE COMPLETO", "#067647")
    if ctx["session"].get("reason") == "CIERRE_ANTICIPADO":
        status_badge += " " + _badge("CIERRE ANTICIPADO 13:00 ET", C["ALTO"])
    counts = tri["counts"]
    # Encabezado
    out.append(
        f'<tr><td style="background:{C["navy"]};padding:22px 24px 18px 24px;">'
        f'<div style="font-family:{FONT};font-size:11px;letter-spacing:3px;color:{C["gold"]};font-weight:bold;">'
        f'INFORME DIARIO · ANTES DE LA APERTURA</div>'
        f'<div style="font-family:{FONT};font-size:22px;color:#FFFFFF;font-weight:bold;padding-top:4px;">'
        f'PREMARKET INTELLIGENCE — S&amp;P 500</div>'
        f'<div style="font-family:{FONT};font-size:13px;color:#C9D3DD;padding-top:6px;">{e(fecha_larga(d))}</div>'
        f'<div style="font-family:{FONT};font-size:12px;color:#C9D3DD;padding-top:6px;line-height:1.6;">'
        f'Generado: {e(ctx["generated_label"])}<br>Corte de información: <b style="color:#FFFFFF;">'
        f'{e(ctx["cutoff_label"])}</b><br>Apertura NYSE: {e(ctx["open_label"])}</div>'
        f'<div style="padding-top:10px;">{status_badge}</div></td></tr>')
    if partial:
        out.append(_row(
            f'<div style="background:{C["warn_bg"]};border:1px solid {C["warn_line"]};padding:10px 12px;'
            f'font-family:{FONT};font-size:13px;color:{C["ink"]};"><b>Reporte parcial.</b> '
            f'{e(r.get("partial_reason") or "La investigación no se completó antes del límite de envío.")}</div>',
            "14px 24px 0 24px"))
    # I. Resumen
    ex = r.get("executive_summary", {})
    out.append(_h2("I", "Resumen ejecutivo del premarket"))
    out.append(_row(_p(ex.get("overview", "N/D"), 15)))
    out.append(_row(_p(f'Noticias confirmadas: {counts["CRÍTICO"]} críticas · {counts["ALTO"]} de alto impacto · '
                       f'{counts["MODERADO"]} moderadas' +
                       (f' · {counts["no_confirmadas"]} no confirmadas' if counts["no_confirmadas"] else ""),
                       12, C["muted"])))
    for title, key, color in (("Factores alcistas", "bullish", C["Alcista"]),
                              ("Factores bajistas", "bearish", C["Bajista"]),
                              ("Incertidumbres", "uncertain", C["Mixto / incierto"])):
        out.append(_row(f'<div style="font-family:{FONT};font-size:12px;font-weight:bold;letter-spacing:1px;'
                        f'color:{color};padding-top:6px;">{title.upper()}</div>' + _bullets(ex.get(key, []), color)))
    # II. Termómetro
    out.append(_h2("II", "Termómetro de mercado"))
    mrows = ctx["market_rows"]
    if mrows:
        groups: dict[str, list] = {}
        for m in mrows:
            groups.setdefault(m.get("group", "Premarket"), []).append(m)
        for g, items in groups.items():
            rows = []
            for m in items:
                src = (f'<a href="{safe_url(m.get("url"))}" style="color:{C["link"]};">{e(m.get("source"))}</a>'
                       if safe_url(m.get("url")) else e(m.get("source", "")))
                ch = str(m.get("change", "N/D"))
                # verde/rojo solo para índices y futuros de renta variable (en tasas o VIX subir no es "bueno")
                equity = any(k in str(m.get("label", "")) for k in ("S&P", "Nasdaq", "Dow", "Russell", "Nikkei",
                                                                     "Stoxx", "DAX", "Hang Seng", "acciones"))
                col = C["ink"] if not equity else C["Alcista"] if ch.startswith("+") else \
                    C["Bajista"] if ch.startswith(("-", "−")) else C["ink"]
                note = f'<div style="color:{C["muted"]};font-size:11px;">{e(m["note"])}</div>' if m.get("note") else ""
                rows.append([f'<b>{e(m.get("label"))}</b>{note}', e(m.get("value", "N/D")),
                             f'<span style="color:{col};">{e(ch)}</span>',
                             f'{e(m.get("timestamp", "N/D"))}<br>{src}'])
            out.append(_row(f'<div style="font-family:{FONT};font-size:12px;font-weight:bold;color:{C["muted"]};'
                            f'padding:4px 0;">{e(g.upper())}</div>' +
                            _table(["Indicador", "Valor", "Var.", "Hora · Fuente"], rows,
                                   ["left", "right", "right", "left"], raw=True)))
        out.append(_row(_p("Los cierres oficiales corresponden al día hábil previo y no son tiempo real. "
                           "Futuros ≠ índice spot.", 11, C["muted"])))
    else:
        out.append(_section_empty("No fue posible verificar datos de mercado con fuente y hora confiables."))
    # III-V. Noticias
    for num, lvl, title in (("III", "CRÍTICO", "Noticias críticas"), ("IV", "ALTO", "Noticias de alto impacto"),
                            ("V", "MODERADO", "Noticias de impacto moderado")):
        out.append(_h2(num, title))
        if lvl == "CRÍTICO":
            out.append(_row(_p("El sesgo de cada noticia es una interpretación condicional del mecanismo, no una "
                               "predicción. Orden: relevancia y urgencia.", 11, C["muted"])))
        items = tri["by_level"][lvl]
        compact = ctx.get("compact_levels", ())
        if items:
            out.extend((_news_compact if lvl in compact else _news_card)(it) for it in items)
        else:
            out.append(_section_empty(f"Sin noticias de nivel {lvl} que superen el umbral de relevancia."))
    # VI. Calendario
    out.append(_h2("VI", "Calendario económico del día"))
    cal = ctx["calendar"]
    if cal.get("rows"):
        rows = []
        for c in cal["rows"]:
            imp_c = C["CRÍTICO"] if c["impact"] == "ALTO" else C["ALTO"] if c["impact"] == "MEDIO" else C["muted"]
            st = c["status"]
            st_c = "#067647" if st == "PUBLICADO" else C["ALTO"] if st == "PENDIENTE" else C["muted"]
            actual = e(c["actual"])
            if c.get("surprise"):
                actual += f'<div style="font-size:10px;color:{C["muted"]};">{e(c["surprise"])}</div>'
            ev = e(c["event"])
            if c.get("url") and safe_url(c["url"]):
                ev = f'<a href="{safe_url(c["url"])}" style="color:{C["link"]};">{ev}</a>'
            weight = "font-weight:bold;" if c["impact"] == "ALTO" and c["country"] == "USD" else ""
            mute = f'color:{C["muted"]};'
            rows.append([
                f'<span style="{weight}">{e(c["time_et"])}</span><br><span style="{mute}">{e(c["time_mx"])} MX</span>',
                f'<span style="{mute}font-size:11px;">{e(c["country"])}</span>&nbsp; <span style="{weight}">{ev}</span>'
                f'<br><span style="color:{imp_c};font-weight:bold;font-size:10px;">IMPACTO {e(c["impact"])}</span>',
                f'<span style="{mute}">Ant</span> {e(c["previous"])}<br><span style="{mute}">Cons</span> '
                f'{e(c["consensus"])}<br><span style="{mute}">Real</span> <b>{actual}</b>',
                f'<span style="color:{st_c};font-weight:bold;font-size:11px;white-space:nowrap;">'
                f'{e(st).replace(" · ", "<br>")}</span>'])
        out.append(_row(_table(["Hora NY / CDMX", "País · Evento · Impacto", "Anterior / Consenso / Real", "Estado"],
                               rows, ["left", "left", "left", "left"], raw=True)))
        out.append(_row(_p(f'{cal.get("source_note", "")}. Datos reales verificados contra la fuente oficial cuando '
                           'está disponible; "N/D" = no disponible (nunca estimado). Eventos USD de impacto ALTO en negrita.',
                           11, C["muted"])))
    else:
        out.append(_section_empty(f'Calendario no disponible: {cal.get("error", "fuente sin respuesta")}.'))
    # VII. Catalizadores
    out.append(_h2("VII", "Los catalizadores a vigilar hoy"))
    cats = r.get("catalysts", [])
    if cats:
        for c in cats:
            when = f'<span style="color:{C["gold"]};font-weight:bold;">{e(c["time"])} · </span>' if c.get("time") else ""
            out.append(_row(f'<div style="font-family:{FONT};font-size:14px;color:{C["navy"]};font-weight:bold;">'
                            f'{when}{e(c.get("title"))}</div>' + _p(c.get("detail", ""), 13)))
    else:
        out.append(_section_empty("Sin catalizadores adicionales identificados."))
    # VIII. Conclusión
    out.append(_h2("VIII", "Conclusión estratégica"))
    con = r.get("conclusion", {})
    for q, k in (("¿Qué parece estar descontando el mercado?", "priced_in"),
                 ("¿Qué información podría cambiar esas expectativas?", "could_change"),
                 ("¿Dónde podría concentrarse la volatilidad?", "volatility_focus"),
                 ("¿Qué incertidumbres siguen abiertas?", "open_uncertainties")):
        out.append(_row(f'<div style="font-family:{FONT};font-size:13px;font-weight:bold;color:{C["navy"]};">{q}</div>'
                        + _p(con.get(k, "N/D"), 14)))
    # No confirmadas
    if tri["unconfirmed"]:
        out.append(_h2("⚠", "Información no confirmada"))
        out.append(_row(_p("Lo siguiente NO está verificado. Se incluye solo por su posible relevancia; no lo trates "
                           "como un hecho.", 12, C["CRÍTICO"], "font-weight:bold;")))
        for it in tri["unconfirmed"]:
            out.append(_row(f'<div style="font-family:{FONT};font-size:14px;font-weight:bold;color:{C["ink"]};">'
                            f'{_badge("NO CONFIRMADO", C["muted"])} {e(it.get("title"))}</div>' +
                            _p(it.get("summary", ""), 13) +
                            _p("Fuente: " if it.get("sources") else "", 12, C["muted"]) +
                            (f'<div style="font-family:{FONT};font-size:12px;">{_links(it["sources"])}</div>'
                             if it.get("sources") else "")))
    # Registro técnico
    logl = "<br>".join(e(x) for x in ctx["log_lines"])
    out.append(f'<tr><td style="padding:26px 24px 8px 24px;"><div style="border-top:1px solid {C["line"]};'
               f'padding-top:12px;font-family:{FONT};font-size:11px;line-height:1.6;color:{C["muted"]};">'
               f'<b>Registro de ejecución</b><br>{logl}</div></td></tr>')
    out.append(f'<tr><td style="padding:6px 24px 26px 24px;font-family:{FONT};font-size:11px;line-height:1.5;'
               f'color:{C["muted"]};">Este informe es contexto e identificación de riesgos, no una recomendación de '
               f'compra o venta. Los sesgos son interpretaciones condicionales. Verifica las cifras en las fuentes '
               f'enlazadas antes de operar. Sistema PREMARKET INTELLIGENCE v{e(ctx["version"])}.</td></tr>')
    pre = e(ex.get("overview", ""))[:180]
    # font-family se declara una vez en el contenedor (Gmail lo hereda) para no inflar el HTML
    body = "".join(out).replace(f"font-family:{FONT};", "")
    doc = (f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{e(ctx["subject"])}</title></head>'
           f'<body style="margin:0;padding:0;background:{C["bg"]};">'
           f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{pre}</div>'
           f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
           f'style="background:{C["bg"]};"><tr><td align="center" style="padding:12px 6px;">'
           f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
           f'style="max-width:700px;background:{C["card"]};border:1px solid {C["line"]};font-family:{FONT};'
           f'color:{C["ink"]};font-size:14px;line-height:1.5;">{body}</table>'
           f'</td></tr></table></body></html>')
    return wrap_lines(slim(re.sub(r">\s*\n\s*<", "><", doc)))  # conserva espacios entre etiquetas en línea


def slim(doc: str) -> str:
    """Quita estilos heredables y atributos por defecto: menos KB (Gmail recorta >102 KB) y
    menos texto que transcribir al conector de Gmail. El contenedor fija color/tamaño/interlineado."""
    head, sep, body = doc.partition('font-size:14px;line-height:1.5;">')
    for a, b in ((' role="presentation"', ""), (' border="0"', ""), (' align="left"', ""),
                 (f'color:{C["ink"]};', ""), ("line-height:1.35;", ""), ("line-height:1.5;", ""),
                 ("line-height:1.55;", ""), ("word-break:break-word;", ""), ("padding:6px 6px;", "padding:6px;"),
                 ("text-decoration:underline;", ""), ('<span style="">', "<span>"), (' style=""', ""),
                 ("font-size:14px;", "")):
        body = body.replace(a, b)
    body = body.replace(' style=""', "")
    body = re.sub(r"<span>([^<]*)</span>", r"\1", body)
    return head + sep + body


def wrap_lines(doc: str, maxlen: int = 900) -> str:
    """Saltos de línea entre etiquetas de bloque (inocuos en HTML) para que ninguna línea
    sea muy larga: así el agente puede leer y copiar el HTML íntegro al conector de Gmail."""
    doc = re.sub(r"(</tr>|</table>|<tr>|</div>)", r"\1\n", doc)
    out = []
    for line in doc.split("\n"):
        while len(line) > maxlen:
            cut = max(line.rfind("</td>", 0, maxlen), line.rfind("<br>", 0, maxlen),
                      line.rfind("</span>", 0, maxlen))
            if cut <= 0:
                cut = line.rfind("><", 0, maxlen)
            if cut <= 0:
                cut = line.find(" ", maxlen)  # espacio dentro de texto: también inocuo
                if cut < 0:
                    break
            cut += 1 if line[cut] in " >" else (line.index(">", cut) + 1 - cut)
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return "\n".join(x for x in out if x)


# ---------------------------------------------------------------- plain text
def render_text(ctx: dict) -> str:
    r, tri, d = ctx["report"], ctx["triage"], ctx["date"]
    L = []
    w = L.append
    w("PREMARKET INTELLIGENCE — S&P 500")
    w(fecha_larga(d))
    w(f"Generado: {ctx['generated_label']} | Corte: {ctx['cutoff_label']}")
    w("REPORTE PARCIAL: " + (r.get("partial_reason") or "investigación incompleta") if ctx["partial"]
      else "REPORTE COMPLETO")
    w("=" * 64)
    ex = r.get("executive_summary", {})
    w("\nI. RESUMEN EJECUTIVO\n" + ex.get("overview", "N/D"))
    for t, k in (("Alcistas", "bullish"), ("Bajistas", "bearish"), ("Incertidumbres", "uncertain")):
        w(f"\n{t}:")
        for i in ex.get(k, []) or ["—"]:
            w(f"  - {i}")
    w("\nII. TERMÓMETRO DE MERCADO")
    for m in ctx["market_rows"] or []:
        w(f"  {m.get('label')}: {m.get('value')} ({m.get('change', 'N/D')}) — {m.get('timestamp')} — "
          f"{m.get('source')} {m.get('url', '')}")
    if not ctx["market_rows"]:
        w("  Sin datos verificables.")
    for num, lvl, title in (("III", "CRÍTICO", "NOTICIAS CRÍTICAS"), ("IV", "ALTO", "ALTO IMPACTO"),
                            ("V", "MODERADO", "IMPACTO MODERADO")):
        w(f"\n{num}. {title}")
        items = tri["by_level"][lvl]
        if not items:
            w("  Sin noticias en este nivel.")
        for it in items:
            w(f"\n[{lvl}] {it.get('title')}")
            w(f"  {it.get('summary', '')}")
            w(f"  Por qué importa: {it.get('why_it_matters', '')}")
            w(f"  Sesgo: {it['bias']}. {it.get('bias_detail', '')}".rstrip())
            w(f"  Estado: {it['status']}{' — ' + it['update_note'] if it.get('update_note') else ''} | "
              f"Fecha: {it.get('event_time', 'N/D')}")
            w(f"  Confianza: hecho {it['confidence_fact']} / impacto {it['confidence_impact']}")
            for s in it.get("sources", []):
                w(f"  Fuente: {s.get('name')} — {s.get('url')}")
    w("\nVI. CALENDARIO ECONÓMICO")
    for c in ctx["calendar"].get("rows", []):
        w(f"  {c['time_et']} NY / {c['time_mx']} CDMX | {c['country']} | {c['event']} | {c['impact']} | "
          f"Ant {c['previous']} | Cons {c['consensus']} | Real {c['actual']} | {c['status']}")
    if not ctx["calendar"].get("rows"):
        w("  Calendario no disponible.")
    w("\nVII. CATALIZADORES A VIGILAR")
    for c in r.get("catalysts", []):
        w(f"  - {(c.get('time') + ' · ') if c.get('time') else ''}{c.get('title')}: {c.get('detail', '')}")
    w("\nVIII. CONCLUSIÓN ESTRATÉGICA")
    con = r.get("conclusion", {})
    for q, k in (("Descontado", "priced_in"), ("Qué podría cambiarlo", "could_change"),
                 ("Volatilidad", "volatility_focus"), ("Incertidumbres", "open_uncertainties")):
        w(f"  {q}: {con.get(k, 'N/D')}")
    if tri["unconfirmed"]:
        w("\nINFORMACIÓN NO CONFIRMADA (no tratar como hecho)")
        for it in tri["unconfirmed"]:
            w(f"  - {it.get('title')}: {it.get('summary', '')}")
    w("\nREGISTRO DE EJECUCIÓN")
    for x in ctx["log_lines"]:
        w(f"  {x}")
    w("\nContexto e identificación de riesgos; no es recomendación de compra o venta.")
    return "\n".join(L)
