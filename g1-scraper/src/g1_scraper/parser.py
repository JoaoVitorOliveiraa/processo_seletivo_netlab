"""
Parsing do HTML e normalização de campos.
Este módulo NÃO faz requisições HTTP — recebe o HTML já baixado e devolve
uma lista de `Resultado`. Isso torna os testes triviais (basta passar
um HTML fixture).
"""

from __future__ import annotations

import logging
import re                                       # Expressões regulares para datas.
from datetime import datetime, timedelta        # Manipulação de datas.
from bs4 import BeautifulSoup                   # Parser HTML.
from .config import SELECTORS
from .models import Resultado

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Expressões regulares para normalizar datas em português
# ---------------------------------------------------------------------------

# Exemplo: "há 2 horas", "há 3 dias", "há 1 semana"
_RELATIVE_RE = re.compile(
    r"há\s+(\d+)\s+(minuto|hora|dia|semana|m[êe]s|ano)s?",
    re.IGNORECASE,
)

# Exemplo: "10/01/2025 14h30"
_ABSOLUTE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2})h(\d{2})")

# Mapeamento unidade → função que retorna timedelta
_DELTAS = {
    "minuto": lambda n: timedelta(minutes=n),
    "hora": lambda n: timedelta(hours=n),
    "dia": lambda n: timedelta(days=n),
    "semana": lambda n: timedelta(weeks=n),
    "mês": lambda n: timedelta(days=30 * n),
    "mes": lambda n: timedelta(days=30 * n),
    "ano": lambda n: timedelta(days=365 * n),
}


def normalize_date(raw: str | None, now: datetime | None = None) -> str | None:
    """
    Converte datas relativas/absolutas do G1 para ISO 8601.
    Retorna None se não for possível converter. O texto bruto continua
    disponível em data_publicacao_raw, então nada é perdido.
    """

    if not raw:
        return None

    now = now or datetime.now()
    raw_clean = raw.strip().lower()

    # Caso 1: Data relativa ("há 2 horas")
    m = _RELATIVE_RE.search(raw_clean)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta_fn = _DELTAS.get(unit)
        if delta_fn:
            return (now - delta_fn(n)).isoformat(timespec="seconds")

    # Caso 2: Palavras-Chave ("ontem", "hoje")
    if raw_clean == "ontem":
        return (now - timedelta(days=1)).date().isoformat()
    if raw_clean in ("hoje", "agora"):
        return now.date().isoformat()

    # Caso 3: Data absoluta ("10/01/2025 14h30")
    m = _ABSOLUTE_RE.search(raw_clean)
    if m:
        d, mo, y, h, mi = map(int, m.groups())
        try:
            return datetime(y, mo, d, h, mi).isoformat(timespec="seconds")
        except ValueError:
            # Data inválida (ex.: 31/02) → desiste
            return None

    return None


def parse_page(html: str, page_num: int, termo: str) -> list[Resultado]:
    """
    Extrai todos os resultados válidos de uma página HTML do G1.
    Regras:
    - Cards sem título OU sem URL são ignorados (não são resultados).
    - Campos ausentes viram None — nunca lançam exceção.
    - Qualquer erro em um card individual não interrompe os demais.
    """
    
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(SELECTORS["container"])

    # Se o seletor principal falhar, é sinal de que o layout mudou
    if not cards:
        logger.warning(
            "Nenhum card na página %d com o seletor %r. "
            "Verifique src/g1_scraper/config.py.",
            page_num,
            SELECTORS["container"],
        )
        return []

    results: list[Resultado] = []

    for idx, card in enumerate(cards):
        try:
            # Título: obrigatório. Se não tiver link, o card não é um resultado.
            title_tag = card.select_one(SELECTORS["title"])
            if not title_tag or not title_tag.get("href"):
                logger.debug("Card %d da página %d sem título/URL. Ignorado.", idx, page_num)
                continue

            # Resumo e data: opcionais
            summary_tag = card.select_one(SELECTORS["summary"])
            date_tag = card.select_one(SELECTORS["date"])

            # URL absoluta (o G1 usa hrefs relativos)
            from urllib.parse import urljoin
            from .config import SITE_ROOT

            url = urljoin(SITE_ROOT + "/", title_tag["href"])
            raw_date = date_tag.get_text(strip=True) if date_tag else None

            results.append(Resultado(
                titulo=title_tag.get_text(strip=True),
                url=url,
                resumo=summary_tag.get_text(strip=True) if summary_tag else None,
                data_publicacao_raw=raw_date,
                data_publicacao_iso=normalize_date(raw_date),
                pagina=page_num,
                termo_busca=termo,
            ))

        except Exception as e:
            # Um card ruim não derruba a coleta inteira
            logger.warning("Erro no card %d da página %d: %s", idx, page_num, e)
            continue

    logger.info("Página %d: %d resultados válidos.", page_num, len(results))
    return results