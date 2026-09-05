# ARC-AGI-1: CEGIS Standard vs CEGIS+Anti-Cheat

Experimento comparativo de síntese de programas no benchmark **ARC-AGI-1**.

**Foco da pesquisa**: quantificar o impacto do **prompt anti-cheat** na redução de **falsa convergência** dentro do laço CEGIS.

## Hipótese Central

O CEGIS pode sofrer de **falsa convergência**: o modelo gera código que passa em todos os exemplos de treino (`converged_train=True`) via hardcoding ou memorização, mas falha nos pares de teste ocultos (`success=False`). Ao injetar regras explícitas que proíbem hardcoding tanto no prompt inicial quanto nos feedbacks de contraexemplo, espera-se reduzir essa falha sem perda de acurácia geral.

→ Veja [docs/hipotese_anticheat.md](docs/hipotese_anticheat.md) para a formulação completa.

## Métricas Principais

- **Acurácia**: % de tarefas com `success=True` no par de teste oculto
- **Taxa de Falsa Convergência (FC)**: `converged_train=True AND success=False` / n_tasks
- **Redução de FC**: `FC_standard - FC_anticheat`
- **Ganho absoluto de acurácia**: `acc_anticheat - acc_standard`


## Proteções Free Tier

- **Context Pruning no CEGIS**: prompt = especificação inicial + código atual + contraexemplo ativo. Tamanho constante, sem acumulação exponencial.
- **Multi-Key Pool**: rotação entre chaves API.
- **Rate Limiter (RPM)**: delay configurável entre requests.
- **Daily Quota Guard (RPD)**: teto de requisições diárias com pausa segura.
- **Checkpoint/Resume**: salva após cada tarefa; retoma de onde parou.

## Setup & Execução

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente (`.env`)
```env
GEMINI_API_KEY="sua_chave"

MAX_CEGIS_ITERS=5
REQUEST_DELAY=2.0
MAX_DAILY_REQUESTS=14400
```

Variáveis opcionais:
| Variável | Padrão | Descrição |
|---|---|---|
| `MODEL_NAME` | `gemini-3.1-flash-lite` | Modelo alvo |
| `MAX_CEGIS_ITERS` | `5` | Máximo de iterações de refinamento |
| `TIMEOUT_SECONDS` | `2.0` | Timeout de execução Python por teste |
| `REQUEST_DELAY` | `2.0` | Delay entre requests (segundos) |
| `MAX_DAILY_REQUESTS` | `14400` | Teto de requisições diárias |
| `INCLUDE_BASELINE` | `false` | Incluir baseline (1-shot) automaticamente |

### 3. Executar o experimento

```bash
# Comparação principal: CEGIS Standard vs CEGIS+Anti-Cheat (100 tasks)
python3 main.py --tasks ./data --max-tasks 100 --output results_experiment.json

# Com baseline 1-shot como referência adicional
python3 main.py --tasks ./data --max-tasks 100 --include-baseline --output results_experiment.json

# Reiniciar do zero (ignorar checkpoint existente)
python3 main.py --tasks ./data --max-tasks 100 --no-resume --output results_experiment.json

# Teste rápido com 5 tasks
python3 main.py --tasks ./data --max-tasks 5 --no-resume --output test_results.json
```

### 4. Analisar resultados

```bash
# Tabela comparativa completa com métricas de falsa convergência
python analysis/analyze_false_convergence.py results_experiment.json

# Com lista de tasks por categoria
python analysis/analyze_false_convergence.py results_experiment.json --verbose
```

## Resultados Anteriores

O experimento original (Baseline 1-shot vs CEGIS) com `gemma-4-31b-it` em 100 tasks está preservado em:
- `experiments/raw_results/baseline_vs_cegis/`
- `experiments/baseline_vs_cegis_report.md`
