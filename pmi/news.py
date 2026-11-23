"""Modelo de noticias: validación de fiabilidad, deduplicación y orden.

Reglas aplicadas (sección 5 y 6 del documento de requisitos):
- Una noticia confirmada necesita >=1 fuente con nombre, URL http(s) y
  `verified: true` (el agente abrió la página y confirmó que corresponde).
- Estado "No confirmado" o sin fuente verificada -> sección "Información no confirmada"
  (si es relevante) y nunca en el bloque de noticias confirmadas.
- Duplicados (misma URL, mismo `event_key` o títulos muy similares) se fusionan
  conservando todos los enlaces y el nivel más alto.
- Orden: nivel (CRÍTICO > ALTO > MODERADO), luego urgencia, luego hora.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

LEVELS = {"CRÍTICO": 0, "CRITICO": 0, "ALTO": 1, "MODERADO": 2}
CANON_LEVEL = {"CRITICO": "CRÍTICO"}
BIASES = {"alcista": "Alcista", "bajista": "Bajista", "mixto": "Mixto / incierto",
          "incierto": "Mixto / incierto", "mixto / incierto": "Mixto / incierto",
          "mixto o incierto": "Mixto / incierto"}
STATUSES = {"confirmado": "Confirmado", "programado": "Programado",
            "actualizado": "Actualizado", "no confirmado": "No confirmado"}
CONF = {"alta": "Alta", "media": "Media", "limitada": "Limitada", "baja": "Limitada"}
OFFICIAL_HINTS = ("federalreserve.gov", "bls.gov", "bea.gov", "treasury.gov", "sec.gov",
                  "nyse.com", "ecb.europa.eu", "boj.or.jp", "bankofengland.co.uk",
                  "whitehouse.gov", "ustr.gov", "commerce.gov", "census.gov", "dol.gov",
                  "eia.gov", "imf.org", "investor.", "ir.", "/investor", "newsroom")
STOP = set("de la el los las un una y o en a del al por para con que se su sus es the of "
           "to and in on for at as is are by with from s p 500 sp".split())


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokens(text: str) -> set[str]:
    t = _strip_accents((text or "").lower())
    # raíz ligera (5 caracteres) para que "supera"/"superar", "recorte"/"recortes" coincidan
    return {w[:5] for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and len(w) > 1}


def canon_url(u: str) -> str:
    try:
        p = urlsplit(u.strip())
        return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."),
                           p.path.rstrip("/"), "", ""))
    except Exception:  # noqa: BLE001
        return u


def similarity(a: dict, b: dict) -> float:
    ta, tb = tokens(a.get("title", "")), tokens(b.get("title", ""))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_official(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in OFFICIAL_HINTS) or u.endswith(".gov") or ".gov/" in u


def _valid_source(s: dict) -> bool:
    return bool(s.get("name")) and str(s.get("url", "")).startswith(("http://", "https://"))


def normalize(item: dict) -> dict:
    it = dict(item)
    lvl = str(it.get("level", "MODERADO")).upper().strip()
    it["level"] = CANON_LEVEL.get(lvl, lvl if lvl in LEVELS else "MODERADO")
    it["bias"] = BIASES.get(str(it.get("bias", "")).lower().strip(), "Mixto / incierto")
    it["status"] = STATUSES.get(str(it.get("status", "")).lower().strip(), "Confirmado")
    it["confidence_fact"] = CONF.get(str(it.get("confidence_fact", "")).lower(), "Media")
    it["confidence_impact"] = CONF.get(str(it.get("confidence_impact", "")).lower(), "Media")
    it["sources"] = [dict(s) for s in it.get("sources", []) if isinstance(s, dict)]
    it.setdefault("urgency", 3)
    return it


def merge(a: dict, b: dict) -> dict:
    """Fusiona b dentro de a (a se conserva como noticia principal)."""
    out = dict(a)
    if LEVELS[b["level"]] < LEVELS[a["level"]]:
        out["level"] = b["level"]
    seen = {canon_url(s["url"]) for s in a["sources"] if s.get("url")}
    out["sources"] = list(a["sources"]) + [s for s in b["sources"]
                                            if canon_url(s.get("url", "")) not in seen]
    if len(b.get("summary", "")) > len(a.get("summary", "")):
        out["summary"] = b["summary"]
    out["urgency"] = min(a.get("urgency", 3), b.get("urgency", 3))
    out["merged_count"] = a.get("merged_count", 1) + b.get("merged_count", 1)
    for k in ("why_it_matters", "bias_detail", "update_note", "event_time", "published_time"):
        if not out.get(k) and b.get(k):
            out[k] = b[k]
    return out


def dedupe(items: list[dict], threshold: float = 0.6) -> tuple[list[dict], list[str]]:
    kept: list[dict] = []
    log: list[str] = []
    for it in items:
        target = None
        urls = {canon_url(s["url"]) for s in it["sources"] if s.get("url")}
        for k in kept:
            kurls = {canon_url(s["url"]) for s in k["sources"] if s.get("url")}
            ka, kb = it.get("event_key"), k.get("event_key")
            if ka and kb:  # claves explícitas mandan: iguales => fusión, distintas => nunca
                # (una URL compartida no basta: los blogs en vivo cubren varias noticias)
                if ka == kb:
                    target = k
                    break
                continue
            if (urls & kurls) or similarity(it, k) >= threshold:
                target = k
                break
        if target is None:
            kept.append(it)
        else:
            idx = kept.index(target)
            kept[idx] = merge(target, it)
            log.append(f"Fusionada: «{it.get('title')}» → «{target.get('title')}»")
    return kept, log


def triage(items: list[dict], unconfirmed_in: list[dict] | None = None) -> dict:
    """Valida, separa confirmadas/no confirmadas, fusiona y ordena."""
    confirmed, unconfirmed, warnings = [], [], []
    for raw in items:
        it = normalize(raw)
        srcs = [s for s in it["sources"] if _valid_source(s)]
        verified = [s for s in srcs if s.get("verified") is True]
        if it["status"] == "No confirmado" or not verified:
            reason = "estado No confirmado" if it["status"] == "No confirmado" \
                else "sin fuente con enlace verificado"
            it["status"] = "No confirmado"
            unconfirmed.append(it)
            warnings.append(f"Movida a 'no confirmada' ({reason}): «{it.get('title')}»")
            continue
        it["sources"] = srcs
        if it["level"] == "CRÍTICO" and len(verified) < 2 and not any(is_official(s["url"]) for s in verified):
            warnings.append(f"CRÍTICO con una sola fuente no oficial; buscar corroboración: «{it.get('title')}»")
        words = len(str(it.get("summary", "")).split())
        if words < 25 or words > 140:
            warnings.append(f"Resumen de {words} palabras (objetivo 40–90): «{it.get('title')}»")
        for f in ("title", "summary", "why_it_matters"):
            if not it.get(f):
                warnings.append(f"Falta '{f}' en «{it.get('title', '?')}»")
        if not (it.get("event_time") or it.get("published_time")):
            warnings.append(f"Sin fecha/hora: «{it.get('title')}»")
        confirmed.append(it)
    for raw in unconfirmed_in or []:
        it = normalize(raw)
        it["status"] = "No confirmado"
        unconfirmed.append(it)
    confirmed, mlog = dedupe(confirmed)
    unconfirmed, ulog = dedupe(unconfirmed)
    key = lambda x: (LEVELS[x["level"]], x.get("urgency", 3))  # noqa: E731
    confirmed.sort(key=key)
    unconfirmed.sort(key=key)
    by = {lvl: [x for x in confirmed if x["level"] == lvl] for lvl in ("CRÍTICO", "ALTO", "MODERADO")}
    return {"by_level": by, "unconfirmed": unconfirmed, "warnings": warnings,
            "merge_log": mlog + ulog, "counts": {k: len(v) for k, v in by.items()} |
            {"no_confirmadas": len(unconfirmed)}}
