#Camada HTTP: Baixa páginas, Trata erros e Respeita robots.txt.

from __future__ import annotations

import logging                                      # Logs informativos e de erro.
import time
from urllib.robotparser import RobotFileParser      # Parser do robots.txt.
import requests                                     # Cliente HTTP.

from .config import (
    BACKOFF_BASE,
    HEADERS,
    RETRIES,
    ROBOTS_URL,
    TIMEOUT,
)

# "__name__" vira "g1_scraper.client", permitindo filtrar logs por módulo.
logger = logging.getLogger(__name__)    

# Cache global do robots.txt (lido uma vez por execução)
_robots_cache: RobotFileParser | None = None


def _get_robots() -> RobotFileParser:
    """
    Lê o robots.txt uma única vez e mantém em cache.

    O G1 serve o robots.txt com Content-Encoding: gzip, o que quebra o
    parser nativo do Python (ele não descomprime automaticamente). Por
    isso, baixamos com `requests` (que descomprime) e parseamos o texto
    manualmente via `parse()`.

    Se a leitura falhar por qualquer motivo, retornamos um parser
    explicitamente permissivo — nunca um vazio, que bloquearia tudo.
    """
    global _robots_cache
    if _robots_cache is not None:
        return _robots_cache

    rp = RobotFileParser()
    rp.set_url(ROBOTS_URL)

    try:
        # `requests` lida com gzip/deflate/br automaticamente.
        resp = requests.get(ROBOTS_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        # `parse()` espera uma lista de linhas (sem o \n).
        rp.parse(resp.text.splitlines())
        logger.info("robots.txt carregado com sucesso de %s.", ROBOTS_URL)

    except Exception as e:
        # Fallback explícito: libera tudo. O aviso é honesto agora —
        # o comportamento real bate com a mensagem do log.
        logger.warning(
            "Falha ao ler robots.txt (%s). Modo permissivo ativado.", e
        )
        # Truque: alimenta o parser com uma regra que libera tudo.
        rp.parse(["User-agent: *", "Disallow:"])

    _robots_cache = rp
    return _robots_cache


def can_fetch(url: str, user_agent: str = "*") -> bool:
    """
    Consulta o robots.txt do G1. Retorna True se a coleta é permitida.
    Se o robots.txt não puder ser lido, é permissivo por padrão.
    """
    try:
        return _get_robots().can_fetch(user_agent, url)
    except Exception:
        return True


def fetch_page(url: str, retries: int = RETRIES, backoff: float = BACKOFF_BASE) -> str | None:
    """
    Baixa o HTML de uma URL com retentativas e backoff exponencial.
    Retorna:
        str  → HTML da página, se bem-sucedido.
        None → se todas as tentativas falharem OU se houver redirecionamento
               (o G1 redireciona para a página 1 quando você pede além do
               limite, e isso sinaliza fim da paginação).
    """

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                allow_redirects=False,
            )

            # Códigos 3xx indicam redirecionamento → fim da paginação.
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "?")
                logger.info("Redirecionamento em %s → %s. Encerrando paginação.", url, location)
                return None

            # Levanta exceção para 4xx e 5xx.
            response.raise_for_status()
            return response.text

        except requests.Timeout:
            logger.warning("Timeout (tentativa %d/%d) em %s", attempt, retries, url)

        except requests.HTTPError as e:
            # 4xx = erro do cliente (não adianta repetir).
            # 5xx = erro do servidor (pode valer a pena repetir).
            status = e.response.status_code if e.response is not None else None
            logger.error("HTTP %s em %s", status, url)

            if status is not None and 400 <= status < 500:
                return None  # Desiste imediatamente.

        except requests.RequestException as e:
            # Qualquer outro erro de rede (DNS, conexão recusada etc.)
            logger.error("Erro de conexão em %s: %s", url, e)

        # Backoff exponencial antes da próxima tentativa
        if attempt < retries:
            time.sleep(backoff ** attempt)

    logger.error("Falha definitiva ao baixar %s após %d tentativas.", url, retries)
    return None