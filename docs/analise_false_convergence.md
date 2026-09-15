# Script de Análise: `analyze_false_convergence.py`

## Visão Geral

O script `analysis/analyze_false_convergence.py` é a ferramenta de análise pós-experimento responsável por computar e apresentar todas as métricas comparativas entre as variantes **CEGIS Padrão** e **CEGIS Antitrapaça** a partir do arquivo JSON de resultados gerado pelo `main.py`.

**Arquivo**: [`analysis/analyze_false_convergence.py`](../analysis/analyze_false_convergence.py)

---

## 1. Entrada: Formato do Arquivo JSON de Resultados

O script consome o arquivo `results_experiment.json` (ou qualquer caminho especificado) com a estrutura:

```json
{
  "config": {
    "model": "gemma-4-31b-it",
    "max_cegis_iters": 5,
    "provider": "gemini",
    "timestamp": "2026-09-04T..."
  },
  "summary": { ... },
  "results": [
    {
      "task_id": "007bbfb7",
      "cegis_padrao": {
        "strategy": "cegis_padrao",
        "success": false,
        "api_error": false,
        "converged_train": true,
        "false_convergence": true,
        "iterations_used": 3,
        "latency": 12.4,
        "generated_code": "def transform(grid): ...",
        "iteration_history": [...],
        "test_results": [...]
      },
      "cegis_antitrapaca": {
        "strategy": "cegis_antitrapaca",
        "success": true,
        "converged_train": true,
        "false_convergence": false,
        "iterations_used": 3,
        ...
      }
    }
    ...
  ]
}
```

O script lê **apenas** os campos `results`, `config` e `summary`. Campos ausentes são tratados com valores padrão para robustez.

---

## 2. Uso

```bash
# Análise padrão — tabela de métricas
python analysis/analyze_false_convergence.py results_experiment.json

# Com listagem de task IDs por categoria
python analysis/analyze_false_convergence.py results_experiment.json --verbose
```

---

## 3. Métricas Computadas

### 3.1. Contadores por Variante

Para cada tarefa no array `results`, o script acumula:

| Contador | Campo Lido | Descrição |
|---|---|---|
| `std_correct` / `ac_correct` | `success` | Tarefas com código correto no teste oculto |
| `std_converged` / `ac_converged` | `converged_train` | Tarefas onde o código passou em todos os exemplos de treino |
| `std_false_conv` / `ac_false_conv` | `false_convergence` | Tarefas com falsa convergência (converged_train=True e success=False) |
| `std_iters_total` / `ac_iters_total` | `iterations_used` | Soma de iterações usadas |

### 3.2. Métricas Derivadas

```python
# Acurácia
std_acc  = std_correct  / n * 100  # %
ac_acc   = ac_correct   / n * 100  # %
acc_gain = ac_acc - std_acc         # Δ absoluto (pp)

# Taxa de Falsa Convergência (FC)
std_fc_rate       = std_false_conv / n * 100  # %
ac_fc_rate        = ac_false_conv  / n * 100  # %
fc_rate_reduction = std_fc_rate - ac_fc_rate  # Δ (pp), positivo = redução

# Iterações médias
std_avg_iters = std_iters_total / n
ac_avg_iters  = ac_iters_total  / n
```

### 3.3. Buckets de Desfecho por Tarefa

Cada tarefa é classificada em **exatamente um** dos quatro buckets de acurácia:

| Bucket | Condição | Interpretação |
|---|---|---|
| `both_pass` | Padrão=✅, Antitrapaça=✅ | Ambas corretas — tarefa acessível a ambas |
| `both_fail` | Padrão=❌, Antitrapaça=❌ | Ambas falham — tarefa além da capacidade do modelo |
| `only_std` | Padrão=✅, Antitrapaça=❌ | Antitrapaça **regrediu** nesta tarefa |
| `only_ac` | Padrão=❌, Antitrapaça=✅ | Antitrapaça **corrigiu** uma falha do Padrão |

E dois buckets de falsa convergência (**não mutuamente exclusivos** com os anteriores):

| Bucket | Condição | Interpretação |
|---|---|---|
| `fc_fixed` | Padrão=FC, Antitrapaça=!FC | Anti-cheat **eliminou** uma falsa convergência |
| `fc_introduced` | Padrão=!FC, Antitrapaça=FC | Anti-cheat **introduziu** uma nova FC (inesperado) |

---

## 4. Saída: Estrutura do Relatório

### Seção 1: Tabela Comparativa de Métricas

```
=================================================================
  ANÁLISE: CEGIS Padrão vs CEGIS Antitrapaça
=================================================================
  Modelo : gemma-4-31b-it
  Max Iter: 5
  Tarefas: 100 avaliadas
=================================================================
  Métrica                                   Padrão  Antitrapaça       Δ
  ---------------------------------------- ---------- ------------ --------
  Acurácia (success no teste)                25.00%       30.00%   +5.00%
  Corretas                                       25           30       +5
  Convergência no treino (converged_train)       60           58       -2
  Falsas convergências (FC)                      35           28       -7
  Taxa de FC                                 35.00%       28.00%   +7.00%
  Iterações médias                            3.12         3.45    +0.33
```

