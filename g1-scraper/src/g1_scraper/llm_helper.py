"""
Uso de LLM para sugerir seletores quando o HTML do G1 muda.
A LLM só sugere — toda sugestão passa por validação programática e
revisão humana antes de entrar em produção. O módulo é opcional: se a
LLM estiver fora do ar, a coleta continua com os seletores atuais.
"""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Prompt fixo: reduz alucinação e obriga saída estruturada
SYSTEM_PROMPT = """Você é um assistente especializado em web scraping com Beautiful Soup.

REGRAS OBRIGATÓRIAS:
1. Responda APENAS com JSON válido, sem texto adicional.
2. Cite o trecho exato do HTML que justifica cada seletor sugerido.
3. Se não tiver certeza, retorne {"error": "insufficient_evidence"}.
4. Nunca invente classes, IDs ou tags que não apareçam no HTML fornecido.
5. Use apenas seletores CSS válidos e suportados por soupsieve.
"""

def _build_prompt(html_snippet: str, current_selectors: dict, log_tail: str = "") -> str:
    """Monta o prompt com HTML truncado + seletores atuais + log."""

    return f"""Analise o HTML abaixo e sugira seletores CSS para extrair:
- container de cada resultado
- título (com link)
- resumo
- data de publicação

SELETORES ATUAIS (possivelmente quebrados):
{json.dumps(current_selectors, ensure_ascii=False, indent=2)}

ÚLTIMAS LINHAS DO LOG:
{log_tail[:2000]}

HTML (primeiros 8000 caracteres):
{html_snippet[:8000]}

Responda APENAS com JSON:
{{
  "container": {{"selector": "...", "evidence": "trecho do HTML"}},
  "title":     {{"selector": "...", "evidence": "trecho do HTML"}},
  "summary":   {{"selector": "...", "evidence": "trecho do HTML"}},
  "date":      {{"selector": "...", "evidence": "trecho do HTML"}}
}}
"""


def _safe_json_parse(text: str) -> dict:
    """Extrai JSON da resposta da LLM. Retorna {} se inválido."""

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Resposta da LLM não é JSON válido.")
        return {}


def suggest_selectors(
    html_snippet: str,
    current_selectors: dict,
    llm_client,
    log_tail: str = "",
) -> dict:
    """
    Pede sugestões de seletores à LLM.

    Retorna dict no formato {campo: {"selector": ..., "evidence": ...}},
    NÃO validado. Use `validate_selectors()` antes de aplicar.
    """

    prompt = _build_prompt(html_snippet, current_selectors, log_tail)

    # Falha da LLM não derruba o fluxo — apenas loga e retorna {}
    try:
        response = llm_client.complete(system=SYSTEM_PROMPT, user=prompt)
    except Exception as e:
        logger.error("Falha ao consultar a LLM: %s", e)
        return {}

    parsed = _safe_json_parse(response)

    # LLM admite incerteza → tratamos como "sem sugestão"
    if "error" in parsed:
        logger.info("LLM declarou evidência insuficiente: %s", parsed["error"])
        return {}

    return parsed


def validate_selectors(html: str, candidates: dict) -> dict:
    """
    Valida cada seletor candidato contra o HTML real.
    Um seletor é válido apenas se: (1) for CSS válido,
    (2) casar com ≥ 1 elemento no HTML.
    """

    soup = BeautifulSoup(html, "html.parser")
    report: dict = {"valid": True, "details": {}}

    for field, payload in candidates.items():
        # Aceita tanto {"selector": "..."} quanto "..." direto
        selector = payload.get("selector") if isinstance(payload, dict) else payload

        if not selector:
            report["valid"] = False
            report["details"][field] = {"error": "sem seletor"}
            continue

        try:
            elements = soup.select(selector)
        except Exception as e:
            report["valid"] = False
            report["details"][field] = {"error": f"seletor CSS inválido: {e}"}
            continue

        ok = len(elements) > 0
        report["details"][field] = {"count": len(elements), "ok": ok}
        if not ok:
            report["valid"] = False

    return report


def compare_snapshots(old_html: str, new_html: str) -> dict:
    """
    Compara duas versões do HTML e reporta classes CSS removidas/adicionadas.

    Útil como entrada adicional para a LLM: mostra o que mudou entre
    duas versões da página.
    """

    def classes(soup: BeautifulSoup) -> set[str]:
        """Extrai o conjunto de classes CSS primárias de um HTML."""

        result = set()
        for tag in soup.find_all(class_=True):
            cls = tag.get("class")
            if cls:
                result.add(cls[0])
        return result

    old_c = classes(BeautifulSoup(old_html, "html.parser"))
    new_c = classes(BeautifulSoup(new_html, "html.parser"))

    return {
        "classes_removidas": sorted(old_c - new_c),
        "classes_adicionadas": sorted(new_c - old_c),
    }