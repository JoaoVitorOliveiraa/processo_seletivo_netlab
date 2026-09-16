"""
Testes do módulo quality.py.
Cada métrica é testada isoladamente, incluindo casos de borda:
listas vazias, campos ausentes, duplicatas e registros incompletos.
"""

from g1_scraper.quality import (
    completeness,
    traceability,
    uniqueness,
)

# ---------------------------------------------------------------------------
# Casos vazios — Todas as métricas devem retornar 0.0, não quebrar
# ---------------------------------------------------------------------------

def test_metricas_com_lista_vazia_retornam_zero():
    """Lista vazia é o caso mais extremo — nenhuma métrica deve dividir por zero."""
    assert uniqueness([]) == 0.0
    assert completeness([]) == 0.0
    assert traceability([]) == 0.0


# ---------------------------------------------------------------------------
# uniqueness — Fração de URLs distintas sobre o total
# ---------------------------------------------------------------------------

def test_uniqueness_sem_duplicatas():
    """Todas as URLs diferentes → métrica perfeita (1.0)."""
    data = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
    assert uniqueness(data) == 1.0


def test_uniqueness_com_duplicatas():
    """Uma duplicata em três registros → 2 únicas / 3 totais."""
    data = [{"url": "a"}, {"url": "b"}, {"url": "a"}]
    assert uniqueness(data) == 2 / 3


def test_uniqueness_ignora_registros_sem_url():
    """Registros com url=None são descartados do cálculo (não contam como duplicata)."""
    data = [{"url": "a"}, {"url": None}, {"url": "a"}]
    # Só "a" conta → 1 única / 2 com url = 0.5
    assert uniqueness(data) == 0.5


# ---------------------------------------------------------------------------
# completeness — Fração de registros com campos obrigatórios preenchidos
# ---------------------------------------------------------------------------

def test_completeness_tudo_preenchido():
    """Todos os campos obrigatórios presentes em todos os registros → 1.0."""
    data = [
        {"titulo": "t", "url": "u", "pagina": 1, "coletado_em": "x"},
        {"titulo": "t", "url": "u", "pagina": 2, "coletado_em": "x"},
    ]
    assert completeness(data) == 1.0


def test_completeness_com_campo_faltando():
    """Um registro com url=None entre dois → 1 completo / 2 totais."""
    data = [
        {"titulo": "t", "url": "u", "pagina": 1, "coletado_em": "x"},
        {"titulo": "t", "url": None, "pagina": 1, "coletado_em": "x"},
    ]
    assert completeness(data) == 0.5


def test_completeness_campo_opcional_nao_conta_como_falha():
    """`resumo` é opcional — sua ausência NÃO afeta a métrica."""
    data = [
        {"titulo": "t", "url": "u", "pagina": 1, "coletado_em": "x", "resumo": None},
    ]
    assert completeness(data) == 1.0


def test_completeness_campo_vazio_string_conta_como_faltando():
    """String vazia ('') deve ser tratada como ausente, igual a None."""
    data = [
        {"titulo": "", "url": "u", "pagina": 1, "coletado_em": "x"},
    ]
    assert completeness(data) == 0.0


# ---------------------------------------------------------------------------
# traceability — Fração de registros com pagina + coletado_em preenchidos
# ---------------------------------------------------------------------------

def test_traceability_completa():
    """Todos os registros com pagina e coletado_em → 1.0."""
    data = [
        {"pagina": 1, "coletado_em": "x"},
        {"pagina": 2, "coletado_em": "y"},
    ]
    assert traceability(data) == 1.0


def test_traceability_parcial():
    """Um registro sem pagina entre dois → 1 rastreável / 2 totais."""
    data = [
        {"pagina": 1, "coletado_em": "x"},
        {"pagina": None, "coletado_em": "x"},
    ]
    assert traceability(data) == 0.5


def test_traceability_sem_coletado_em_conta_como_falha():
    """Falta de coletado_em também invalida a rastreabilidade do registro."""
    data = [
        {"pagina": 1, "coletado_em": "x"},
        {"pagina": 1, "coletado_em": None},
    ]
    assert traceability(data) == 0.5