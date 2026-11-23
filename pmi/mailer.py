"""Envío del correo.

Backends:
- resend: API HTTPS de Resend. Clave en la variable de entorno RESEND_API_KEY
  (nunca en el código). Usa Idempotency-Key para impedir duplicados (24 h).
- gmail_connector: el envío lo hace el agente con la herramienta send_message del
  conector de Gmail (OAuth). Python prepara `out/send_request.json` y el agente,
  tras enviar, registra el resultado con `cli record-sent`.

El destinatario se toma de --to o de la variable PMI_RECIPIENT (no está en el repo).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

from . import load_config
from .httpget import post_json
from .timing import ET, now_et

RESEND_URL = "https://api.resend.com/emails"


def wait_until(target: dt.datetime, max_wait_s: float = 20 * 60) -> float:
    """Duerme hasta `target` (ET) si es futuro. Devuelve segundos esperados."""
    delta = (target - now_et()).total_seconds()
    if delta <= 0:
        return 0.0
    delta = min(delta, max_wait_s)
    time.sleep(delta)
    return delta


def marker_path(out: Path, day: str, kind: str) -> Path:
    return out / f"SENT_{day}_{kind}.json"


def send_resend(*, to: str, subject: str, html: str, text: str, idem_key: str,
                deadline: dt.datetime | None = None, attempts: int = 4) -> dict:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "RESEND_API_KEY no configurada", "retryable": False}
    payload = {"from": load_config()["email"]["resend_from"], "to": [to], "subject": subject,
               "html": html, "text": text}
    headers = {"Authorization": f"Bearer {key}", "Idempotency-Key": idem_key}
    last = {}
    for i in range(attempts):
        status, body = post_json(RESEND_URL, payload, headers)
        if status == 200 and body.get("id"):
            return {"ok": True, "backend": "resend", "provider_id": body["id"], "http": status}
        if status == 409:  # misma clave de idempotencia ya usada: no reenviar
            return {"ok": True, "backend": "resend", "duplicate_prevented": True, "http": status,
                    "detail": body}
        last = {"ok": False, "http": status, "detail": body,
                "retryable": status == 429 or status >= 500}
        if status in (401, 403, 422) or not last["retryable"]:
            break
        if deadline and now_et() > deadline:
            break
        time.sleep(5 * (2 ** i))
    last.setdefault("backend", "resend")
    return last


def prepare_connector_request(out: Path, *, to: str, subject: str, html_path: Path,
                              text_path: Path, kind: str) -> Path:
    req = {"backend": "gmail_connector", "to": to, "subject": subject,
           "html_path": str(html_path), "text_path": str(text_path), "kind": kind,
           "prepared_at_et": now_et().isoformat(timespec="seconds"),
           "instructions": "Llamar a la herramienta send_message del conector Gmail con to/subject y "
                           "el contenido HTML del archivo html_path (texto plano de text_path si la "
                           "herramienta lo admite). Luego: python -m pmi.cli record-sent --backend "
                           "gmail_connector --provider-id <id devuelto>."}
    p = out / "send_request.json"
    p.write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def recipient(arg: str | None) -> str:
    to = (arg or os.environ.get(load_config().get("recipient_env", "PMI_RECIPIENT"), "")).strip()
    if not to or "@" not in to:
        raise SystemExit("Destinatario no definido: usa --to o la variable PMI_RECIPIENT")
    return to
