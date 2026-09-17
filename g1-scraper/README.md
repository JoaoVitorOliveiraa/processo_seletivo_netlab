# NetLab UFRJ — Scraper de Resultados de Busca do G1

Rotina de Web Scraping em Python para coletar resultados de busca do
portal G1, corrigida e instrumentada para o processo seletivo do
NetLab UFRJ.

**Termo padrão:** `lgpd` — **Fonte:** <https://g1.globo.com/busca/?q=lgpd>

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

**Três problemas independentes** fazem a rotina original falhar silenciosamente:

**1. Seletores obsoletos.** O código original buscava `div.resultado`,
`div.titulo`, `p.resumo` e `span.data` — classes que **não existem mais**
na página atual do G1. Após inspeção manual do HTML real (via DevTools),
os seletores corretos foram identificados como pertencentes ao framework
`widget--info__*`:

| Campo     | Seletor atual                   |
| --------- | ------------------------------- |
| Container | `li[id^='search-result-item-']` |
| Título    | `div.widget--info__title`       |
| Resumo    | `p.widget--info__description`   |
| Veículo   | `div.widget--info__header`      |
| Data      | `div.widget--info__meta > span` |

**2. URLs de tracking.** Todos os links do G1 são envolvidos por um wrapper
de redirecionamento (`https://measures.globo.com/v1/click?...&u=<URL_REAL>`).
A URL real está **URL-encoded** no parâmetro `u=`. Sem decodificá-la, o
CSV resultante fica cheio de URLs inúteis e a métrica de precisão HTTP
falha (o domínio `measures.globo.com` exige autenticação). O scraper
corrigido decodifica esse parâmetro automaticamente.

**3. Página renderizada via JavaScript (SSR + hydration).** A inspeção do
HTML retornado pelo `requests` mostrou que a página de busca do G1 **não
contém os cards no HTML inicial** — apenas o esqueleto da página (metadados
de configuração e URLs de assets). Os dados são injetados **depois** pelo
JavaScript do navegador.

O diagnóstico foi feito com cinco testes independentes (`debug_g1.py`,
`debug_g1_v2.py`, `debug_g1_v4.py`, `debug_paginacao.py`,
`debug_parametros.py`):

| Teste                                         | Hipótese descartada      | Resultado                                                              |
| --------------------------------------------- | ------------------------ | ---------------------------------------------------------------------- |
| `requests` com User-Agent básico              | Bloqueio simples         | 0 cards, sem "lgpd"                                                    |
| `requests` com headers completos de navegador | Bloqueio por headers     | 0 cards, sem "lgpd"                                                    |
| `requests` com `Referer` + `Sec-Fetch-*`      | Bloqueio por anti-bot    | 0 cards, sem "lgpd"                                                    |
| Busca de dados embutidos em `<script>`        | SSR puro (dados no HTML) | Nenhum JSON de resultados                                              |
| Variações de parâmetro de paginação           | Paginação via URL        | `page`, `from`, `offset`, `start`, `p`, `pagina` — **todos ignorados** |

**Conclusões:**

- A página é uma SPA — `requests` sozinho não funciona.
- A paginação **não é mais via URL** — é via **botão "Veja mais"**
  (`button.pagination__load-more`), que carrega mais resultados via JS.

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
| 9   | URLs de tracking não decodificadas        | CSV com links inúteis               |
| 10  | `requests` sem executar JavaScript        | Zero cards em SPAs                  |

---

## 2. Solução Implementada

### 2.1 Correções Principais

- **Seletores atualizados** e centralizados em `src/g1_scraper/config.py`,
  extraídos do **HTML real do G1** via inspeção manual (DevTools).
- **Decodificação de URLs de tracking** — extrai a URL real do parâmetro
  `u=` do wrapper `measures.globo.com`.
- **Playwright (Chromium headless)** para renderizar o JavaScript da SPA
  no `client.py`. O Beautiful Soup continua sendo usado no `parser.py` —
  a extração de dados é feita sobre o HTML já renderizado.
- **Paginação via clique** no botão "Veja mais"
  (`button.pagination__load-more`), acumulando resultados em uma única
  sessão de navegador.
- **Deduplicação** por chave `(url, titulo)` — preserva atualizações
  legítimas da mesma notícia.
- **Tratamento de erros** em três níveis: por requisição (retry + backoff),
  por card (try/except individual) e por execução (exceção de topo).
- **Campos ausentes viram `None`** — nunca interrompem a execução.
- **Datas normalizadas** para ISO 8601 (converte "há 2 horas", "ontem",
  "25/08/2026 16:27" para um formato único).
