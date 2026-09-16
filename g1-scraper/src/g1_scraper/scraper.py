"""
Orquestração da coleta: dispara o fetch paginado e aplica deduplicação.
"""

from __future__ import annotations

import logging

from .client import can_fetch, fetch_page
from .config import MAX_PAGES, SEARCH_URL
from .models import Resultado
from .parser import parse_page

logger = logging.getLogger(__name__)


def collect(
    termo: str,
    max_pages: int = MAX_PAGES,
) -> list[Resultado]:
    """
    Coleta os resultados da busca pelo termo informado.

    A paginação é feita clicando em "Veja mais" no navegador
    (o G1 não expõe mais paginação via URL). O parâmetro `max_pages`
    define quantas vezes o botão é clicado.
    """
    # Monta a URL (a página 1 é a URL "limpa"; a paginação é feita no browser)
    url = f"{SEARCH_URL}?q={termo}"

    # Respeita robots.txt
    if not can_fetch(url):
        logger.error("robots.txt proíbe a coleta de %s. Abortando.", url)
        return []

    # Baixa o HTML com todas as páginas acumuladas
    html = fetch_page(url, pages=max_pages)
    if html is None:
        logger.error("Falha ao baixar %s.", url)
        return []

    # Parseia — todos os cards vêm em um único HTML agora
    results = parse_page(html, page_num=1, termo=termo)

    # Deduplica (o G1 pode repetir entre cliques do "Veja mais")
    seen: set[tuple[str, str]] = set()
    unique: list[Resultado] = []
    for r in results:
        key = (r.url, r.titulo)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(
        "Coleta concluída: %d resultados únicos (%d brutos).",
        len(unique), len(results),
    )
    return unique