"""
Camada HTTP: baixa páginas, trata erros e respeita robots.txt.

Usa Playwright (navegador headless) porque a página de busca do G1 é
renderizada via JavaScript — o HTML inicial retornado por `requests`
não contém os cards de resultado. O Playwright executa o JS e devolve
o DOM já renderizado, que é então parseado com Beautiful Soup.

O `robots.txt` continua sendo lido com `requests` (arquivo estático,
não precisa de JS). O fallback é permissivo e explícito.
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


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def _get_robots() -> RobotFileParser:
    """
    Lê o robots.txt uma única vez e mantém em cache.

    Usa `requests` porque o G1 serve o arquivo com Content-Encoding: gzip,
    e o `RobotFileParser.read()` nativo não descomprime.
    """
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
        # Fallback explícito e permissivo — nunca um parser vazio,
        # que bloquearia tudo silenciosamente.
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

def _render_with_playwright(url: str) -> str | None:
    """
    Abre a URL num Chromium headless e devolve o HTML após o JS rodar.

    Aguarda explicitamente pelos cards (`li[id^='search-result-item-']`)
    antes de capturar o HTML — sem isso, o snapshot pega a página no
    meio do carregamento e o parser encontraria zero resultados.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="pt-BR",
            )
            page = context.new_page()

            try:
                page.goto(url, timeout=TIMEOUT * 1000, wait_until="domcontentloaded")

                # Bloqueia imagens/CSS/fonts — não são necessários para o parser
                # e aceleram o carregamento.
                page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,webp,css,woff,woff2,ttf}",
                    lambda route: route.abort(),
                )

                # Aguarda os cards aparecerem.
                page.wait_for_selector(
                    "li[id^='search-result-item-']",
                    timeout=15_000,
                )
                return page.content()

            except PlaywrightTimeout:
                # Pode ser fim de paginação ou layout mudado.
                # Devolve o HTML — o parser decide o que fazer.
                logger.warning("Timeout aguardando cards em %s.", url)
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

def fetch_page(
    url: str,
    retries: int = RETRIES,
    backoff: float = BACKOFF_BASE,
) -> str | None:
    """
    Baixa o HTML renderizado de uma URL, com retentativas e backoff.

    Retorna:
        str  → HTML já com o resultado do JavaScript (os cards existem).
        None → se todas as tentativas falharem ou houver redirecionamento
               para a página 1 (sinal de fim da paginação).
    """
    for attempt in range(1, retries + 1):
        try:
            # Detecta redirecionamentos antes de abrir o navegador
            # (o G1 manda de volta para page=1 quando se excede o limite).
            resp = requests.head(
                url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False
            )

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "?")
                logger.info("Redirecionamento em %s → %s. Fim da paginação.", url, location)
                return None

            html = _render_with_playwright(url)
            if html:
                return html

        except requests.Timeout:
            logger.warning("Timeout (tentativa %d/%d) em %s", attempt, retries, url)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            logger.error("HTTP %s em %s", status, url)
            if status is not None and 400 <= status < 500:
                return None
        except requests.RequestException as e:
            logger.error("Erro de conexão em %s: %s", url, e)

        if attempt < retries:
            time.sleep(backoff ** attempt)

    logger.error("Falha definitiva ao baixar %s após %d tentativas.", url, retries)
    return None