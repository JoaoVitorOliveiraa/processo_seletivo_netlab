"""
Exportação dos resultados para CSV e JSON.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from .config import FIELDNAMES
from .models import Resultado

logger = logging.getLogger(__name__)


def _normalize(record: dict) -> dict:
    """
    Garante que o registro tenha exatamente as chaves de FIELDNAMES.
    Campos ausentes viram None — evita KeyError no csv.DictWriter.
    """
    return {k: record.get(k) for k in FIELDNAMES}


def save_json(data: list[Resultado], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [r.to_dict() if hasattr(r, "to_dict") else r for r in data]
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Salvos %d registros em %s", len(payload), path)


def save_csv(data: list[Resultado], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        # extrasaction="ignore" evita erro se algum dict tiver chave extra
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for record in data:
            d = record.to_dict() if hasattr(record, "to_dict") else record
            writer.writerow(_normalize(d))
    logger.info("Salvos %d registros em %s", len(data), path)