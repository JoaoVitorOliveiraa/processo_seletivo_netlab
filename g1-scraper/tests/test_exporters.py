"""
Testes do módulo exporters.py.
Verifica: Gravação em JSON e CSV, criação automática de diretório,
robustez a campos ausentes/extras e preservação de acentuação.
"""

import csv
import json
from pathlib import Path

from g1_scraper.exporters import save_csv, save_json
from g1_scraper.models import Resultado


# ---------------------------------------------------------------------------
# Helper — Amostra reutilizada por todos os testes
# ---------------------------------------------------------------------------

def _amostra() -> list[Resultado]:
    """
    Dois registros: um completo (com acentos) e outro sem resumo.
    O segundo testa o comportamento com campos opcionais ausentes.
    """
    return [
        Resultado(
            titulo="Notícia com acentuação",
            url="https://g1.globo.com/1",
            resumo="Resumo com acento: ção, ã, é",
            veiculo="G1",
            data_publicacao_raw="10/01/2025 14h30",
            data_publicacao_iso="2025-01-10T14:30:00",
            publicitario=False,
            pagina=1,
            termo_busca="lgpd",
        ),
        Resultado(
            titulo="Sem resumo",
            url="https://g1.globo.com/2",
            veiculo="G1",
            pagina=1,
            termo_busca="lgpd",
        ),
    ]


# ---------------------------------------------------------------------------
# Salvando em JSON
# ---------------------------------------------------------------------------

def test_save_json_cria_arquivo(tmp_path: Path):
    """O arquivo .json deve existir após a chamada."""
    out = tmp_path / "out.json"
    save_json(_amostra(), out)

    assert out.exists()
    dados = json.loads(out.read_text(encoding="utf-8"))
    assert len(dados) == 2
    assert dados[0]["titulo"] == "Notícia com acentuação"


def test_save_json_cria_diretorio_pai(tmp_path: Path):
    """Se o diretório pai não existe, deve ser criado automaticamente."""
    out = tmp_path / "subdir" / "out.json"
    save_json(_amostra(), out)
    assert out.exists()


def test_save_json_preserva_acentos(tmp_path: Path):
    """ensure_ascii=False — acentos aparecem legíveis, sem escape \\u."""
    out = tmp_path / "out.json"
    save_json(_amostra(), out)
    texto = out.read_text(encoding="utf-8")
    assert "acentuação" in texto
    assert "\\u00e7" not in texto


def test_save_json_aceita_dict_direto(tmp_path: Path):
    """Aceita dicts simples, não apenas dataclasses Resultado."""
    out = tmp_path / "out.json"
    save_json([{"titulo": "t", "url": "u"}], out)
    dados = json.loads(out.read_text(encoding="utf-8"))
    assert dados[0]["titulo"] == "t"


# ---------------------------------------------------------------------------
# Salvando em CSV
# ---------------------------------------------------------------------------

def test_save_csv_escreve_cabecalho_e_linhas(tmp_path: Path):
    """CSV deve ter header + 2 linhas, na ordem correta dos campos."""
    out = tmp_path / "out.csv"
    save_csv(_amostra(), out)

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["titulo"] == "Notícia com acentuação"


def test_save_csv_campo_ausente_vira_string_vazia(tmp_path: Path):
    """resumo=None é serializado como string vazia no CSV (não 'None')."""
    out = tmp_path / "out.csv"
    save_csv(_amostra(), out)

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[1]["resumo"] == ""


def test_save_csv_ignora_campos_extras(tmp_path: Path):
    """Chave fora de FIELDNAMES não deve quebrar o DictWriter."""
    out = tmp_path / "out.csv"
    dados = [{"titulo": "t", "url": "u", "campo_extra": "ignorado"}]
    save_csv(dados, out)

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert "campo_extra" not in rows[0]


def test_save_csv_preserva_acentos(tmp_path: Path):
    """UTF-8 explícito — acentos no CSV devem ser legíveis."""
    out = tmp_path / "out.csv"
    save_csv(_amostra(), out)

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["titulo"] == "Notícia com acentuação"
    assert "ção" in rows[0]["resumo"]