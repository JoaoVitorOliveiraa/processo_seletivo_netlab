"""
Camada HTTP: baixa páginas do G1 usando Playwright e respeita robots.txt.

O G1 renderiza a busca via JavaScript E usa um botão "Veja mais" para
paginação (não há parâmetro de URL para navegar entre páginas — testamos
`page`, `from`, `offset`, `start`, `p`, `pagina` e todos são ignorados).

Solução: o Playwright abre a página, clica no botão "Veja mais" N vezes,
e devolve o HTML acumulado. O parsing continua com Beautiful Soup.
"""
from __future__ import annotations

import logging
import time
from urllib.robotparser import RobotFileParser

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from .config import BACKOFF_BASE, HEADERS, RETRIES, ROBOTS_URL, TIMEOUT

logger = logging.getLogger(__name__)

_robots_cache: RobotFileParser | None = None

# Seletor do botão "Veja mais"
SELETOR_BOTAO = "button.pagination__load-more"

# Seletor dos cards
SELETOR_CARDS = "li[id^='search-result-item-']"


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def _get_robots() -> RobotFileParser:
    """Lê o robots.txt uma única vez e mantém em cache."""
    global _robots_cache
    if _robots_cache is not None:
        return _robots_cache

    rp = RobotFileParser()
    rp.set_url(ROBOTS_URL)

    try:
        resp = requests.get(ROBOTS_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        rp.parse(resp.text.splitlines())
        logger.info("robots.txt carregado com sucesso.")
    except Exception as e:
        logger.warning("Falha ao ler robots.txt (%s). Modo permissivo.", e)
        rp.parse(["User-agent: *", "Disallow:"])

    _robots_cache = rp
    return _robots_cache


def can_fetch(url: str, user_agent: str = "*") -> bool:
    """Consulta o robots.txt. Permissivo em caso de erro."""
    try:
        return _get_robots().can_fetch(user_agent, url)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Renderização com Playwright
# ---------------------------------------------------------------------------

def _render_with_pagination(url: str, pages: int) -> str | None:
    """
    Abre a URL, clica em "Veja mais" (pages - 1) vezes, e devolve o HTML.

    Aguarda novos cards usando o ID sequencial (`#search-result-item-N`)
    em vez de `wait_for_function` — evita o conflito de aspas simples no
    seletor CSS que quebrava o JavaScript interno do Playwright.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="pt-BR",
            )
            page = context.new_page()

            # Bloqueia recursos pesados que não afetam o parser
            page.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp,css,woff,woff2,ttf}",
                lambda route: route.abort(),
            )

            try:
                page.goto(url, timeout=TIMEOUT * 1000, wait_until="domcontentloaded")

                # Aguarda os primeiros cards
                page.wait_for_selector(SELETOR_CARDS, timeout=15_000)
                total_inicial = len(page.query_selector_all(SELETOR_CARDS))
                logger.info("Página 1 carregada: %d cards.", total_inicial)

                # Clica em "Veja mais" (pages - 1) vezes
                for i in range(pages - 1):
                    antes = len(page.query_selector_all(SELETOR_CARDS))

                    botao = page.query_selector(SELETOR_BOTAO)
                    if not botao:
                        logger.info(
                            "Botão 'Veja mais' não encontrado — fim dos resultados "
                            "após %d página(s).",
                            i + 1,
                        )
                        break

                    botao.scroll_into_view_if_needed()
                    botao.click()
                    logger.debug("Clique %d em 'Veja mais' (antes: %d cards).", i + 1, antes)

                    # Espera o card de número (antes + 1) aparecer.
                    # Usar o ID sequencial evita interpolar CSS no JavaScript.
                    try:
                        page.wait_for_selector(
                            f"li#search-result-item-{antes + 1}",
                            timeout=10_000,
                        )
                        depois = len(page.query_selector_all(SELETOR_CARDS))
                        logger.info(
                            "Página %d carregada: %d → %d cards.",
                            i + 2, antes, depois,
                        )
                    except PlaywrightTimeout:
                        logger.warning(
                            "Timeout aguardando mais cards após o clique %d. "
                            "Parando paginação.",
                            i + 1,
                        )
                        break

                return page.content()

            except PlaywrightTimeout:
                logger.warning("Timeout aguardando cards iniciais em %s.", url)
                return page.content()

            finally:
                context.close()
                browser.close()

    except Exception as e:
        logger.error("Falha no Playwright em %s: %s", url, e)
        return None

# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def fetch_page(url: str, pages: int = 1) -> str | None:
    """
    Baixa o HTML renderizado de uma URL do G1, com paginação via clique.

    Parâmetros:
        url:   URL de busca (ex.: https://g1.globo.com/busca/?q=lgpd)
        pages: Quantas vezes considerar a paginação. `pages=1` devolve
               só a primeira leva; `pages=3` clica em "Veja mais" 2 vezes,
               acumulando ~30 cards.

    Retorna:
        str  → HTML renderizado com todos os cards acumulados.
        None → em caso de erro persistente.
    """
    logger.info("Coletando %s (pages=%d)", url, pages)
    return _render_with_pagination(url, pages)