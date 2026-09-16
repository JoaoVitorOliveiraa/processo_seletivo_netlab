"""
Testes do módulo llm_helper.py.
Cobre as três funções públicas do módulo — sem chamar API de LLM real:
1. Parsing seguro da resposta JSON (com fallback para texto solto).
2. Validação de seletores CSS contra um HTML real.
3. Comparação de snapshots HTML (detecção de drift de layout).
"""

from g1_scraper.llm_helper import (
    _safe_json_parse,
    compare_snapshots,
    validate_selectors,
)

# ---------------------------------------------------------------------------
# Extraindo JSON de respostas de LLM
# ---------------------------------------------------------------------------

def test_safe_json_parse_extracts_json_from_code_fence():
    """
    LLMs costumam envolver o JSON em ```json ... ```.
    O parser deve extrair o conteúdo entre as cercas, ignorando o resto.
    """
    text = '```json\n{"container": {"selector": "div.x"}}\n```'
    assert _safe_json_parse(text)["container"]["selector"] == "div.x"


def test_safe_json_parse_ignores_surrounding_text():
    """
    Mesmo sem cercas, a LLM pode adicionar preâmbulo ("Claro! Aqui está:").
    O regex interno deve localizar o primeiro { ... } e ignorar o resto.
    """
    text = 'Claro! Aqui está: {"a": 1} — espero ter ajudado.'
    assert _safe_json_parse(text) == {"a": 1}


def test_safe_json_parse_returns_empty_without_json():
    """
    Se não há JSON nenhum na resposta, retorna {} — não lança exceção.
    A ausência de sugestão é tratada como "sem sugestão", não como erro.
    """
    assert _safe_json_parse("sem json aqui") == {}
    assert _safe_json_parse("") == {}


def test_safe_json_parse_returns_empty_on_invalid_json():
    """
    JSON malformado (chave sem aspas) também cai no fallback {}.
    Isso evita que uma resposta criativa da LLM derrube a pipeline inteira.
    """
    assert _safe_json_parse("{chave sem aspas}") == {}


# ---------------------------------------------------------------------------
# Validando seletores CSS
# ---------------------------------------------------------------------------

def test_validate_selectors_accepts_valid_selector():
    """
    Seletor CSS correto + casa com ≥ 1 elemento → valid=True.
    O relatório detalha quantos elementos cada campo encontrou.
    """
    html = '<div class="x"><a href="#">t</a></div>'
    report = validate_selectors(html, {"container": {"selector": "div.x"}})
    assert report["valid"] is True
    assert report["details"]["container"]["count"] == 1


def test_validate_selectors_rejects_missing_selector():
    """
    Seletor sintaticamente válido, mas que não casa com nada no HTML
    (ex.: classe inexistente) → valid=False. É o cenário clássico de
    "o G1 mudou o layout e o seletor antigo ficou órfão".
    """
    html = "<div></div>"
    report = validate_selectors(html, {"container": {"selector": "div.missing"}})
    assert report["valid"] is False


def test_validate_selectors_rejects_invalid_css():
    """
    Seletor com sintaxe quebrada (ex.: '>>> inválido') deve ser rejeitado
    ANTES de tentar casar com o HTML — o BeautifulSoup lança exceção ao
    compilar. O relatório guarda a mensagem de erro no campo details.
    """
    html = "<div></div>"
    report = validate_selectors(html, {"x": {"selector": ">>> invalid"}})
    assert report["valid"] is False
    assert "error" in report["details"]["x"]


def test_validate_selectors_accepts_plain_string():
    """
    O candidato pode vir como dict ({"selector": "...", "evidence": "..."})
    ou como string simples. A função normaliza os dois formatos.
    """
    html = '<div class="x"></div>'
    report = validate_selectors(html, {"container": "div.x"})
    assert report["valid"] is True


# ---------------------------------------------------------------------------
# Comparando HTMLs
# ---------------------------------------------------------------------------

def test_compare_snapshots_detects_changes():
    """
    Comparar dois HTMLs e listar classes CSS adicionadas/removidas.

    Esse diff é o gatilho do monitoramento: se uma classe que estava nos
    seletores ativos aparecer em 'classes_removidas', é sinal de que o
    layout mudou e a coleta pode estar quebrada. A LLM recebe esse diff
    como contexto adicional para sugerir seletores novos.
    """
    old = '<div class="a"></div><div class="b"></div>'
    new = '<div class="b"></div><div class="c"></div>'

    diff = compare_snapshots(old, new)
    assert "a" in diff["classes_removidas"]
    assert "c" in diff["classes_adicionadas"]
    assert "b" not in diff["classes_removidas"]  # classe preservada


def test_compare_snapshots_no_changes():
    """
    HTML idêntico → diff vazio nos dois lados. Garante que o comparador
    não gera falsos positivos (alertas desnecessários no monitoramento).
    """
    html = '<div class="a"></div>'
    diff = compare_snapshots(html, html)
    assert diff["classes_removidas"] == []
    assert diff["classes_adicionadas"] == []