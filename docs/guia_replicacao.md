# Guia de Replicação do Experimento

Este documento descreve, passo a passo, como um pesquisador externo pode replicar completamente o experimento **CEGIS Padrão vs CEGIS Antitrapaça** no benchmark ARC-AGI-1.

---

## 1. Requisitos de Hardware e Software

### Sistema Operacional
- Linux, macOS ou Windows com WSL2
- Testado em: macOS com chip Apple Silicon (ARM64)

### Python
- **Versão mínima**: Python 3.10 (requerido para `tuple[...]` como anotação de tipo nativa)
- Verificar: `python3 --version`

### Dependências Python
```bash
pip install -r requirements.txt
```

Dependências principais:
| Pacote | Versão mínima | Função |
|---|---|---|
| `google-genai` | 1.x | Cliente da API Google Gemini |
| `python-dotenv` | 1.x | Carregamento de variáveis de ambiente |

### API de LLM
O experimento utiliza por padrão a **Google Gemini API**. É necessário:
- Uma conta Google com acesso à API Gemini
- Uma ou mais chaves de API (`GEMINI_API_KEY`)
- O modelo padrão é `gemini-3.1-flash-lite` (Free Tier disponível)

---

## 2. Obtenção dos Dados

### Dataset ARC-AGI-1
```bash
# Clone o repositório oficial do ARC
git clone https://github.com/fchollet/ARC-AGI.git arc-agi-data

# Copie as tasks para o diretório do projeto
cp -r arc-agi-data/data/training/ ./data/training/
cp -r arc-agi-data/data/evaluation/ ./data/evaluation/
```

Cada task é um arquivo JSON com a estrutura:
```json
{
  "train": [
    {"input": [[...]], "output": [[...]]},
    ...
  ],
  "test": [
    {"input": [[...]], "output": [[...]]}
  ]
}
```

O campo `test[*].output` é o alvo avaliado; o modelo **nunca vê** este campo durante a síntese.

---

## 3. Configuração do Ambiente

### 3.1. Arquivo `.env`

Crie um arquivo `.env` na raiz do projeto:

```env
# === LLM PROVIDER ===
GEMINI_API_KEY="sua_chave_aqui"
LLM_PROVIDER="gemini"
MODEL_NAME="gemini-3.1-flash-lite"

# === CEGIS PARAMETERS ===
MAX_CEGIS_ITERS=5
TIMEOUT_SECONDS=2.0

# === RATE LIMITING ===
REQUEST_DELAY=2.0
MAX_DAILY_REQUESTS=14400
MAX_CONCURRENT_TASKS=3
```

### 3.2. Multi-Key Pool (para paralelismo com múltiplas chaves)

Para multiplicar o throughput usando múltiplas chaves API em paralelo:

```env
# Pool de 3 chaves — cada uma com delay de 2s = ~30 req/min total
LLM_POOL="gemini:gemma-4-31b-it,gemini:gemma-4-31b-it,gemini:gemma-4-31b-it"
LLM_POOL_1_API_KEY="chave_1"
LLM_POOL_2_API_KEY="chave_2"
LLM_POOL_3_API_KEY="chave_3"
LLM_POOL_1_REQUEST_DELAY=2.0
LLM_POOL_2_REQUEST_DELAY=2.0
LLM_POOL_3_REQUEST_DELAY=2.0
LLM_POOL_1_MAX_CONCURRENT_TASKS=1
LLM_POOL_2_MAX_CONCURRENT_TASKS=1
LLM_POOL_3_MAX_CONCURRENT_TASKS=1
```

### 3.3. Parâmetros de Configuração Completos

