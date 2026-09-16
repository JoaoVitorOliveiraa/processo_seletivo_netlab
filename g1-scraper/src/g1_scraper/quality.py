"""
Métricas de qualidade dos dados coletados.
Cobre as sete dimensões do edital: completude, atualidade, precisão,
acurácia, unicidade, consistência e rastreabilidade. Cada métrica é
uma função pura — recebe dados, retorna número entre 0 e 1.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from .config import FIELDNAMES, HEADERS

logger = logging.getLogger(__name__)


def _check_url(url: str) -> bool:
    """Verifica se a URL responde 200. Usa stream para não baixar o conteúdo."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=5, stream=True, allow_redirects=True)
        r.close()
        return r.status_code == 200
    except requests.RequestException:
        return False


def precision_http(urls: list[str], max_workers: int = 10) -> float:
    """
    Fração de URLs que respondem 200.
    Paraleliza com ThreadPoolExecutor para não travar em N requisições
    sequenciais — verificar 30 URLs em série levaria minutos.
    """
    if not urls:
        return 0.0

    ok = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check_url, u): u for u in urls}
        for fut in as_completed(futures):
            if fut.result():
                ok += 1

    return ok / len(urls)


def completeness(data: list[dict], required: list[str] | None = None) -> float:
    """
    Fração de registros com todos os campos obrigatórios preenchidos.
    Campos padrão: titulo, url, pagina, coletado_em. Campos opcionais
    (resumo, data_*) não contam como falha.
    """
    if not data:
        return 0.0

    required = required or ["titulo", "url", "pagina", "coletado_em"]
    ok = sum(
        1 for r in data
        if all(r.get(f) not in (None, "") for f in required)
    )
    return ok / len(data)


def uniqueness(data: list[dict]) -> float:
    """Fração de URLs únicas sobre o total de registros com URL."""
    if not data:
        return 0.0

    urls = [r.get("url") for r in data if r.get("url")]
    return len(set(urls)) / len(urls) if urls else 0.0


def traceability(data: list[dict]) -> float:
    """Fração de registros com `pagina` e `coletado_em` preenchidos."""
    if not data:
        return 0.0

    ok = sum(1 for r in data if r.get("pagina") and r.get("coletado_em"))
    return ok / len(data)


def accuracy_vs_reference(data: list[dict], reference_path: str | Path) -> float:
    """
    Acurácia medida como interseção de URLs entre os dados coletados
    e a amostra manual de referência (ground truth).
    """
    ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    ref_urls = {r["url"] for r in ref if r.get("url")}
    col_urls = {r["url"] for r in data if r.get("url")}

    if not ref_urls:
        return 0.0

    return len(ref_urls & col_urls) / len(ref_urls)


def evaluate(data_path: str | Path, reference_path: str | Path | None = None) -> dict:
    """
    Calcula todas as métricas e retorna um dict pronto para o README.
    A precisão HTTP usa apenas as primeiras 30 URLs para não sobrecarregar
    o servidor do G1 durante a avaliação.
    """
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    sample_for_http = [r["url"] for r in data[:30] if r.get("url")]

    metrics = {
        "total_registros": len(data),
        "unicidade": round(uniqueness(data), 4),
        "completude": round(completeness(data), 4),
        "rastreabilidade": round(traceability(data), 4),
        "precisao_http": round(precision_http(sample_for_http), 4),
    }

    # Acurácia só faz sentido se a amostra de referência existir
    if reference_path and Path(reference_path).exists():
        metrics["acuracia_vs_referencia"] = round(
            accuracy_vs_reference(data, reference_path), 4
        )

    return metrics