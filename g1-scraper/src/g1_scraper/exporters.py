"""
Exportação dos dados coletados em JSON e CSV.
Usa apenas a biblioteca padrão. Aceita `Resultado` ou `dict`.
Cria o diretório de saída automaticamente.
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
    """Garante que o registro tenha exatamente as chaves de FIELDNAMES."""
    return {k: record.get(k) for k in FIELDNAMES}


def save_json(data: list[Resultado], path: str | Path) -> None:
    """Salva os resultados em JSON (UTF-8, indentado)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Aceita Resultado (via .to_dict) ou dict direto
    payload = [r.to_dict() if hasattr(r, "to_dict") else r for r in data]

    with path.open("w", encoding="utf-8") as f:
        # ensure_ascii=False preserva acentos; indent=2 facilita leitura
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info("Salvos %d registros em %s", len(payload), path)


def save_csv(data: list[Resultado], path: str | Path) -> None:
    """Salva os resultados em CSV (UTF-8, com cabeçalho)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # newline="" evita linhas duplicadas no Windows (exigência do módulo csv)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES,
            extrasaction="ignore",  # ignora chaves fora do schema
        )
        writer.writeheader()

        for record in data:
            d = record.to_dict() if hasattr(record, "to_dict") else record
            writer.writerow(_normalize(d))  # padroniza ordem e campos

    logger.info("Salvos %d registros em %s", len(data), path)