| Variável de Ambiente | Padrão | Descrição |
|---|---|---|
| `GEMINI_API_KEY` | — | Chave da API Google Gemini |
| `LLM_PROVIDER` | `gemini` | Provider (`gemini`) |
| `MODEL_NAME` | `gemini-3.1-flash-lite` | Modelo LLM utilizado |
| `MAX_CEGIS_ITERS` | `5` | Máximo de iterações de refinamento CEGIS |
| `TIMEOUT_SECONDS` | `2.0` | Timeout de execução Python por exemplo |
| `REQUEST_DELAY` | `2.0` | Delay mínimo entre requisições (segundos) |
| `MAX_DAILY_REQUESTS` | `14400` | Teto de requisições diárias (quota guard) |
| `MAX_CONCURRENT_TASKS` | `3` | Número de tarefas executadas em paralelo |
| `LOG_FILE` | `experiment.log` | Arquivo de log do experimento |

---

## 4. Execução do Experimento

### 4.1. Verificação de Ambiente (Health Check)

Antes de iniciar, o `main.py` executa automaticamente um health check que:
1. Valida a chave API com uma requisição mínima
2. Verifica se o modelo responde
3. Checa limites de quota restante

```bash
DOTENV=.env python3 main.py --health-check
```

### 4.2. Execução Principal

```bash
# Experimento comparativo: 100 tasks do conjunto de treinamento
DOTENV=.env python3 main.py \
  --tasks ./data/training \
  --max-tasks 100 \
  --output results_experiment.json \
  --markdown results_report.md
```

### 4.3. Argumentos CLI Completos

| Argumento | Padrão | Descrição |
|---|---|---|
| `--tasks PATH` | `./data` | Diretório das tasks ARC |
| `--max-tasks N` | `100` | Número máximo de tarefas a avaliar |
| `--output FILE` | `results_experiment.json` | Arquivo JSON de saída |
| `--markdown FILE` | — | Gerar relatório Markdown |
| `--model MODEL` | (de `.env`) | Modelo LLM |
| `--max-iters N` | (de `.env`) | Máximo de iterações CEGIS |
| `--no-resume` | `false` | Ignorar checkpoint existente e recomeçar |
| `--workers N` | (de `.env`) | Número de workers paralelos |

### 4.4. Checkpoint e Resumo Automático

O experimento salva o estado após cada tarefa concluída. Em caso de interrupção (rede, quota, ctrl+C), retome sem perda de dados:

```bash
# Retomar de onde parou (comportamento padrão)
DOTENV=.env python3 main.py --tasks ./data --max-tasks 100 --output results_experiment.json

# Forçar reinício do zero
DOTENV=.env python3 main.py --tasks ./data --max-tasks 100 --output results_experiment.json --no-resume
```

O arquivo `results_experiment.json` é atualizado após cada tarefa via rename atômico.

---

## 5. Monitoramento em Tempo Real

O log do experimento exibe, para cada tarefa concluída:

```
[15/100] 007bbfb7: Padrão=FAIL FC!, Antitrapaça=PASS | Iters: P=5 AT=3 | API: 90/14400
```

Onde:
- `[15/100]`: progresso
- `007bbfb7`: task ID
- `Padrão=FAIL FC!`: falhou E teve falsa convergência no Padrão
- `Antitrapaça=PASS`: acertou no Antitrapaça
- `Iters: P=5 AT=3`: iterações usadas por cada variante
- `API: 90/14400`: chamadas API usadas / limite diário

```bash
# Acompanhar em tempo real
tail -f experiment.log
```

---

## 6. Análise dos Resultados

### 6.1. Análise Primária

```bash
# Tabela comparativa completa
python3 analysis/analyze_false_convergence.py results_experiment.json

# Com listagem de task IDs por categoria (para análise qualitativa)
python3 analysis/analyze_false_convergence.py results_experiment.json --verbose
```

### 6.2. Relatório Markdown

O arquivo `results_report.md` (gerado com `--markdown`) contém:
- Tabela de métricas resumidas
- Log por tarefa com emojis indicadores
- Listagem de tarefas problemáticas (api errors, etc.)

### 6.3. Checklist de Verificação dos Resultados

Após o experimento, verifique:

- [ ] `n_completed == max_tasks` (ou pelo menos 95%) — sem muitas tarefas faltantes
- [ ] `api_errors < 5%` — baixa taxa de erros de API
- [ ] `std_converged_train > 20%` — o Padrão conseguiu convergir em pelo menos algumas tarefas (valida que o modelo funciona)
- [ ] `std_false_conv > 0` — existem casos de falsa convergência para medir redução
- [ ] A diferença `fc_fixed - fc_introduced` é computável e interpretável

