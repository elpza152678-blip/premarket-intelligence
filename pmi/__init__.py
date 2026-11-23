"""PREMARKET INTELLIGENCE — S&P 500.

Paquete con la parte determinística del sistema: calendario NYSE, reloj,
fuentes de datos, validación/deduplicación de noticias, render y envío.
La investigación y el análisis los realiza el agente siguiendo RUNBOOK.md.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
__version__ = "1.0.0"


def load_config() -> dict:
    with open(ROOT / "config.json", encoding="utf-8") as fh:
        return json.load(fh)
