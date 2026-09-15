# 🧩 ARC-AGI-1: CEGIS com Regularização Indutiva Anti-Trapaça

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Benchmark ARC-AGI](https://img.shields.io/badge/benchmark-ARC--AGI--1-orange.svg)](https://arcprize.org/)
[![Artigo PDF](https://img.shields.io/badge/artigo-PDF-red.svg)](docs/artigo.pdf)

**Avaliação Experimental do CEGIS com Prompt Anti-Trapaça na Resolução do ARC-AGI**.

 Este estudo investiga a injeção de restrições semânticas Anti-Trapaça (*Anti-Cheat*) no laço de refinamento **CEGIS** (*Counterexample-Guided Inductive Synthesis*) mediado por LLMs, atuando como um **regularizador** que previne atalhos superficiais e destrava a convergência de algoritmos universais no benchmark **ARC-AGI-1**.

---

## Abordagem Proposta e Isolamento de Variáveis

| Estratégia | Prompt Inicial  | Feedback de Contraexemplo  |
| :--- | :---: | :---: |
| **CEGIS Padrão** *(Controle)* | Sem regras Anti-Cheat | Entrada, Saída Esperada, Saída Produzida |
| **CEGIS Anti-Trapaça** *(Proposto)* | **Sem regras Anti-Cheat** | Entrada, Saída Esperada, Saída Produzida + Regras Anti-Trapaça |

>  O prompt da iteração inicial é **idêntico** em ambas as estratégias. Como na primeira tentativa o modelo não possui acesso às respostas esperadas (gabarito), as regras anti-trapaça são injetadas somente a partir do primeiro feedback semântico.

---

## Resultados Principais (100 Tarefas)

A aplicação do prompt Anti-Trapaça elevou a acurácia de generalização no teste oculto e reduziu a oscilação por ajustes locais sem adicionar custos adicionais de inferência:

| Métrica | Gemini 3.1 Flash-Lite (Padrão) | Gemini 3.1 Flash-Lite (Anti-Trapaça) | \\(\Delta\\) Gemini | Gemma 4 26B (Padrão) | Gemma 4 26B (Anti-Trapaça) | \\(\Delta\\) Gemma |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Acurácia (Teste Oculto)** | **47,0%** | **55,0%** | **+8,0%** | **31,0%** | **40,0%** | **+9,0%** |
| **Convergência no Treino** | 52,0% | 56,0% | +4,0% | 32,0% | 41,0% | +9,0% |
| **Falsas Convergências (FC)** | **6** | **2** | **-66,7%** | 2 | 2 | 0,0% |
| **Requisições à API (Total)** | 318 | 303 | **-4,7%** | 381 | 361 | **-5,2%** |

### 💡 A Descoberta
O ganho de desempenho não veio apenas de evitar fraudes no teste, mas sim de **destravar a convergência de treino** (responsável por 80% a 90% do aumento de acurácia). Ao proibir remendos locais baseados no gabarito, o prompt força o modelo a abandonar ciclos de correções infrutíferas e encontrar operadores geométricos universais.

---

## Estrutura do Repositório

```text
.
├── main.py                          # Ponto de entrada do experimento principal
├── arc_cegis/                       # Pacote central do ciclo CEGIS
│   ├── experiment.py                # Motor do ciclo CEGIS (Padrão vs Anti-Trapaça)
│   ├── prompts.py                   # Construção de prompts e injeção de regras
│   ├── sandbox.py                   # Execução isolada em subprocesso (timeout 2.0s)
│   ├── llm.py                       # Gestão de APIs (Gemini) e Rate-Limiting 
│   ├── data_loader.py               # Carregamento e validação dos pares ARC-AGI
│   └── config.py                    # Parâmetros de execução e Poda de Contexto
├── analysis/                        # Análise de falsa convergência e métricas
│   └── analyze_false_convergence.py # Auditoria automatizada via LLM-as-a-Judge (JSON)
├── docs/                            # Documentação científica e metodológica
├── experiments/                     # Dados brutos e relatórios dos experimentos
└── data/                            # Tarefas canônicas do ARC-AGI-1 (JSON)
```

---

## Setup & Execução

### 1. Instalar Dependências

```bash
pip install -r requirements.txt

```

### 2. Configurar Variáveis de Ambiente (`.env`)

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
GEMINI_API_KEY="sua_chave_aqui"
MAX_CEGIS_ITERS=5
REQUEST_DELAY=2.0
MAX_DAILY_REQUESTS=14400

```

### 3. Executar o Experimento Comparativo

**Comparação oficial (100 tarefas):**

```bash
python3 main.py --tasks ./data --max-tasks 100 --output results_experiment.json

```

**Teste rápido (5 tarefas):**

```bash
python3 main.py --tasks ./data --max-tasks 5 --no-resume --output test_results.json

```

### 4. Executar Auditoria Qualitativa (LLM-as-a-Judge)

```bash
python3 analysis/analyze_false_convergence.py results_experiment.json --verbose

```
