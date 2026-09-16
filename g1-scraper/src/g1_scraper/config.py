"""
Configurações centralizadas do projeto.
Todos os "números mágicos", URLs e seletores vivem aqui. Se o G1 mudar
o HTML, altera-se apenas este arquivo — o resto do código não precisa
ser tocado.
Obs: os seletores abaixo foram baseados em inspeção manual.
Antes de rodar, verifique abrindo https://g1.globo.com/busca/?q=lgpd no
navegador (F12 → Elements) e confirmando que as classes ainda existem.
"""

from __future__ import annotations                    # Ativa o modo de anotações postergadas.

# ---------------------------------------------------------------------------
# URLs do G1
# ---------------------------------------------------------------------------

SITE_ROOT = "https://g1.globo.com"                    # Raiz do site (usada para montar URLs absolutas).
SEARCH_URL = f"{SITE_ROOT}/busca/"                    # Endpoint de busca.
ROBOTS_URL = f"{SITE_ROOT}/robots.txt"                # Para respeitar políticas de crawling.

# ---------------------------------------------------------------------------
# Parâmetros de busca
# ---------------------------------------------------------------------------

TERMO_BUSCA = "lgpd"                                   # Termo padrão do exercício.

# ---------------------------------------------------------------------------
# Headers HTTP — sem User-Agent "de bot", o G1 pode bloquear ou servir HTML diferente
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------------------------------------------------------------------------
# Seletores CSS — AJUSTE AQUI se o G1 mudar o layout
# ---------------------------------------------------------------------------
# Cada seletor tem um "fallback" (separado por vírgula) para aumentar a
# robustez a mudanças parciais de layout. O BeautifulSoup aceita múltiplos
# seletores separados por vírgula (mesma semântica de CSS).

SELECTORS = {
    "container": (
        "div.feed-post-body, "          # Layout atual observado.
        "div[class*='bstn-'] article, " # Fallback: framework interno da Globo.
        "li[class*='result']"           # Fallback: layout antigo.
    ),
    "title": (
        "a.feed-post-link, "
        "h2 a, "                        # Fallback: título dentro de <h2>
        "a[class*='title']"
    ),
    "summary": (
        "div.feed-post-body-resumo, "
        "p[class*='resumo'], "
        "p"                             # Fallback mais genérico.
    ),
    "date": (
        "span.feed-post-datetime, "
        "time, "                        # Tag HTML semântica de data.
        "span[class*='date']"
    ),
}

# ---------------------------------------------------------------------------
# Parâmetros de execução
# ---------------------------------------------------------------------------

MAX_PAGES = 10              # Limite superior de páginas (evita loop infinito).
SLEEP_INTERVAL = 1.5        # Segundos entre requisições (respeito ao servidor).
RETRIES = 3                 # Tentativas por URL antes de desistir.
BACKOFF_BASE = 2.0          # Base do backoff exponencial (2^tentativa segundos).
TIMEOUT = 15                # Timeout de cada requisição HTTP, em segundos.

# ---------------------------------------------------------------------------
# Schema dos registros — ordem importa para o CSV
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "titulo",
    "url",
    "resumo",
    "data_publicacao_raw",   # Texto bruto como apareceu na página.
    "data_publicacao_iso",   # Data normalizada em ISO 8601 (se possível).
    "pagina",                # Número da página de onde veio o resultado.
    "termo_busca",           # Termo usado (rastreabilidade).
    "coletado_em",           # Timestamp da coleta.
]