- **Alerta de drift parcial** — o `run.py` avisa quando a cobertura de
  campos opcionais cai abaixo de 50%.
- **Logging estruturado** (console + arquivo rotativo de 5 MB × 4).
- **Respeita `robots.txt`** antes de cada requisição.

### 2.2 Arquitetura Modular

Cada módulo tem **uma única responsabilidade**:

| Módulo          | Responsabilidade                                                   |
| --------------- | ------------------------------------------------------------------ |
| `config.py`     | Constantes (URLs, seletores, headers, limites, schema)             |
| `models.py`     | Dataclass `Resultado` (tipagem + `to_dict`)                        |
| `client.py`     | HTTP + Playwright: renderização, clique em "Veja mais", robots.txt |
| `parser.py`     | HTML → `Resultado` + normalização de datas + decode de tracking    |
| `scraper.py`    | Orquestração: fetch paginado + deduplicação                        |
| `quality.py`    | Métricas de qualidade                                              |
| `exporters.py`  | Persistência em JSON e CSV                                         |
| `llm_helper.py` | Proposta de integração com LLM                                     |

**Nota:** a paginação via clique em "Veja mais" é responsabilidade do
`client.py` — o `scraper.py` apenas recebe o HTML acumulado e aplica
deduplicação. Essa decisão reflete o fato de que a paginação agora é uma
operação **do navegador** (não da URL).

---

## 3. Instalação

**Requisitos:** Python 3.12 (recomendado) e Git.

> **Nota sobre a versão do Python:** o projeto requer **Python 3.12** ou
> superior. **Evite o Python 3.13** — algumas dependências compiladas
> (como `greenlet`) ainda não têm wheels pré-compilados para essa versão
> no Windows, forçando compilação local que exige o Visual C++ Build Tools
> e falha se ele não estiver instalado. Você pode confirmar quais versões
> do Python estão instaladas com `py -0` (Windows).
>
> **Importante:** o `.venv` deve ser criado **na raiz do projeto** (mesma
> pasta que contém `pyproject.toml`, `run.py` e `src/`). Criar o `.venv`
> em uma pasta pai causa `ModuleNotFoundError` porque o pacote não fica
> registrado no ambiente correto.

```bash
# 1. Clonar o repositório
git clone <url-do-repo>
cd g1-scraper

# 2. Criar ambiente virtual com Python 3.12
py -3.12 -m venv .venv          # Windows
python3.12 -m venv .venv        # Linux/Mac

# 3. Ativar o ambiente virtual
source .venv/bin/activate       # Linux/Mac
.venv\Scripts\activate          # Windows
```

**⚠️ Verificação obrigatória:** confirme que o venv está usando o
**Python 3.12** antes de prosseguir:

```bash
python --version
# Saída esperada: Python 3.12.8
```

Se aparecer `Python 3.13.x`, o venv foi criado com a versão errada.
Apague-o (`Remove-Item -Recurse -Force .venv` no Windows ou
`rm -rf .venv` no Linux/Mac) e recrie com `py -3.12 -m venv .venv`.

```bash
# 4. Instalar dependências
pip install -r requirements.txt

# 5. Instalar o Chromium do Playwright (~150 MB, uma vez só)
playwright install chromium

# 6. Instalar o pacote em modo editável
pip install -e .

# 7. Configurar VS Code (opcional, mas recomendado)
# Crie .vscode/settings.json com:
# {"python.analysis.extraPaths": ["./src"]}
```

### Troubleshooting

**`ModuleNotFoundError: No module named 'g1_scraper'`**

Falta rodar `pip install -e .` no `.venv` ativo. O comando registra o
pacote no venv — permitindo importá-lo de qualquer lugar. Confirme com:

```bash
pip list | grep g1-scraper
# Saída esperada: g1-scraper 0.1.0 /caminho/para/g1-scraper/src
```

**`ModuleNotFoundError: No module named 'greenlet._greenlet'`**

O `.venv` foi criado com Python 3.13 (muito recente — sem wheels
pré-compilados para `greenlet` no Windows). Confirme com
`python --version` — se aparecer `3.13.x`, recrie o venv com
`py -3.12 -m venv .venv`.

**`Error: Microsoft Visual C++ 14.0 or greater is required`**

O pip tentou compilar o `greenlet` do source. Confirme a versão do
Python (`python --version` deve ser `3.12.x`). Se for 3.13, recrie o
`.venv` com Python 3.12.

**`playwright._impl._api_types.Error: Executable doesn't exist`**

O Chromium não foi baixado. Rode:

```bash
playwright install chromium
```