> **Nota sobre a coluna Δ na Taxa de FC**: o sinal exibido na tabela indica **mudança** (não redução), portanto um `+7.00%` na coluna Δ de Taxa de FC significa que a taxa *diminuiu* em 7 pontos percentuais — o sinal é coerente com `ac_fc_rate - std_fc_rate`, que é negativo quando há redução.

### Seção 2: Distribuição de Desfechos

```
=================================================================
  DISTRIBUIÇÃO DE DESFECHOS
=================================================================
  🎯 Ambos corretos          :   20 (20.0%)
  ❌ Ambos incorretos        :   45 (45.0%)
  🚀 Só Anti-Cheat acertou   :   10 (10.0%)
  ⚠️  Só Standard acertou    :    5  (5.0%)
```

### Seção 3: Análise de Falsa Convergência

```
=================================================================
  ANÁLISE DE FALSA CONVERGÊNCIA
=================================================================
  FC eliminadas pelo Anti-Cheat  :   12  (Standard tinha FC, Anti-Cheat não)
  FC introduzidas pelo Anti-Cheat:    5  (Standard não tinha FC, Anti-Cheat teve)
  Redução líquida de FCs         :   +7
```

### Seção 4: Veredicto Final

```
=================================================================
  Acurácia     : ✅ Anti-Cheat MELHOROU (+5.00%)
  Falsa Conv.  : ✅ FC REDUZIDA (-7.00% na taxa)
=================================================================
```

### Seção 5: Task IDs por Categoria (--verbose)

Com a flag `--verbose`, o script exibe as listas de `task_id` para cada bucket:
- `only_ac`: tarefas corrigidas pelo Antitrapaça
- `only_std`: tarefas perdidas com o Antitrapaça
- `fc_fixed`: tasks onde FC foi eliminada
- `fc_introduced`: tasks onde FC foi introduzida (casos anômalos para análise manual)

---

## 5. Interpretação dos Resultados para o Artigo

### 5.1. Hipótese Confirmada

A hipótese se confirma quando, simultaneamente:
- `fc_rate_reduction > 0` (redução na taxa de falsa convergência)
- `acc_gain >= 0` (sem perda de acurácia geral)

O resultado ideal é `acc_gain > 0` com `fc_rate_reduction > 0`, demonstrando que a Antitrapaça tanto reduz FCs quanto melhora a acurácia real.

### 5.2. Hipótese Parcialmente Confirmada

- `fc_rate_reduction > 0` com `acc_gain = 0`: o Antitrapaça não melhora a acurácia mas reduz o número de casos de hardcoding detectados. Pode indicar que o modelo generaliza mais mas ainda não resolve as tasks corretamente.
- `fc_rate_reduction > 0` com `acc_gain < 0`: o Antitrapaça elimina falsas convergências mas também elimina algumas soluções que, por acaso, eram corretas mesmo sendo parcialmente hardcoded.

### 5.3. Hipótese Refutada

- `fc_rate_reduction <= 0` com `acc_gain <= 0`: o prompt anti-cheat não tem efeito positivo ou prejudica o desempenho.

### 5.4. Métricas Secundárias para Discussão

- **`fc_introduced > 0`**: indica casos onde o prompt anti-cheat induziu o modelo a produzir código que não passa nem no treino mas ficou travado sem convergir (`converged_train=False, success=False`). Investigar com `--verbose`.
- **Iterações médias**: se `ac_avg_iters > std_avg_iters`, o Antitrapaça requer mais refinamentos, indicando que a restrição anti-cheat força mais iterações antes da convergência — o que é esperado e aceitável se a acurácia final for maior.
- **`std_converged >> ac_converged`**: se a Antitrapaça converge em treino muito menos que o Padrão, pode indicar que o prompt anti-cheat está impedindo convergência genuína além do hardcoding.

---

## 6. Limitações do Script

1. **Sem teste de significância estatística**: o script reporta diferenças absolutas e percentuais, mas não calcula *p-values* nem intervalos de confiança. Para o artigo, recomenda-se adicionar testes de significância adequados ou testes binomiais.
2. **Sem análise do código gerado**: o script não inspeciona o `generated_code` — a classificação de "falsa convergência" é puramente baseada nos sinais booleanos, não na análise do código.
3. **Sem separação por tipo de tarefa**: o ARC-AGI-1 tem tarefas de diferentes complexidades e categorias (geométricas, cromáticas, etc.). O script agrega tudo em uma única análise.
4. **Sem distinção de API errors**: tarefas com `api_error=True` são incluídas na análise com `success=False`, o que pode subestimar a acurácia real.
