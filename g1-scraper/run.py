"""
Ponto de entrada do projeto g1-scraper.
Este arquivo:
1. Lê argumentos de linha de comando.
2. Garante que a pasta `logs/` exista (cria se necessário).
3. Configura logging para console + arquivo rotativo.
4. Loga os seletores ativos (para auditoria e diagnóstico).
5. Executa a coleta via `g1_scraper.scraper.collect`.
6. Salva os resultados em JSON e CSV.
7. Alerta se a proporção de campos nulos for alta (drift de layout).
8. Opcionalmente avalia a qualidade dos dados.
9. Trata exceções de topo, retornando código de saída apropriado.
"""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from g1_scraper.config import MAX_PAGES, SELECTORS, TERMO_BUSCA
from g1_scraper.exporters import save_csv, save_json
from g1_scraper.quality import evaluate
from g1_scraper.scraper import collect


# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False) -> None:
    """Configura logging para console + arquivo rotativo."""
    # Garante que a pasta `logs/` exista antes de criar o handler.
    # Sem isso, o RotatingFileHandler falharia com FileNotFoundError.
    Path("logs").mkdir(exist_ok=True)

    # Com --verbose, ativa DEBUG (inclui mensagens de diagnóstico detalhado).
    # Sem --verbose, fica em INFO (só o essencial).
    level = logging.DEBUG if verbose else logging.INFO

    # Formato único para os dois handlers.
    # Ex.: 2025-01-15 10:30:01 | INFO    | g1_scraper.scraper | Página 1: 12 resultados.
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

    # Handler 1 — console (stdout): feedback em tempo real durante a execução.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(log_format))

    # Handler 2 — arquivo rotativo: histórico persistente entre execuções.
    # - maxBytes=5_000_000 → rotaciona ao atingir 5 MB.
    # - backupCount=3      → mantém scraper.log.1, .2 e .3.
    # - encoding="utf-8"   → acentuação correta em português.
    file_handler = RotatingFileHandler(
        "logs/scraper.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(log_format))

    # `force=True` descarta handlers pré-existentes, evitando duplicação
    # caso setup_logging seja chamada mais de uma vez na mesma execução.
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[console_handler, file_handler],
        force=True,
    )