**`SyntaxError` ao rodar comandos `python -c "..."` com aspas**

O terminal (especialmente PowerShell) tem dificuldade com aspas aninhadas.
Prefira criar um arquivo `.py` e rodá-lo, em vez de usar `python -c "..."`.

**Se o passo 5 falhar**, verifique se o Playwright foi instalado:

```bash
playwright --version
# Saída esperada: Version 1.45.x
```

---

## 4. Execução

```bash
# Execução básica (termo padrão: lgpd, 10 páginas/cliques)
python run.py

# Outro termo
python run.py --termo "dados abertos"

# Limitar cliques em "Veja mais"
python run.py --max-pages 3

# Pular avaliação de qualidade (mais rápido)
python run.py --no-quality

# Logs detalhados (nível DEBUG)
python run.py --verbose

# Ver todas as opções
python run.py --help
```

**Tempo esperado:** com Playwright, cada página leva **2-5 segundos** para
renderizar (o navegador precisa executar o JavaScript e aguardar os cards).
Uma coleta com `--max-pages 3` roda em ~15-20 segundos.

### Saídas Geradas

| Arquivo                    | Conteúdo                              |
| -------------------------- | ------------------------------------- |
| `data/output/g1_lgpd.json` | Registros em JSON                     |
| `data/output/g1_lgpd.csv`  | Mesmos registros em CSV               |
| `logs/scraper.log`         | Log da execução (rotacionado em 5 MB) |

### Campos Coletados

| Campo                 | Descrição                                      |
| --------------------- | ---------------------------------------------- |
| `titulo`              | Título da notícia                              |
| `url`                 | URL real da notícia (decodificada do tracking) |
| `resumo`              | Primeiras linhas do conteúdo                   |
| `veiculo`             | Veículo emissor (ex.: "G1", "MGTV 1ª Edição")  |
| `data_publicacao_raw` | Data no formato exibido na página              |
| `data_publicacao_iso` | Data normalizada para ISO 8601                 |
| `publicitario`        | `true` se o card é patrocinado                 |
| `pagina`              | Página de onde veio o resultado                |
| `termo_busca`         | Termo usado na busca                           |
| `coletado_em`         | Timestamp da coleta                            |

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

- **`test_parser.py`** — Parsing de HTML + Decodificação de URLs + Normalização de datas
- **`test_scraper.py`** — Orquestração + Deduplicação
- **`test_quality.py`** — Métricas de qualidade
- **`test_exporters.py`** — JSON e CSV
- **`test_llm_helper.py`** — Validação de seletores sugeridos

**Resultado atual: 42 testes passando em ~0.5s.**

Os **fixtures HTML** em `tests/fixtures/` são recortes **reais** da página
do G1, garantindo que os testes reflitam o cenário real. Os testes são
**offline** — usam `monkeypatch` para isolar rede e Playwright.

---

## 6. Qualidade dos Dados

### Metodologia

Construímos uma **amostra de referência** (ground truth) com **16 registros
únicos** selecionados manualmente das páginas 1 e 2 do G1, salva em
`data/reference/reference_lgpd.json`. Comparamos essa amostra com os dados
produzidos pelo scraper.

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

### Resultados Obtidos

Execução: `python run.py --max-pages 3`

| Métrica                 | Valor | Meta   | Status |
| ----------------------- | ----- | ------ | ------ |
| Total de registros      | 40    | ≥ 30   | ✅     |
| Unicidade               | 1.00  | = 1.0  | ✅     |
| Completude              | 1.00  | ≥ 0.95 | ✅     |
| Rastreabilidade         | 1.00  | = 1.0  | ✅     |
| Precisão HTTP           | 1.00  | ≥ 0.95 | ✅     |
| Acurácia vs. referência | 1.00  | ≥ 0.90 | ✅     |

**Todas as métricas atingiram a meta.** Os 40 registros cobrem
integralmente os 16 da amostra de referência e mais 24 resultados
adicionais.

### Pontos Fortes e Limitações

**Fortes:**

- Zero duplicatas (dedup por `(url, titulo)`).
- Completude total — resumo, veículo e data preenchidos em 40/40 registros.
- Rastreabilidade completa — todo registro tem `pagina` e `coletado_em`.
- Precisão HTTP 100% — todas as 40 URLs respondem 200.
- Acurácia 100% — todos os 16 registros da referência foram capturados.

**Limitações:**

- O `pagina` é sempre `1` (a paginação via clique não expõe a página
  individual — o número real da página é a ordem de aparição).
