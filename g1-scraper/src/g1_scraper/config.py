"""
Configurações centralizadas do projeto.

Seletores CSS extraídos do HTML REAL do G1 (inspeção manual via DevTools).
Fonte: https://g1.globo.com/busca/?q=lgpd
"""
from __future__ import annotations

SITE_ROOT = "https://g1.globo.com"
SEARCH_URL = f"{SITE_ROOT}/busca/"
ROBOTS_URL = f"{SITE_ROOT}/robots.txt"

TERMO_BUSCA = "lgpd"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Seletores CSS confirmados contra o HTML real do G1
SELECTORS = {
    # Cada resultado é um <li id="search-result-item-N"> com classes widget--*
    # Vídeos usam <li class="video-widget--info"> — não têm o mesmo id
    "container": "li[id^='search-result-item-'], li.video-widget--info",

    # Título: <div class="widget--info__title">
    "title_text": "div.widget--info__title, div.video-widget--info__title",

    # Resumo: <p class="widget--info__description">
    "summary": "p.widget--info__description, p.video-widget--info__description",

    # Veículo: <div class="widget--info__header">
    "source": "div.widget--info__header, div.video-widget--info__header",

    # Data: <div class="widget--info__meta"><span>data</span></div>
    "meta": "div.widget--info__meta, div.video-widget--info__meta",

    # Marcador de publicidade (opcional)
    "ad_label": "div.widget--info__ad-label",
}

MAX_PAGES = 10
SLEEP_INTERVAL = 1.5
RETRIES = 3
BACKOFF_BASE = 2.0
TIMEOUT = 15

FIELDNAMES = [
    "titulo",
    "url",
    "resumo",
    "veiculo",
    "data_publicacao_raw",
    "data_publicacao_iso",
    "publicitario",
    "pagina",
    "termo_busca",
    "coletado_em",
]