---

## 7. Configurações de Referência para Replicação

### Configuração Mínima (1 chave Free Tier, ~15 req/min)

```env
GEMINI_API_KEY="..."
MODEL_NAME="gemini-3.1-flash-lite"
MAX_CEGIS_ITERS=5
REQUEST_DELAY=4.0
MAX_CONCURRENT_TASKS=1
MAX_DAILY_REQUESTS=1500
```

Tempo estimado: ~8h para 100 tasks (2 variantes × 100 tasks × 5 iters × 4s delay).

### Configuração Paralela (3 chaves Free Tier, ~45 req/min)

```env
LLM_POOL="gemini:gemini-3.1-flash-lite,gemini:gemini-3.1-flash-lite,gemini:gemini-3.1-flash-lite"
LLM_POOL_1_API_KEY="..."
LLM_POOL_2_API_KEY="..."
LLM_POOL_3_API_KEY="..."
LLM_POOL_1_REQUEST_DELAY=4.0
LLM_POOL_2_REQUEST_DELAY=4.0
LLM_POOL_3_REQUEST_DELAY=4.0
LLM_POOL_1_MAX_CONCURRENT_TASKS=1
LLM_POOL_2_MAX_CONCURRENT_TASKS=1
LLM_POOL_3_MAX_CONCURRENT_TASKS=1
MAX_CONCURRENT_TASKS=3
MAX_DAILY_REQUESTS=4500
```

Tempo estimado: ~3h para 100 tasks.

---

## 8. Estrutura de Arquivos para Replicação

```
cegis-arc-agi-1/
├── .env                        ← Configuração da sua API (crie este arquivo)
├── requirements.txt            ← Instalar com pip install -r requirements.txt
├── main.py                     ← Entry point do experimento
├── data/
│   └── training/               ← Tasks ARC-AGI-1 (obter do repo oficial)
│       ├── 007bbfb7.json
│       └── ...
├── arc_cegis/
│   ├── experiment.py           ← Lógica das duas variantes CEGIS
│   ├── prompts.py              ← Templates de prompt (inicial e feedback)
│   ├── sandbox.py              ← Execução segura de código Python
│   ├── llm.py                  ← Cliente LLM com rate limiting
│   ├── data_loader.py          ← Carregamento das tasks
│   └── config.py               ← Configuração via env vars
├── analysis/
│   └── analyze_false_convergence.py  ← Análise pós-experimento
└── docs/
    ├── hipotese_anticheat.md         ← Hipótese da pesquisa
    ├── metodologia_experimento.md    ← Este documento
    ├── analise_false_convergence.md  ← Documentação do script de análise
    └── guia_replicacao.md           ← Guia de replicação (este arquivo)
```

---

## 9. Variações Sugeridas para Estudos Futuros

Para pesquisadores interessados em estender o experimento:

| Variação | Como Implementar |
|---|---|
| Anti-cheat no prompt inicial | Alterar `_run_cegis_core` para passar `anti_cheat=True` em `build_initial_prompt` |
| Avaliar com conjunto `evaluation/` | Usar `--tasks ./data/evaluation` |
| Mais iterações CEGIS | Aumentar `MAX_CEGIS_ITERS` para 8 ou 10 |
| Diferentes modelos (Gemini / Gemma) | Alterar `MODEL_NAME` — ex: `gemini-3.1-pro`, `gemma-4-27b-it` |
| Análise de discordância 2×2 | Analisar a partir dos buckets `only_std` e `only_ac` — eles formam a tabela 2×2 |

### Matriz de Contingência 2×2 (para o artigo)

A tabela 2×2 dos casos discordantes é construída diretamente dos buckets do script:

```
                    Antitrapaça PASS   Antitrapaça FAIL
Padrão PASS         both_pass           only_std
Padrão FAIL         only_ac             both_fail
```