- Datas relativas ("há 12 horas") dependem do momento da coleta — se você
  rodar em outro dia, a conversão para ISO usa um `now` diferente.

---

## 7. Proposta de Uso de LLM

A LLM atua como **ferramenta de apoio**, nunca como fonte de verdade:
**sugere, mas não decide**. Toda sugestão passa por validação programática
e revisão humana.

### 7.1 Onde a LLM Atua

| Etapa                 | Função                                    | Gatilho                                 |
| --------------------- | ----------------------------------------- | --------------------------------------- |
| **Diagnóstico**       | Analisar HTML atual e sugerir seletores   | Coleta retorna `[]` ou completude < 0.5 |
| **Monitoramento**     | Comparar HTML atual com snapshot anterior | Job diário (cron)                       |
| **Geração de testes** | Propor casos para novos cenários          | PR que altera `SELECTORS`               |

> **Gatilho já implementado:** o `run.py` loga os seletores ativos no início
> da execução e emite um `WARNING` automático quando a cobertura de campos
> opcionais (resumo, data, veículo) cai abaixo de 50%. Esse alerta funciona
> como ponto de entrada para o pipeline de diagnóstico via LLM descrito
> abaixo — nenhuma chamada de API é feita automaticamente; o alerta
> sinaliza que uma análise manual ou assistida é recomendada.

### 7.2 Dados Fornecidos

**Enviado:** trecho de 8 KB do HTML, dict de seletores atuais, últimas 20
linhas do log, diff de classes CSS removidas/adicionadas.

**Não enviado:** HTML completo, cookies, tokens, dados pessoais, conteúdo
integral das notícias.

### 7.3 Pipeline de Validação

1. **LLM sugere seletores** — Com evidência textual do HTML
2. **Parse JSON** — Descarta a resposta se não for JSON válido
3. **Valida CSS** — Verifica a sintaxe com `soupsieve`
4. **Testa no HTML real** — Cada seletor deve casar com ≥ 1 elemento
5. **Revisão humana** — PR obrigatório, nenhuma mudança é automática
6. **Aplica em `config.py`** — Alteração rastreada no Git

**Fallback:** Se qualquer etapa falhar, mantém os seletores atuais e
dispara um alerta.

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

- **Playwright é mais lento que `requests`.** Cada página leva 2-5s para
  renderizar — inerente à execução de JavaScript. Uma coleta com 10
  páginas leva ~30-50s.
- **Seletores podem quebrar novamente** se o G1 mudar o layout. A
  mitigação é o alerta de drift + a proposta de uso de LLM (seção 7).
- **A paginação via clique depende do botão "Veja mais" existir.** Se o
  G1 mudar o mecanismo de paginação, o `client.py` precisa ser ajustado.
- **Chromium do Playwright adiciona ~150 MB** ao ambiente local. Baixado
  uma vez, não versionado no Git.
- **Rate limiting** pode ocorrer em execuções muito frequentes.
- **`pagina` sempre retorna 1.** Como a paginação é feita em uma única
  sessão, o scraper não sabe em qual "página lógica" cada card estava.
- **Acurácia < 100% em reordenações.** Entre a coleta manual da amostra
  de referência e a coleta automática, o G1 pode reordenar resultados.

### Melhorias Futuras

- **Mapear a "página lógica" de cada card** — durante a paginação,
  marcar cada resultado com o número do clique em que ele apareceu.
- **Cache de HTML renderizado** — evita re-renderizar páginas em
  reavaliações ou debugging.
- **Detecção automática de drift de seletores** — integração com o
  `llm_helper.py` para sugerir novos seletores automaticamente.
- **Similaridade textual** (Levenshtein) entre título coletado e título
  na página, para elevar a acurácia em casos de reordenação.
- **Alertas automáticos** (e-mail, Slack) quando a coleta falhar ou a
  cobertura de campos cair.
- **CI/CD** com GitHub Actions rodando `pytest` a cada push.
- **Suporte a Python 3.13** — aguardar wheels pré-compilados de
  `greenlet` para Windows.

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
│   │   ├── page_1.html
│   │   └── page_missing_fields.html
│   ├── test_parser.py
│   ├── test_scraper.py
│   ├── test_quality.py
│   ├── test_exporters.py
│   └── test_llm_helper.py
├── data/
│   ├── raw/
│   │   └── .gitkeep
│   ├── output/
│   │   └── .gitkeep
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

Se a **paginação** mudar novamente (ex.: deixar de usar o botão "Veja mais"),
o ajuste é apenas no `client.py`, função `_render_with_pagination()`. O
`parser.py` continua idêntico — ele só recebe o HTML acumulado.
