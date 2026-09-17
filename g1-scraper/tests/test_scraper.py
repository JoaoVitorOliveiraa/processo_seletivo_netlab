"""
Testes do módulo scraper.py.

Foca na orquestração: paginação via Playwright + deduplicação.
Usa monkeypatch para isolar do HTTP e do parser — a suíte roda offline.
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
    fetch_page=None sinaliza fim (redirect ou erro persistente).

    A nova assinatura do fetch_page aceita o kwarg `pages` — o mock
    precisa refletir isso para não quebrar o contrato.
    """
    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url, pages=1: None)

    assert scraper.collect("lgpd", max_pages=5) == []


def test_collect_para_quando_nao_ha_novos(monkeypatch):
    """
    Página sem resultados válidos encerra a coleta sem exceção.

    Quando o parser devolve [], o collect retorna [] imediatamente —
    não há loop de páginas como antes, porque a paginação é feita
    dentro do Playwright (clique em 'Veja mais').
    """
    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url, pages=1: "<html/>")
    monkeypatch.setattr(scraper, "parse_page", lambda *a, **k: [])

    results = scraper.collect("lgpd", max_pages=10)
    assert results == []


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------

def test_collect_deduplica_por_url_e_titulo(monkeypatch):
    """
    Mesma chave (url, titulo) nunca entra duas vezes.

    Como o G1 pode repetir cards entre cliques do 'Veja mais', a dedup
    é feita no scraper — antes de retornar a lista final.
    """
    r1 = _make_resultado("https://x.com/1", "Notícia A")
    r2 = _make_resultado("https://x.com/2", "Notícia B")

    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url, pages=1: "<html/>")
    monkeypatch.setattr(scraper, "parse_page", lambda *a, **k: [r1, r2, r1, r2, r1])

    results = scraper.collect("lgpd", max_pages=3)
    assert len(results) == 2


def test_collect_preserva_mesma_url_com_titulos_diferentes(monkeypatch):
    """
    Chave inclui o título: mesma URL com título novo é tratada como atualização.
    """
    r1 = _make_resultado("https://x.com/1", "Título original")
    r2 = _make_resultado("https://x.com/1", "Título atualizado")

    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(scraper, "fetch_page", lambda url, pages=1: "<html/>")
    monkeypatch.setattr(scraper, "parse_page", lambda *a, **k: [r1, r2])

    results = scraper.collect("lgpd", max_pages=1)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def test_collect_respeita_robots_txt(monkeypatch):
    """
    Proibido pelo robots.txt: aborta antes de qualquer fetch.
    """
    monkeypatch.setattr(scraper, "can_fetch", lambda url: False)

    fetch_called = {"v": False}
    monkeypatch.setattr(
        scraper, "fetch_page",
        lambda url, pages=1: fetch_called.__setitem__("v", True),
    )

    assert scraper.collect("lgpd") == []
    assert fetch_called["v"] is False