# ---------------------------------------------------------------------------
# Leitura de argumentos
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Lê os argumentos de linha de comando.

    O parâmetro `argv` permite passar uma lista explícita em testes.
    Quando é None, o argparse lê de `sys.argv[1:]` (comportamento padrão).
    """
    parser = argparse.ArgumentParser(
        prog="g1-scraper",
        description="Coleta resultados de busca do G1 para o NetLab UFRJ.",
    )

    parser.add_argument(
        "--termo", default=TERMO_BUSCA,
        help=f"Termo de busca (padrão: {TERMO_BUSCA})",
    )
    parser.add_argument(
        "--max-pages", type=int, default=MAX_PAGES,
        help=f"Número máximo de páginas (padrão: {MAX_PAGES})",
    )
    parser.add_argument(
        "--output-dir", default="data/output",
        help="Diretório de saída para JSON e CSV (padrão: data/output)",
    )
    parser.add_argument(
        "--reference", default="data/reference/reference_lgpd.json",
        help="Caminho para a amostra de referência (ground truth).",
    )
    parser.add_argument(
        "--no-quality", action="store_true",
        help="Pula a avaliação de qualidade dos dados.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Habilita logs em nível DEBUG.",
    )

    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Diagnóstico pós-coleta
# ---------------------------------------------------------------------------

def _log_field_coverage(logger: logging.Logger, resultados: list) -> None:
    """
    Loga a proporção de campos preenchidos em cada registro.

    Serve como alarme precoce de "drift parcial" — quando o G1 muda o HTML
    de forma que os títulos continuam funcionando, mas os resumos ou datas
    somem. Os registros parecem válidos à primeira vista, mas a completude
    despenca. Sem esse alerta, o problema só aparece ao inspecionar o CSV.

    Campos checados: resumo, data_publicacao_iso, veiculo.
    """
    if not resultados:
        return

    total = len(resultados)
    resumo_ok = sum(1 for r in resultados if r.resumo)
    data_ok = sum(1 for r in resultados if r.data_publicacao_iso)
    veiculo_ok = sum(1 for r in resultados if r.veiculo)

    logger.info(
        "Cobertura de campos: resumo=%d/%d | data=%d/%d | veiculo=%d/%d",
        resumo_ok, total, data_ok, total, veiculo_ok, total,
    )

    # Limite heurístico: abaixo de 50% de cobertura em qualquer campo,
    # provavelmente algo mudou no HTML do G1 e os seletores precisam de ajuste.
    for nome, ok in (("resumo", resumo_ok), ("data", data_ok), ("veiculo", veiculo_ok)):
        if ok / total < 0.5:
            logger.warning(
                "Apenas %d/%d registros com '%s' preenchido. "
                "Verifique os seletores em config.SELECTORS.",
                ok, total, nome,
            )


# ---------------------------------------------------------------------------
# Função Principal
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Executa a rotina completa. Retorna 0 em sucesso, 1 em falha."""
    # Passo 1 — parseia argumentos ANTES de configurar logging, para
    # saber se --verbose foi passado.
    args = parse_args(argv)

    # Passo 2 — configura logging (a pasta logs/ é criada aqui).
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger("run")

    logger.info("=" * 60)
    logger.info("Iniciando g1-scraper")
    logger.info(
        "Termo: %s | Max pages: %d | Output: %s",
        args.termo, args.max_pages, args.output_dir,
    )

    # Passo 3 — loga os seletores ativos para auditoria e diagnóstico.
    # Se a coleta falhar, o log mostra com quais seletores estávamos tentando.
    logger.info("Seletores ativos (config.SELECTORS):")
    for campo, seletor in SELECTORS.items():
        logger.info("  %-12s %s", campo, seletor)
    logger.info("=" * 60)

    # Passo 4 — coleta com tratamento de exceção de topo.
    try:
        resultados = collect(termo=args.termo, max_pages=args.max_pages)
    except Exception:
        logger.exception("Falha fatal durante a coleta")
        return 1

    # Passo 5 — zero resultados é falha explícita, não sucesso silencioso.
    if not resultados:
        logger.error(
            "Nenhum resultado coletado. Verifique os seletores em "
            "src/g1_scraper/config.py e se a página é renderizada via JavaScript."
        )
        return 1

    logger.info("Coleta concluída: %d registros únicos.", len(resultados))

    # Passo 6 — alarme precoce de drift parcial (campos opcionais nulos em massa).
    _log_field_coverage(logger, resultados)

    # Passo 7 — persistência em JSON e CSV.
    output_dir = Path(args.output_dir)
    json_path = output_dir / f"g1_{args.termo}.json"
    csv_path = output_dir / f"g1_{args.termo}.csv"

    try:
        save_json(resultados, json_path)
        save_csv(resultados, csv_path)
    except Exception:
        logger.exception("Falha ao salvar os resultados")
        return 1

    logger.info("Arquivos salvos em: %s e %s", json_path, csv_path)

    # Passo 8 — avaliação de qualidade (opcional; falha aqui NÃO é fatal).
    if args.no_quality:
        logger.info("Avaliação de qualidade pulada (--no-quality).")
    else:
        reference = Path(args.reference)
        # Se a amostra de referência não existe, avisa e pula a métrica
        # de acurácia sem poluir o log com traceback.
        if not reference.exists():
            logger.warning(
                "Amostra de referência não encontrada em %s. "
                "Métricas dependentes dela (acurácia) serão puladas.",
                reference,
            )
        try:
            logger.info("Avaliando qualidade dos dados...")
            metrics = evaluate(
                data_path=json_path,
                reference_path=reference if reference.exists() else None,
            )
            logger.info("Métricas de qualidade:")
            for name, value in metrics.items():
                logger.info("  %-25s %s", name, value)
        except Exception:
            logger.exception("Falha ao avaliar qualidade (não é fatal)")

    logger.info("=" * 60)
    logger.info("Execução finalizada com sucesso.")
    logger.info("=" * 60)
    return 0


# ---------------------------------------------------------------------------
# Ponto de entrada do script
# ---------------------------------------------------------------------------

# Este bloco só roda quando o arquivo é executado diretamente (`python run.py`).
if __name__ == "__main__":
    sys.exit(main())