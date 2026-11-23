"""Pruebas obligatorias A–J (las que se pueden automatizar sin red).

G (envío real) y H (ejecución en la nube) se verifican en vivo y se registran
en TEST_LOG.md. Ejecutar:  python -m pytest -q tests
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import shutil
from pathlib import Path

import pytest

from pmi import calendar_nyse as cal
from pmi import cli, econ_calendar, mailer, news, timing

FIX = Path(__file__).parent / "fixtures"
UTC = dt.timezone.utc


def _ws(tmp_path, report=True, ff=True):
    w, o = tmp_path / "work", tmp_path / "out"
    w.mkdir()
    o.mkdir()
    if report:
        shutil.copy(FIX / "report_sample.json", w / "report.json")
    if ff:
        shutil.copy(FIX / "ff_week_sample.json", w / "ff_week.json")
    return w, o


# ---------------------------------------------------------------- A. EDT / EST
@pytest.mark.parametrize("day,utc_hour,mx_hour,tzname", [
    (dt.date(2026, 11, 24), 14, 8, "EST"),   # EST: 9:00 ET = 14:00 UTC = 08:00 CDMX
    (dt.date(2027, 3, 16), 13, 7, "EDT"),    # EDT: 9:00 ET = 13:00 UTC = 07:00 CDMX
    (dt.date(2027, 7, 7), 13, 7, "EDT"),
    (dt.date(2027, 12, 1), 14, 8, "EST"),
])
def test_A_send_target_edt_est(day, utc_hour, mx_hour, tzname):
    t = timing.at_et(day, "09:00")
    assert t.astimezone(UTC).hour == utc_hour
    assert timing.to_mx(t).hour == mx_hour
    assert t.tzname() == tzname
    s = timing.schedule_for(day)
    assert s["task_start"] < s["research_until"] < s["macro_release_check"] < s["info_cutoff"] < s["send_target"]
    assert s["send_target"] < timing.at_et(day, "09:00:01")


def test_A_phases():
    d = dt.date(2026, 11, 24)
    assert timing.phase(timing.at_et(d, "07:50"))["phase"] == "start"
    assert timing.phase(timing.at_et(d, "08:31:30"))["phase"] == "macro_release_check"
    assert timing.phase(timing.at_et(d, "08:58:10"))["phase"] == "info_cutoff"
    assert timing.phase(timing.at_et(d, "09:20"))["phase"] == "hard_deadline"


# ---------------------------------------------------------------- B. NYSE cerrado
@pytest.mark.parametrize("day,open_,reason", [
    ("2026-11-26", False, "FESTIVO"),            # Thanksgiving
    ("2026-11-28", False, "FIN_DE_SEMANA"),
    ("2026-12-25", False, "FESTIVO"),
    ("2027-03-26", False, "FESTIVO"),            # Good Friday
    ("2027-06-18", False, "FESTIVO"),            # Juneteenth observado
    ("2026-11-27", True, "CIERRE_ANTICIPADO"),   # abre: sí hay reporte
    ("2026-12-24", True, "CIERRE_ANTICIPADO"),
    ("2026-11-24", True, "SESION_REGULAR"),
    ("2028-01-03", True, "SESION_REGULAR"),      # 1-ene-2028 sábado: no se observa
])
def test_B_calendar(day, open_, reason):
    info = cal.session_info(dt.date.fromisoformat(day))
    assert info["open"] is open_ and info["reason"] == reason


def test_B_preflight_exit_codes(tmp_path):
    w, o = _ws(tmp_path)
    base = ["--work", str(w), "--out", str(o)]
    assert cli.main(base + ["--date", "2026-11-26", "--now", "2026-11-26T07:48", "preflight"]) == 10
    assert cli.main(base + ["--date", "2026-11-28", "--now", "2026-11-28T07:48", "preflight"]) == 10
    assert cli.main(base + ["--date", "2026-11-27", "--now", "2026-11-27T07:48", "preflight"]) == 0
    assert cli.main(base + ["--date", "2029-01-02", "preflight"]) == 20  # fuera de cobertura


def test_B_matches_exchange_calendars():
    xc = pytest.importorskip("exchange_calendars")
    import pandas as pd
    c = xc.get_calendar("XNYS", start="2025-12-01", end="2028-12-31")
    for d in pd.bdate_range("2026-01-01", "2028-12-31"):
        assert cal.is_trading_day(d.date()) == c.is_session(d), d
        if c.is_session(d):
            early = c.session_close(d).tz_convert("America/New_York").hour < 16
            assert (d.date().isoformat() in cal.EARLY_CLOSES) == early, d


# ---------------------------------------------------------------- C. validación de fuentes
def test_C_unverified_goes_to_unconfirmed():
    rep = json.loads((FIX / "report_sample.json").read_text(encoding="utf-8"))
    tri = news.triage(rep["news"])
    titles_unc = [x["title"] for x in tri["unconfirmed"]]
    assert any("Rumor" in t for t in titles_unc)
    confirmed = [x for lvl in tri["by_level"].values() for x in lvl]
    assert all(any(s.get("verified") for s in x["sources"]) for x in confirmed)


def test_C_missing_url_or_bad_scheme():
    items = [{"title": "Sin URL", "level": "ALTO", "sources": [{"name": "X", "verified": True}]},
             {"title": "Esquema raro", "level": "ALTO",
              "sources": [{"name": "X", "url": "javascript:alert(1)", "verified": True}]}]
    tri = news.triage(items)
    assert tri["counts"]["ALTO"] == 0 and tri["counts"]["no_confirmadas"] == 2


def test_C_single_source_critical_warns():
    item = {"title": "Algo crítico", "level": "CRÍTICO", "summary": "x " * 50, "why_it_matters": "y",
            "event_time": "08:00 ET", "sources": [{"name": "Blog", "url": "https://blog.example/x", "verified": True}]}
    tri = news.triage([item])
    assert any("corroboración" in w for w in tri["warnings"])


# ---------------------------------------------------------------- D. duplicados
def test_D_duplicates_merge():
    rep = json.loads((FIX / "report_sample.json").read_text(encoding="utf-8"))
    tri = news.triage(rep["news"])
    allc = [x for lvl in tri["by_level"].values() for x in lvl]
    assert len(allc) == 1, "las dos versiones de 'Empresa A' deben fusionarse"
    m = allc[0]
    assert m["level"] == "CRÍTICO"                       # conserva el nivel más alto
    assert len(m["sources"]) == 2                        # conserva ambos enlaces
    assert tri["merge_log"]


def test_D_same_url_merges_different_titles():
    a = {"title": "Fed holds rates", "level": "ALTO", "sources": [{"name": "R", "url": "https://www.x.com/a/", "verified": True}]}
    b = {"title": "Banco central sin cambios", "level": "MODERADO",
         "sources": [{"name": "R2", "url": "https://x.com/a?utm=1", "verified": True}]}
    out, log = news.dedupe([news.normalize(a), news.normalize(b)])
    assert len(out) == 1 and log


def test_D_live_blog_url_with_distinct_keys_not_merged():
    live = "https://finance.example.com/live/markets-today"
    a = {"title": "Nvidia restituye a su CEO", "event_key": "nvda", "level": "CRÍTICO",
         "sources": [{"name": "Live", "url": live, "verified": True}]}
    b = {"title": "El petróleo cae", "event_key": "oil", "level": "MODERADO",
         "sources": [{"name": "Live", "url": live, "verified": True}]}
    out, _ = news.dedupe([news.normalize(a), news.normalize(b)])
    assert len(out) == 2


def test_D_distinct_not_merged():
    a = {"title": "Nvidia supera estimaciones", "level": "ALTO", "sources": [{"name": "A", "url": "https://a.com/1", "verified": True}]}
    b = {"title": "OPEP recorta producción de petróleo", "level": "ALTO", "sources": [{"name": "B", "url": "https://b.com/2", "verified": True}]}
    out, _ = news.dedupe([news.normalize(a), news.normalize(b)])
    assert len(out) == 2


# ---------------------------------------------------------------- E. pendiente -> publicado
def test_E_pending_then_published(tmp_path):
    w, _ = _ws(tmp_path)
    day = dt.date(2026, 11, 24)
    before = econ_calendar.events_for_day(w / "ff_week.json", day, timing.at_et(day, "08:20"))
    claims = next(r for r in before["rows"] if r["event"] == "Unemployment Claims")
    assert claims["status"] == "PENDIENTE" and claims["actual"] == "N/D"
    after_no_data = econ_calendar.events_for_day(w / "ff_week.json", day, timing.at_et(day, "08:35"))
    c2 = next(r for r in after_no_data["rows"] if r["event"] == "Unemployment Claims")
    assert c2["status"] == "PUBLICADO · real N/D" and c2["actual"] == "N/D"   # nunca inventa
    upd = [{"match": "unemployment claims", "country": "USD", "actual": "231K", "source": "DOL",
            "url": "https://www.dol.gov/ui/data.pdf"}]
    after = econ_calendar.events_for_day(w / "ff_week.json", day, timing.at_et(day, "08:35"), upd)
    c3 = next(r for r in after["rows"] if r["event"] == "Unemployment Claims")
    assert c3["status"] == "PUBLICADO" and c3["actual"] == "231K"
    conf = next(r for r in after["rows"] if "Confidence" in r["event"])
    assert conf["status"] == "PENDIENTE"
    assert all(r["time_et_iso"].startswith("2026-11-24") for r in after["rows"])  # solo el día
    assert c3["time_mx"] == "07:30"


# ---------------------------------------------------------------- F. HTML / Gmail
def _build(tmp_path, report=None, now="2026-11-24T08:58:30"):
    w, o = _ws(tmp_path)
    if report is not None:
        (w / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    rc = cli.main(["--work", str(w), "--out", str(o), "--date", "2026-11-24", "--now", now, "build"])
    assert rc == 0
    return w, o


def test_F_html_gmail_basics(tmp_path):
    _, o = _build(tmp_path)
    html = (o / "report.html").read_text(encoding="utf-8")
    assert "<style" not in html.lower() and "<script" not in html.lower() and "<img" not in html.lower()
    for sec in ("Resumen ejecutivo", "Termómetro de mercado", "Noticias críticas", "Noticias de alto impacto",
                "Noticias de impacto moderado", "Calendario económico del día", "catalizadores a vigilar",
                "Conclusión estratégica", "Información no confirmada", "Registro de ejecución"):
        assert sec in html, sec
    for href in re.findall(r'href="([^"]*)"', html):
        assert href.startswith(("https://", "http://")), href
    assert 'name="viewport"' in html and "max-width:700px" in html
    assert "Sin timestamp" not in html   # indicador sin timestamp omitido
    b = json.loads((o / "build.json").read_text(encoding="utf-8"))
    assert b["subject"] == "PREMARKET | S&P 500 | 24-NOV-2026 | Inteligencia de Mercados"
    txt = (o / "report.txt").read_text(encoding="utf-8")
    assert "PREMARKET INTELLIGENCE" in txt and "<" not in txt.split("REGISTRO")[0].replace("<=", "")


def test_F_escaping_and_size_35_items(tmp_path):
    rep = json.loads((FIX / "report_sample.json").read_text(encoding="utf-8"))
    base = rep["news"][0]
    rep["news"] = []
    topics = ["petróleo", "Fed", "BCE", "Japón", "China", "aranceles", "Nvidia", "Apple", "bancos", "crédito",
              "empleo", "inflación", "PIB", "dólar", "oro", "cobre", "Microsoft", "Amazon", "Tesla", "Meta",
              "Alphabet", "Broadcom", "JPMorgan", "Exxon", "OPEP", "Taiwán", "Rusia", "Irán", "Treasury",
              "VIX", "Boeing", "UnitedHealth", "Walmart", "Costco", "Lilly"]
    for i, tpc in enumerate(topics):
        it = copy.deepcopy(base)
        it["title"] = f"Noticia {tpc} número {i} <b>sin html</b> & símbolos"
        it["event_key"] = f"k{i}"
        it["summary"] = " ".join(["palabra"] * 88)          # resúmenes largos (peor caso)
        it["why_it_matters"] = " ".join(["mecanismo"] * 35)
        it["level"] = ["CRÍTICO", "ALTO", "MODERADO"][i % 3]
        it["sources"] = [{"name": f"Fuente {i}", "url": f"https://example.com/{i}", "verified": True}]
        rep["news"].append(it)
    _, o = _build(tmp_path, rep)
    html = (o / "report.html").read_text(encoding="utf-8")
    assert "<b>sin html</b>" not in html and "&lt;b&gt;sin html&lt;/b&gt;" in html
    kb = len(html.encode()) / 1024
    b = json.loads((o / "build.json").read_text(encoding="utf-8"))
    assert sum(b["counts"][k] for k in ("CRÍTICO", "ALTO", "MODERADO")) == 35
    assert kb < 102, f"{kb:.0f} KB: Gmail recortaría el mensaje"


def test_F_partial_label(tmp_path):
    rep = json.loads((FIX / "report_sample.json").read_text(encoding="utf-8"))
    rep["partial"] = True
    rep["partial_reason"] = "Se alcanzó el límite de tiempo."
    _, o = _build(tmp_path, rep)
    assert "REPORTE PARCIAL" in (o / "report.html").read_text(encoding="utf-8")
    assert json.loads((o / "build.json").read_text(encoding="utf-8"))["subject"].endswith("| PARCIAL")


# ---------------------------------------------------------------- I. fallos
def test_I_calendar_source_down(tmp_path):
    w, o = _ws(tmp_path, ff=False)
    rc = cli.main(["--work", str(w), "--out", str(o), "--date", "2026-11-24", "--now", "2026-11-24T08:58", "build"])
    assert rc == 0
    html = (o / "report.html").read_text(encoding="utf-8")
    assert "Calendario no disponible" in html


def test_I_invalid_credentials(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    r = mailer.send_resend(to="a@b.co", subject="s", html="h", text="t", idem_key="k")
    assert r["ok"] is False and "RESEND_API_KEY" in r["error"]


def test_I_scheduler_delay():
    d = dt.date(2026, 11, 24)
    late = timing.phase(timing.at_et(d, "09:25"))
    assert late["phase"] == "hard_deadline" and late["minutes_to_send"] < 0
    past = timing.now_et() - dt.timedelta(minutes=5)
    assert mailer.wait_until(past) == 0.0  # objetivo ya pasado (programador retrasado): no espera


def test_I_no_duplicate_send(tmp_path, monkeypatch):
    w, o = _build(tmp_path)
    monkeypatch.setenv("PMI_RECIPIENT", "test@example.com")
    base = ["--work", str(w), "--out", str(o), "--date", "2026-11-24"]
    assert cli.main(base + ["send", "--backend", "gmail_connector"]) == 0
    assert cli.main(base + ["record-sent", "--provider-id", "abc"]) == 0
    assert mailer.marker_path(o, "2026-11-24", "report").exists()
    # un segundo intento se omite
    calls = []
    monkeypatch.setattr(mailer, "send_resend", lambda **k: calls.append(k) or {"ok": True})
    assert cli.main(base + ["send", "--backend", "resend"]) == 0
    assert calls == []


def test_E_addendum_only_verified(tmp_path):
    w, o = _ws(tmp_path)
    (w / "addendum.json").write_text(json.dumps({"cutoff_et": "2026-11-24T08:57:00", "news": [
        {"title": "Última hora verificada", "level": "CRÍTICO", "summary": "x " * 40, "why_it_matters": "y",
         "event_time": "08:55 ET", "sources": [{"name": "Fed", "url": "https://www.federalreserve.gov/x", "verified": True}]},
        {"title": "Rumor", "level": "ALTO", "sources": [{"name": "X", "url": "https://x.com/1"}]}]}), encoding="utf-8")
    assert cli.main(["--work", str(w), "--out", str(o), "--date", "2026-11-24", "addendum"]) == 0
    h = (o / "addendum.html").read_text(encoding="utf-8")
    assert "Última hora verificada" in h and "Rumor" not in h


# ---------------------------------------------------------------- J. próximos cambios de horario
def test_J_dst_transitions():
    # Próximas transiciones: 14-mar-2027 (inicia EDT) y 7-nov-2027 (inicia EST)
    fri = timing.at_et(dt.date(2027, 3, 12), "07:47")
    mon = timing.at_et(dt.date(2027, 3, 15), "07:47")
    assert (fri.astimezone(UTC).hour, fri.astimezone(UTC).minute) == (12, 47)
    assert (mon.astimezone(UTC).hour, mon.astimezone(UTC).minute) == (11, 47)
    assert timing.to_mx(fri).strftime("%H:%M") == "06:47" and timing.to_mx(mon).strftime("%H:%M") == "05:47"
    fri2 = timing.at_et(dt.date(2027, 11, 5), "09:00")
    mon2 = timing.at_et(dt.date(2027, 11, 8), "09:00")
    assert timing.to_mx(fri2).strftime("%H:%M") == "07:00"
    assert timing.to_mx(mon2).strftime("%H:%M") == "08:00"


# ---------------------------------------------------------------- G (simulado). Envío Resend
def test_G_resend_payload_and_idempotency(tmp_path, monkeypatch):
    w, o = _build(tmp_path)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_dummy")
    monkeypatch.setenv("PMI_RECIPIENT", "destino@example.com")
    sent = []

    def fake_post(url, payload, headers, timeout=30):
        sent.append((url, payload, headers))
        return 200, {"id": "email_123"}
    monkeypatch.setattr(mailer, "post_json", fake_post)
    base = ["--work", str(w), "--out", str(o), "--date", "2026-11-24"]
    assert cli.main(base + ["send", "--backend", "resend"]) == 0
    url, payload, headers = sent[0]
    assert url == "https://api.resend.com/emails"
    assert payload["to"] == ["destino@example.com"] and payload["html"].startswith("<!DOCTYPE html>")
    assert payload["text"] and payload["subject"].startswith("PREMARKET | S&P 500 | 24-NOV-2026")
    assert headers["Idempotency-Key"] == "pmi-2026-11-24-report"
    assert cli.main(base + ["send", "--backend", "resend"]) == 0   # segundo intento: omitido
    assert len(sent) == 1


def test_I_resend_auth_error_not_retried(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_bad")
    calls = []
    monkeypatch.setattr(mailer, "post_json", lambda *a, **k: calls.append(1) or (401, {"message": "API key is invalid"}))
    r = mailer.send_resend(to="a@b.co", subject="s", html="h", text="t", idem_key="k")
    assert r["ok"] is False and r["http"] == 401 and len(calls) == 1


def test_I_resend_transient_retry(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_ok")
    seq = iter([(503, {}), (200, {"id": "e1"})])
    monkeypatch.setattr(mailer, "post_json", lambda *a, **k: next(seq))
    monkeypatch.setattr(mailer.time, "sleep", lambda s: None)
    r = mailer.send_resend(to="a@b.co", subject="s", html="h", text="t", idem_key="k")
    assert r["ok"] and r["provider_id"] == "e1"
