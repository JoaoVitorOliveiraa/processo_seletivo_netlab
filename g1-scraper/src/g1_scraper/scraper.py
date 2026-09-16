"""
Orquestração da coleta: paginação, deduplicação e sleep entre requisições.
"""

from __future__ import annotations

import logging
import time
from .client import can_fetch, fetch_page
from .config import MAX_PAGES, SEARCH_URL, SLEEP_INTERVAL
from .models import Resultado
from .parser import parse_page

logger = logging.getLogger(__name__)


def collect(
    termo: str,
    max_pages: int = MAX_PAGES,
    sleep_interval: float = SLEEP_INTERVAL,
) -> list[Resultado]:
    """
    Coleta todas as páginas de resultados para um termo, com deduplicação.
    A deduplicação usa a chave (url, titulo) — não só URL — para preservar
    atualizações legítimas de uma mesma notícia.

    Encerra automaticamente quando:
    - atinge max_pages;
    - uma página retorna None (redirecionamento ou erro);
    - uma página não traz nenhum resultado novo.
    """
    
    seen_keys: set[tuple[str, str]] = set()
    all_results: list[Resultado] = []

    # Respeita robots.txt antes de qualquer coisa
    if not can_fetch(SEARCH_URL):
        logger.error("robots.txt proíbe a coleta de %s. Abortando.", SEARCH_URL)
        return []

    for page in range(1, max_pages + 1):
    # Página 1 usa URL "limpa" (sem parâmetro page).
    # Páginas 2+ usam ?q=...&page=N.
    # O G1 rejeita ?page=1 com uma página vazia.
        if page == 1:
            url = f"{SEARCH_URL}?q={termo}"
        else:
            url = f"{SEARCH_URL}?q={termo}&page={page}"

        logger.info("Coletando página %d: %s", page, url)

        if not can_fetch(url):
            logger.warning("robots.txt proíbe %s. Pulando.", url)
            continue

        html = fetch_page(url)
        if html is None:
            logger.info("Encerrando paginação na página %d.", page)
            break

        page_results = parse_page(html, page, termo)

        # Filtra duplicados
        new_results = []
        for r in page_results:
            key = (r.url, r.titulo)
            if key not in seen_keys:
                seen_keys.add(key)
                new_results.append(r)

        if not new_results:
            logger.info("Nenhum resultado novo na página %d. Encerrando.", page)
            break

        all_results.extend(new_results)
        logger.info(
            "Página %d: %d novos (total: %d).",
            page, len(new_results), len(all_results),
        )

        # Pausa entre requisições (etiqueta para com o servidor)
        time.sleep(sleep_interval)

    return all_results