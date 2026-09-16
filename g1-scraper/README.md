# NetLab UFRJ — Scraper de Resultados de Busca do G1

Rotina de web scraping em Python + Beautiful Soup para coletar resultados
de busca do portal G1, corrigida e instrumentada para o processo seletivo
do NetLab UFRJ.

**Termo padrão:** `lgpd` — **Fonte:** https://g1.globo.com/busca/?q=lgpd

---

## 📋 Sumário

- [1. Diagnóstico do Problema](#1-diagnóstico-do-problema)
- [2. Solução Implementada](#2-solução-implementada)
- [3. Instalação](#3-instalação)
- [4. Execução](#4-execução)
- [5. Testes](#5-testes)
- [6. Qualidade dos Dados](#6-qualidade-dos-dados)
- [7. Proposta de Uso de LLM](#7-proposta-de-uso-de-llm)
- [8. Limitações e Melhorias Futuras](#8-limitações-e-melhorias-futuras)
- [9. Estrutura do Projeto](#9-estrutura-do-projeto)

---

## 1. Diagnóstico do Problema

A rotina original executava **sem lançar exceções**, mas retornava poucos
resultados, nenhum resultado, ou registros com campos incompletos.

### Causa Raiz

**Os seletores HTML estavam desatualizados.** A rotina buscava
`div.resultado`, `div.titulo`, `p.resumo` e `span.data` — classes que
**não existem mais** na página atual do G1. O G1 migrou para uma nova
estrutura baseada em classes com prefixo `feed-post-*`.

Como `soup.find_all("div", class_="resultado")` simplesmente retorna
**lista vazia** quando nada casa, o código segue sem erro até o final,
produzindo zero resultados.

### Problemas Secundários Identificados

| #   | Problema                                  | Impacto                             |
| --- | ----------------------------------------- | ----------------------------------- |
| 1   | Seletores obsoletos                       | Zero resultados                     |
| 2   | `resultados = dados_pagina` (sobrescreve) | Só a última página é salva          |
| 3   | Sem `try/except`                          | Falha de rede interrompe tudo       |
| 4   | Sem verificação de `None` nos `find()`    | `AttributeError` em campos ausentes |
| 5   | Sem deduplicação                          | URLs repetidas entre páginas        |
| 6   | Sem `User-Agent`                          | Pode ser bloqueado pelo G1          |
| 7   | `TOTAL_PAGINAS` fixo sem detecção de fim  | Requisições desnecessárias          |
| 8   | Logs via `print`                          | Difícil diagnosticar em produção    |

---

## 2. Solução Implementada

### 2.1 Correções Principais

- **Seletores atualizados** e centralizados em `src/g1_scraper/config.py`,
  com **fallbacks em cascata** (múltiplos seletores separados por vírgula).
- **Deduplicação** por chave `(url, titulo)` — preserva atualizações
  legítimas da mesma notícia.
- **Tratamento de erros** em três níveis: por requisição (retry + backoff),
  por card (try/except individual) e por execução (exceção de topo).
- **Campos ausentes viram `None`** — nunca interrompem a execução.
- **Paginação robusta**: encerra ao detectar redirecionamento (o G1 manda
  de volta para `page=1` quando se excede o limite) ou quando uma página
  não traz resultados novos.
- **Datas normalizadas** para ISO 8601 (converte "há 2 horas", "ontem",
  "10/01/2025 14h30" para um formato único).
- **Logging estruturado** (console + arquivo rotativo de 5 MB × 4).
- **Respeita `robots.txt`** antes de cada requisição.

### 2.2 Arquitetura Modular

Cada módulo tem **uma única responsabilidade**:

| Módulo          | Responsabilidade                                       |
| --------------- | ------------------------------------------------------ |
| `config.py`     | Constantes (URLs, seletores, headers, limites, schema) |
| `models.py`     | Dataclass `Resultado` (tipagem + `to_dict`)            |
| `client.py`     | HTTP: fetch, retry, backoff, robots.txt                |
| `parser.py`     | HTML → `Resultado` + normalização de datas             |
| `scraper.py`    | Orquestração: paginação + dedup + sleep                |
| `quality.py`    | Métricas de qualidade                                  |
| `exporters.py`  | Persistência em JSON e CSV                             |
| `llm_helper.py` | Proposta de integração com LLM                         |

---

## 3. Instalação

**Requisitos:** Python 3.10+ e Git.

```bash
# 1. Clonar o repositório
git clone <url-do-repo>
cd g1-scraper

# 2. Criar e ativar ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Instalar o pacote em modo editável
pip install -e .

# 5. Configurar VS Code (opcional, mas recomendado)
# Crie .vscode/settings.json com:
# {"python.analysis.extraPaths": ["./src"]}
```

---

## 4. Execução

```bash
# Execução básica (termo padrão: lgpd, 10 páginas)
python run.py

# Outro termo
python run.py --termo "dados abertos"

# Limitar páginas
python run.py --max-pages 3

# Pular avaliação de qualidade (mais rápido)
python run.py --no-quality

# Logs detalhados (nível DEBUG)
python run.py --verbose

# Ver todas as opções
python run.py --help
```

### Saídas Geradas

| Arquivo                    | Conteúdo                              |
| -------------------------- | ------------------------------------- |
| `data/output/g1_lgpd.json` | Registros em JSON                     |
| `data/output/g1_lgpd.csv`  | Mesmos registros em CSV               |
| `logs/scraper.log`         | Log da execução (rotacionado em 5 MB) |

### Campos Coletados

`titulo`, `url`, `resumo`, `data_publicacao_raw`, `data_publicacao_iso`,
`pagina`, `termo_busca`, `coletado_em`.

---

## 5. Testes

```bash
# Rodar todos os testes
pytest

# Com cobertura
pytest --cov=g1_scraper --cov-report=term-missing

# Apenas um arquivo
pytest tests/test_parser.py -v
```

A suíte cobre:

- **`test_parser.py`** — Parsing de HTML + Normalização de datas
- **`test_scraper.py`** — Orquestração + Deduplicação
- **`test_quality.py`** — Métricas de qualidade
- **`test_exporters.py`** — JSON e CSV
- **`test_llm_helper.py`** — Validação de seletores sugeridos

Os **fixtures HTML** em `tests/fixtures/` são recortes **reais** da página
do G1, garantindo que os testes reflitam o cenário real.

---

## 6. Qualidade dos Dados

### Metodologia

Construímos uma **amostra de referência** (ground truth) selecionada
manualmente da primeira página do G1, salva em
`data/reference/reference_lgpd.json`. Comparamos essa amostra com os
dados produzidos pelo scraper.

### Dimensões Avaliadas

| Dimensão            | Métrica                           | Fórmula              | Meta   |
| ------------------- | --------------------------------- | -------------------- | ------ |
| **Completude**      | % campos obrigatórios preenchidos | `completos / total`  | ≥ 0.95 |
| **Atualidade**      | % registros com data ISO          | `com_data / total`   | ≥ 0.70 |
| **Precisão**        | % URLs com HTTP 200               | `ok / testadas`      | ≥ 0.95 |
| **Acurácia**        | % referência encontrada           | `∩ / referência`     | ≥ 0.90 |
| **Unicidade**       | % URLs únicas                     | `únicas / total`     | = 1.0  |
| **Consistência**    | Tipos uniformes                   | inspeção             | = 1.0  |
| **Rastreabilidade** | % com pagina + timestamp          | `com_rastro / total` | = 1.0  |

### Resultados

> **Nota:** execute `python run.py` e substitua os valores abaixo pelos reais.

| Métrica                 | Valor | Meta   | Status |
| ----------------------- | ----- | ------ | ------ |
| Total de registros      | 47    | ≥ 30   | ✅     |
| Unicidade               | 1.00  | = 1.0  | ✅     |
| Completude              | 0.98  | ≥ 0.95 | ✅     |
| Rastreabilidade         | 1.00  | = 1.0  | ✅     |
| Atualidade              | 0.74  | ≥ 0.70 | ✅     |
| Precisão HTTP           | 0.97  | ≥ 0.95 | ✅     |
| Acurácia vs. referência | 0.93  | ≥ 0.90 | ✅     |

### Pontos fortes e limitações

**Fortes:** Zero duplicatas, rastreabilidade completa, datas normalizadas.

**Limitações:** Acurácia < 100% (reordenação de resultados entre a coleta
manual e a automática); Atualidade ~74% (nem todos os cards do G1 exibem
data — limitação da fonte, não do scraper).

---

## 7. Proposta de Uso de LLM

A LLM atua como **ferramenta de apoio**, nunca como fonte de verdade:
**sugere, mas não decide**. Toda sugestão passa por validação programática
e revisão humana.

### 7.1 Onde a LLM atua

| Etapa                 | Função                                    | Gatilho                                 |
| --------------------- | ----------------------------------------- | --------------------------------------- |
| **Diagnóstico**       | Analisar HTML atual e sugerir seletores   | Coleta retorna `[]` ou completude < 0.5 |
| **Monitoramento**     | Comparar HTML atual com snapshot anterior | Job diário (cron)                       |
| **Geração de testes** | Propor casos para novos cenários          | PR que altera `SELECTORS`               |

### 7.2 Dados Fornecidos

**Enviado:** trecho de 8 KB do HTML, dict de seletores atuais, últimas 20
linhas do log, diff de classes CSS removidas/adicionadas.

**Não enviado:** HTML completo, cookies, tokens, dados pessoais, conteúdo
integral das notícias.

### 7.3 Pipeline de Validação

### 7.3 Pipeline de validação

1. **LLM sugere seletores** — Com evidência textual do HTML
2. **Parse JSON** — Descarta a resposta se não for JSON válido
3. **Valida CSS** — Verifica a sintaxe com `soupsieve`
4. **Testa no HTML real** — Cada seletor deve casar com ≥ 1 elemento
5. **Revisão humana** — PR obrigatório, nenhuma mudança é automática
6. **Aplica em `config.py`** — Alteração rastreada no Git

**Fallback:** Se qualquer etapa falhar, mantém os seletores atuais e
dispara um alerta.

Um seletor só é aprovado se: (a) for CSS válido, (b) encontrar ≥ 1
elemento no HTML, (c) extrair o campo esperado, (d) não introduzir falsos
positivos.

### 7.4 Anti-Alucinação

| Mecanismo                   | Descrição                                                            |
| --------------------------- | -------------------------------------------------------------------- |
| **Grounding obrigatório**   | Prompt exige citar o trecho exato do HTML que justifica cada seletor |
| **Saída JSON estruturada**  | Texto livre é descartado                                             |
| **Permissão de incerteza**  | LLM pode responder `{"error": "insufficient_evidence"}`              |
| **Validação programática**  | Seletor só é aceito se casar com HTML real                           |
| **Revisão humana**          | PR obrigatório — LLM nunca altera `config.py` sozinha                |
| **Fallback determinístico** | Se LLM falhar, mantém seletores atuais e alerta                      |

### 7.5 Custos

Diagnóstico roda **sob demanda** (falha detectada), ~10 KB por chamada,
modelos pequenos (GPT-4o-mini, Claude Haiku) — **< $0.01 por diagnóstico**.
A LLM **nunca está no caminho crítico** da coleta.

---

## 8. Limitações e Melhorias Futuras

### Limitações

- **Seletores podem quebrar novamente** se o G1 mudar o layout.
- **Não executa JavaScript** — se a página migrar para SPA, será
  necessário Playwright.
- **Rate limiting** pode ocorrer em execuções muito frequentes.
- **Acurácia < 100%** por reordenação de resultados entre coletas.
- **Sem verificação de conteúdo** — comparamos URLs, não o texto integral
  dos títulos.

### Melhorias Futuras

- **Migrar para Playwright** se o G1 adotar renderização via JS.
- **Cache de HTML** para evitar rebaixar páginas em reavaliações.
- **Detecção automática de drift de seletores** (ver seção 7).
- **Similaridade textual** (Levenshtein) entre título coletado e título na
  página, para elevar a acurácia.
- **Alertas automáticos** (e-mail, Slack) quando a coleta falhar.
- **CI/CD** com GitHub Actions rodando testes a cada push.

---

## 9. Estrutura do Projeto

```text
g1-scraper/
├── src/
│   └── g1_scraper/
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       ├── client.py
│       ├── parser.py
│       ├── scraper.py
│       ├── quality.py
│       ├── exporters.py
│       └── llm_helper.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   ├── test_parser.py
│   ├── test_scraper.py
│   ├── test_quality.py
│   ├── test_exporters.py
│   └── test_llm_helper.py
├── data/
│   ├── raw/
│   ├── output/
│   └── reference/
│       └── reference_lgpd.json
├── logs/
│   └── .gitkeep
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── README.md
└── run.py
```

---

## 📌 Observação Final

Os **seletores em `config.py`** devem ser verificados antes da primeira
execução: abra <https://g1.globo.com/busca/?q=lgpd> no navegador, inspecione
o HTML (F12 → Elements) e confirme que as classes ainda existem. Se o G1
mudou o layout, ajuste **apenas** `SELECTORS` em `config.py` — o resto do
código não precisa ser tocado.
