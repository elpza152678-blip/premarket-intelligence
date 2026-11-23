"""HTTP mínimo con reintentos (solo stdlib; respeta HTTPS_PROXY y CA del entorno)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

UA = f"Python-urllib/{__import__('sys').version_info[0]}.{__import__('sys').version_info[1]}"  # FRED bloquea UAs personalizados


class FetchError(RuntimeError):
    pass


def get(url: str, *, timeout: float = 20, retries: int = 2, backoff: float = 5,
        headers: dict | None = None, accept_status=(200,)) -> tuple[int, bytes]:
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if r.status in accept_status:
                    return r.status, body
                last = FetchError(f"HTTP {r.status} {url}")
        except urllib.error.HTTPError as e:
            last = FetchError(f"HTTP {e.code} {url}")
            if e.code in (401, 403, 404):
                break  # no tiene sentido reintentar
        except Exception as e:  # timeouts, DNS, reset
            last = FetchError(f"{type(e).__name__}: {e} ({url})")
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    raise last or FetchError(url)


# Resend (Cloudflare) rechaza con 403 el agente genérico de Python; FRED rechaza los personalizados.
POST_UA = "premarket-intelligence/1.0"


def post_json(url: str, payload: dict, headers: dict, timeout: float = 30) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": POST_UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            body = {"raw": "unparseable"}
        return e.code, body
