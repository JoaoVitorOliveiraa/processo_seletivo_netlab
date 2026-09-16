"""
Parsing do HTML do G1 e normalização de campos.

Seletores baseados em inspeção real do HTML (não em suposições).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, unquote

from bs4 import BeautifulSoup

from .config import SELECTORS, SITE_ROOT
from .models import Resultado

logger = logging.getLogger(__name__)

_RELATIVE_RE = re.compile(r"há\s+(\d+)\s+(minuto|hora|dia|semana|m[êe]s|ano)s?", re.IGNORECASE)

# Casa com ambos os formatos observados no G1:
# - "25/08/2026 16:27"  (layout atual — dois pontos)
# - "10/01/2025 14h30"  (layout antigo — letra h)
_ABSOLUTE_RE = re.compile(
    r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2})[h:](\d{2})"
)

_DELTAS = {
    "minuto": lambda n: timedelta(minutes=n),
    "hora": lambda n: timedelta(hours=n),
    "dia": lambda n: timedelta(days=n),
    "semana": lambda n: timedelta(weeks=n),
    "mês": lambda n: timedelta(days=30 * n),
    "mes": lambda n: timedelta(days=30 * n),
    "ano": lambda n: timedelta(days=365 * n),
}


def extract_real_url(tracking_url: str) -> str:
    """
    Extrai a URL real do parâmetro `u=` do link de tracking do G1.

    O G1 envolve todos os links num wrapper de redirecionamento
    (measures.globo.com/v1/click?...&u=<URL_REAL>). Se não decodificarmos,
    o CSV fica cheio de URLs de tracking em vez das notícias reais.

    Fallback: retorna a URL original se não houver parâmetro `u=`.
    """
    if not tracking_url:
        return ""
    parsed = urlparse(tracking_url)
    params = parse_qs(parsed.query)
    real = params.get("u", [None])[0]
    return unquote(real) if real else tracking_url


def normalize_date(raw: str | None, now: datetime | None = None) -> str | None:
    """Converte datas relativas/absolutas do G1 para ISO 8601."""
    if not raw:
        return None
    now = now or datetime.now()
    raw_clean = raw.strip().lower()

    m = _RELATIVE_RE.search(raw_clean)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta_fn = _DELTAS.get(unit)
        if delta_fn:
            return (now - delta_fn(n)).isoformat(timespec="seconds")

    if raw_clean == "ontem":
        return (now - timedelta(days=1)).date().isoformat()
    if raw_clean in ("hoje", "agora"):
        return now.date().isoformat()

    m = _ABSOLUTE_RE.search(raw_clean)
    if m:
        d, mo, y, h, mi = map(int, m.groups())
        try:
            return datetime(y, mo, d, h, mi).isoformat(timespec="seconds")
        except ValueError:
            return None

    return None


def _extract_date(card) -> str | None:
    """Extrai a data do div.widget--info__meta (último <span>)."""
    meta = card.select_one(SELECTORS["meta"])
    if not meta:
        return None
    textos = [t.strip() for t in meta.stripped_strings if t.strip()]
    return textos[-1] if textos else None


def parse_page(html: str, page_num: int, termo: str) -> list[Resultado]:
    """Extrai resultados válidos da página HTML do G1."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(SELECTORS["container"])

    if not cards:
        logger.warning(
            "Nenhum card na página %d com seletor %r. Verifique config.py.",
            page_num, SELECTORS["container"],
        )
        return []

    results: list[Resultado] = []

    for idx, card in enumerate(cards):
        try:
            # Título (obrigatório)
            title_div = card.select_one(SELECTORS["title_text"])
            if not title_div:
                logger.debug("Card %d sem título. Ignorado.", idx)
                continue

            # O link está no <a> que envolve o title_div
            link_tag = title_div.find_parent("a")
            if not link_tag or not link_tag.get("href"):
                logger.debug("Card %d sem link. Ignorado.", idx)
                continue

            # URL real (decodificada do tracking)
            url = extract_real_url(link_tag["href"])

            # Resumo e veículo (opcionais)
            summary_tag = card.select_one(SELECTORS["summary"])
            source_tag = card.select_one(SELECTORS["source"])

            # Data (do meta)
            raw_date = _extract_date(card)

            # Marcador de publicidade
            is_ad = card.select_one(SELECTORS["ad_label"]) is not None

            results.append(Resultado(
                titulo=title_div.get_text(strip=True),
                url=url,
                resumo=summary_tag.get_text(strip=True) if summary_tag else None,
                veiculo=source_tag.get_text(strip=True) if source_tag else None,
                data_publicacao_raw=raw_date,
                data_publicacao_iso=normalize_date(raw_date),
                publicitario=is_ad,
                pagina=page_num,
                termo_busca=termo,
            ))

        except Exception as e:
            logger.warning("Erro no card %d da página %d: %s", idx, page_num, e)
            continue

    logger.info("Página %d: %d resultados válidos.", page_num, len(results))
    return results