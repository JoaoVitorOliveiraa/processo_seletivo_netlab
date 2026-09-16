"""
Testes do parser — baseados no HTML real do G1.

Cobre: extração de campos, decodificação de URLs de tracking,
normalização de datas e detecção de conteúdo patrocinado.
"""
from datetime import datetime

from g1_scraper.parser import extract_real_url, normalize_date, parse_page


# ---------------------------------------------------------------------------
# extract_real_url — decodifica o wrapper de tracking do G1
# ---------------------------------------------------------------------------

def test_extract_real_url_do_tracking():
    """A URL real está no parâmetro u= do link measures.globo.com."""
    tracking = (
        "https://measures.globo.com/v1/click?c=busca-headless&h=abc"
        "&u=https%3A%2F%2Fg1.globo.com%2Ftecnologia%2Fnoticia%2F2026%2F08%2F25%2Ftiktok.ghtml"
    )
    assert extract_real_url(tracking) == (
        "https://g1.globo.com/tecnologia/noticia/2026/08/25/tiktok.ghtml"
    )


def test_extract_real_url_sem_tracking():
    """URL direta (não envelopada) deve ser retornada intacta."""
    url = "https://g1.globo.com/noticia-direta.ghtml"
    assert extract_real_url(url) == url


def test_extract_real_url_vazia():
    """Entradas vazias ou None não devem lançar exceção."""
    assert extract_real_url("") == ""
    assert extract_real_url(None) == ""


# ---------------------------------------------------------------------------
# parse_page — extração completa a partir do HTML real
# ---------------------------------------------------------------------------

def test_parse_page_extrai_campos_reais(sample_html):
    """Cada card deve virar um Resultado com todos os campos corretos."""
    results = parse_page(sample_html, page_num=1, termo="lgpd")

    assert len(results) == 3

    # Card 1: notícia com data relativa
    r1 = results[0]
    assert r1.titulo == "EmpregaTrans: capacitação gratuita para pessoas trans"
    assert r1.url == "https://g1.globo.com/mt/mato-grosso/noticia/2026/09/15/empregatrans.ghtml"
    assert r1.veiculo == "G1"
    assert r1.data_publicacao_raw == "há 12 horas"
    assert r1.publicitario is False

    # Card 2: notícia com data absoluta (convertida para ISO)
    r2 = results[1]
    assert r2.data_publicacao_raw == "25/08/2026 16:27"
    assert r2.data_publicacao_iso == "2026-08-25T16:27:00"

    # Card 3: conteúdo patrocinado (marcado pela ad-label)
    r3 = results[2]
    assert r3.publicitario is True


def test_parse_page_decodifica_url_real(sample_html):
    """Nenhuma URL final deve apontar para measures.globo.com."""
    results = parse_page(sample_html, page_num=1, termo="lgpd")
    for r in results:
        assert r.url.startswith("https://g1.globo.com/")
        assert "measures.globo.com" not in r.url


# ---------------------------------------------------------------------------
# normalize_date — converte formatos variados para ISO 8601
# ---------------------------------------------------------------------------

def test_normalize_date_absoluta():
    """Formato DD/MM/AAAA HHhMM vira ISO 8601."""
    assert normalize_date("10/01/2025 14h30") == "2025-01-10T14:30:00"


def test_normalize_date_relativa_horas():
    """Datas relativas ('há N horas') viram ISO com base no 'now'."""
    now = datetime(2025, 1, 15, 12, 0, 0)
    assert normalize_date("há 2 horas", now=now) == "2025-01-15T10:00:00"


def test_normalize_date_invalida():
    """Texto irreconhecível ou None retornam None, sem exceção."""
    assert normalize_date("texto") is None
    assert normalize_date(None) is None