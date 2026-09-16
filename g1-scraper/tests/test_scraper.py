"""
Testes do módulo scraper.py.
Foca na orquestração: paginação, deduplicação e parada antecipada.
Usa monkeypatch para isolar do HTTP e do parser — a suíte roda offline
e determinística.
"""

from g1_scraper import scraper
from g1_scraper.models import Resultado


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_resultado(url: str, titulo: str, pagina: int = 1) -> Resultado:
    """Resultado mínimo — só os campos que a dedup do scraper usa."""
    return Resultado(titulo=titulo, url=url, pagina=pagina, termo_busca="lgpd")


# ---------------------------------------------------------------------------
# Parada antecipada
# ---------------------------------------------------------------------------

def test_collect_para_quando_fetch_retorna_none(monkeypatch):
    """
    fetch_page=None é o sinal que o scraper usa para encerrar a paginação.

    O client devolve None quando: (a) o G1 redireciona para page=1 (sinal
    de "passou do limite"), ou (b) esgotou as retentativas após 4xx/5xx.
    Este teste garante que o scraper trata esse caso sem lançar exceção.
    """
    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url: None)
    monkeypatch.setattr(scraper, "parse_page", lambda *a, **k: [])

    assert scraper.collect("lgpd", max_pages=5) == []


def test_collect_para_quando_nao_ha_novos(monkeypatch):
    """
    Página sem resultados novos encerra a coleta — não varre o restante.

    Em uma busca típica, as páginas vão ficando vazias conforme se aproxima
    do fim. Sem essa checagem, o scraper faria 10 requests inúteis ao G1.
    O teste verifica o call_count para provar que só 2 páginas foram
    processadas (a 1ª com dados, a 2ª vazia → break).
    """
    call_count = {"n": 0}

    def fake_parse(html, page, termo):
        call_count["n"] += 1
        # Página 1 tem 2 resultados; as seguintes vêm vazias
        return [_make_resultado(f"https://x.com/{i}", f"N{i}") for i in range(2)] if page == 1 else []

    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url: "<html/>")
    monkeypatch.setattr(scraper, "parse_page", fake_parse)

    results = scraper.collect("lgpd", max_pages=10, sleep_interval=0)

    assert len(results) == 2
    assert call_count["n"] == 2  # Parou na 2ª — não tentou as 8 restantes


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------

def test_collect_deduplica_por_url_e_titulo(monkeypatch):
    """
    Cada resultado é identificado pela tupla (url, titulo), não só pela URL.

    O scraper mantém um set de chaves vistas e descarta repetições antes de
    acumular. Aqui, as 3 páginas retornam os mesmos 2 resultados — o set
    precisa reduzir 6 entradas brutas para 2 únicas.

    Sem essa dedup, o CSV sairia com URLs repetidas e a métrica de
    unicidade do quality.py cairia abaixo de 1.0.
    """
    r1 = _make_resultado("https://x.com/1", "Notícia A")
    r2 = _make_resultado("https://x.com/2", "Notícia B")

    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url: "<html/>")
    monkeypatch.setattr(scraper, "parse_page", lambda *a, **k: [r1, r2])

    results = scraper.collect("lgpd", max_pages=3, sleep_interval=0)

    assert len(results) == 2


def test_collect_preserva_mesma_url_com_titulos_diferentes(monkeypatch):
    """
    Incluir o título na chave evita descartar republicações legítimas.

    Se a chave fosse só a URL, uma notícia atualizada (mesmo link, título
    novo) seria descartada como duplicata — perdendo a versão mais recente.
    Com (url, titulo) as duas convivem; cabe ao analista decidir qual usar.
    """
    r1 = _make_resultado("https://x.com/1", "Título original")
    r2 = _make_resultado("https://x.com/1", "Título atualizado")

    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url: "<html/>")
    monkeypatch.setattr(scraper, "parse_page", lambda *a, **k: [r1, r2])

    results = scraper.collect("lgpd", max_pages=1, sleep_interval=0)

    assert len(results) == 2


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def test_collect_respeita_robots_txt(monkeypatch):
    """
    Se can_fetch(url) == False, nenhuma requisição HTTP é feita.

    can_fetch consulta o robots.txt do G1 (cacheado em client.py) e devolve
    True/False conforme as regras do site. Este teste prova que a checagem
    acontece ANTES do fetch_page — o spy fetch_called nunca vira True.

    É a garantia ética do scraper: mesmo que o robots.txt mude para proibir
    a busca, o código não insiste em burlar a restrição.
    """
    monkeypatch.setattr(scraper, "can_fetch", lambda url: False)

    fetch_called = {"v": False}
    monkeypatch.setattr(
        scraper, "fetch_page",
        lambda url: fetch_called.__setitem__("v", True),
    )

    assert scraper.collect("lgpd") == []
    assert fetch_called["v"] is False