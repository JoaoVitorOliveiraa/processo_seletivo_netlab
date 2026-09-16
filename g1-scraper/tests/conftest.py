"""
Fixtures compartilhadas do pytest.
Define dados reutilizáveis por todos os módulos de teste.
"""

from pathlib import Path
import sys

import pytest

# Adiciona `src/` ao sys.path para que `g1_scraper` seja importável
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def fixtures_dir() -> Path:
    """Caminho absoluto para a pasta de fixtures HTML."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_html(fixtures_dir: Path) -> str:
    """HTML de uma página completa do G1 (recorte real)."""
    return (fixtures_dir / "page_1.html").read_text(encoding="utf-8")


@pytest.fixture
def html_missing_fields(fixtures_dir: Path) -> str:
    """HTML com cards incompletos — para testar robustez do parser."""
    return (fixtures_dir / "page_missing_fields.html").read_text(encoding="utf-8")


@pytest.fixture
def sample_data() -> list[dict]:
    """Lista de dicts de exemplo, no formato dos registros coletados."""
    return [
        {
            "titulo": "LGPD completa 5 anos",
            "url": "https://g1.globo.com/noticia-1",
            "resumo": "Resumo 1",
            "data_publicacao_raw": "10/01/2025 14h30",
            "data_publicacao_iso": "2025-01-10T14:30:00",
            "pagina": 1,
            "termo_busca": "lgpd",
            "coletado_em": "2025-01-15T10:00:00",
        },
        {
            "titulo": "Multas por violação crescem",
            "url": "https://g1.globo.com/noticia-2",
            "resumo": None,
            "data_publicacao_raw": None,
            "data_publicacao_iso": None,
            "pagina": 1,
            "termo_busca": "lgpd",
            "coletado_em": "2025-01-15T10:00:00",
        },
    ]