# Metodologia do Experimento: CEGIS Padrão vs CEGIS Antitrapaça

## 1. Introdução e Motivação

Este documento descreve a metodologia científica utilizada no experimento comparativo entre duas variantes do algoritmo CEGIS (*Counterexample-Guided Inductive Synthesis*) aplicado ao benchmark **ARC-AGI-1** (*Abstraction and Reasoning Corpus*). O objetivo central é investigar se a inclusão de restrições explícitas anti-hardcoding no prompt de *feedback* do ciclo CEGIS reduz a ocorrência de **falsa convergência** — o principal modo de falha identificado no método.

---

## 2. Benchmark: ARC-AGI-1

O ARC-AGI-1 é um benchmark de raciocínio abstrato composto por tarefas de transformação de grids 2D de inteiros. Cada tarefa contém:

- **Exemplos de treino**: pares `(grid_entrada, grid_saída)` que demonstram a transformação.
- **Pares de teste**: um ou mais pares `(grid_entrada, grid_saída)` ocultos, usados exclusivamente para avaliação final.

As transformações envolvem operações geométricas e lógicas (rotações, reflexões, preenchimentos, padrões cromáticos, etc.) que requerem generalização a partir de poucos exemplos. O benchmark foi projetado para resistir à memorização, pois os pares de teste não são vistos durante a síntese.

---

## 3. Abordagem: Program Synthesis via LLM

Em vez de buscar a saída diretamente, o experimento utiliza **síntese de programas**: o modelo de linguagem (LLM) deve produzir uma função Python `transform(grid: list[list[int]]) -> list[list[int]]` que implemente a transformação descoberta. A avaliação da função é feita por execução, não por comparação textual.

Vantagens desta abordagem:
- A função é **determinística e verificável**: podemos checar exatamente se ela está correta em cada par.
- Permite detectar **falsa convergência** com precisão: o código pode passar no treino por memorização, mas falhar no teste por não generalizar.
- Desacopla a capacidade de raciocínio do LLM da capacidade de geração de respostas diretas.

---

## 4. Algoritmo CEGIS Aplicado a ARC

O CEGIS (*Counterexample-Guided Inductive Synthesis*) é um paradigma clássico de síntese de programas que opera em um ciclo síntese–verificação–refinamento:

```
┌─────────────────────────────────────────────────────────┐
│  LOOP CEGIS (máx. MAX_CEGIS_ITERS iterações)            │
│                                                         │
│  1. LLM gera candidato: transform(grid)                 │
│  2. Verificador executa o candidato em todos os         │
│     exemplos de treino                                  │
│  3a. Se passar em TODOS → converged_train = True        │
│      → Avalia nos pares de teste ocultos → FIM          │
│  3b. Se falhar em algum → extrai counterexemplo         │
│      → Constrói feedback semântico                      │
│      → Adiciona ao prompt → volta ao passo 1            │
│                                                         │
│  Se esgotar iterações → avalia código atual no teste    │
└─────────────────────────────────────────────────────────┘
```

### 4.1. Prompt Inicial (Ambas as Variantes)

O prompt inicial é **idêntico** em ambas as variantes:

```
You are an expert Python programmer solving an ARC puzzle.
Analyze the input-output grid demonstration pairs to discover the
underlying transformation rule.

--- Example 0 ---
Input: [[...]]
Output: [[...]]
...

Write a Python function transform(grid) -> list[list[int]].

RULES:
- Do NOT use `import` statements; use only pure native Python.

Requirements:
- Input: 2D list of integers. Return: 2D list of integers.
- Briefly state the transformation rule and return valid Python code
  in a ```python ... ``` block.
```

### 4.2. Context Pruning (Poda de Contexto)

Para cada iteração de refinamento, o contexto enviado ao LLM é **podado** para conter apenas:

1. O prompt inicial com os exemplos de treino
2. O último código candidato gerado (como turno do assistente)
3. O feedback do counterexemplo atual (como turno do usuário)

Isto mantém o tamanho do prompt **constantemente limitado** ao longo de todas as iterações, prevenindo acumulação exponencial de tokens e violações do limite de TPM (*Tokens per Minute*) da API.

---

## 5. As Duas Variantes Experimentais

### 5.1. CEGIS Padrão (Grupo Controle)

O CEGIS Padrão executa o algoritmo sem qualquer restrição sobre a estratégia de síntese além da proibição de `import`. O feedback de counterexemplo segue o formato:

```
Your code failed on Training Example {idx}.
- Input: [[...]]
- Expected Output: [[...]]
- Produced Output: [[...]] ou Execution Error: ...

RULES:
- Do NOT use `import` statements; use only pure native Python.

Fix the logic and provide the updated transform(grid) function.
```

O modelo é livre para aprender qualquer padrão, **incluindo** memorização ou hardcoding dos valores de treino.

### 5.2. CEGIS Antitrapaça (Grupo Experimental)

O CEGIS Antitrapaça é **idêntico** ao Padrão no prompt inicial, mas adiciona **ANTI_CHEAT_RULES** em cada mensagem de feedback:

```
Your code failed on Training Example {idx}.
- Input: [[...]]
- Expected Output: [[...]]
- Produced Output: [[...]]

RULES:
- Do NOT use `import` statements; use only pure native Python.
- Do NOT hardcode coordinates or branch on specific example indices;
  provide a single uniform geometric/mathematical transformation.
- Do NOT memorize or replicate specific output grids from the examples;
  the function must generalize.

Fix the logic and provide the updated transform(grid) function.
```

#### Justificativa para Feedback-Only

A restrição é inserida **apenas no feedback** (e não no prompt inicial) por dois motivos:

1. **Pertinência temporal**: Na primeira iteração, o modelo ainda não viu os outputs esperados, portanto não há oportunidade de hardcoding. A restrição só se torna relevante após o modelo receber pelo menos um counterexemplo revelando um output concreto.
2. **Reaproveitamento de dados**: O experimento anterior (CEGIS original, que já tinha anti-cheat no feedback) é diretamente comparável ao CEGIS Antitrapaça, permitindo reutilizar dados históricos.

---

## 6. Verificador: Sandbox de Execução Segura

Cada código candidato é executado em um **subprocesso isolado** (`multiprocessing.Process`) com:

- **Namespace restrito**: apenas builtins seguros são disponibilizados (`range`, `len`, `min`, `max`, `sum`, `abs`, `enumerate`, `zip`, `list`, `dict`, `set`, etc.). Qualquer instrução `import` resulta em `NameError`.
- **Timeout**: execução encerrada após `TIMEOUT_SECONDS` (padrão: 2.0s). O processo é terminado com `SIGTERM`, depois `SIGKILL` se necessário.
- **Isolamento de memória**: a entrada é copiada antes da execução para prevenir mutação in-place do grid.
- **Verificação de tipo de retorno**: o resultado deve ser `list`. Qualquer outro tipo resulta em falha.

O resultado da verificação é um triplo `(success: bool, output_grid, error_msg)`.

---

## 7. Fluxo de Dados Completo por Tarefa

```
Tarefa ARC
    │
    ├─ train_pairs → Prompt Inicial (idêntico em ambas variantes)
    │
    │   ┌── CEGIS Padrão ─────────────────────────────────────┐
    │   │  iter 1: LLM → código → sandbox → falhou?           │
    │   │  iter 2: feedback (sem anti-cheat) → LLM → código → │
    │   │  ...                                                 │
    │   │  iter N: converged_train=True ou max_iters           │
    │   │  → evaluate_on_test(test_pairs) → success, FC?      │
    │   └──────────────────────────────────────────────────────┘
    │
    ├─ train_pairs → Prompt Inicial (idêntico em ambas variantes)
    │
    │   ┌── CEGIS Antitrapaça ────────────────────────────────┐
    │   │  iter 1: LLM → código → sandbox → falhou?           │
    │   │  iter 2: feedback (+ anti-cheat) → LLM → código →  │
    │   │  ...                                                 │
    │   │  iter N: converged_train=True ou max_iters           │
    │   │  → evaluate_on_test(test_pairs) → success, FC?      │
    │   └──────────────────────────────────────────────────────┘
    │
    └─ Resultado: { cegis_padrao: {...}, cegis_antitrapaca: {...} }
```

---

## 8. Definição Formal da Falsa Convergência

Seja *T* uma tarefa com exemplos de treino *E_train* e pares de teste *E_test*.  
Seja *f* a função gerada pelo CEGIS ao final do ciclo.

**Convergência no treino** (converged_train):
> ∀ (x, y) ∈ E_train : f(x) = y

**Sucesso no teste** (success):
> ∀ (x, y) ∈ E_test : f(x) = y

**Falsa Convergência** (false_convergence):
> converged_train = True **AND** success = False

Ou seja: *f* satisfaz todos os exemplos conhecidos mas falha nos ocultos — evidência de que *f* aprendeu uma solução específica ao treino (hardcoding, memorização) em vez da transformação subjacente geral.

---

## 9. Variáveis do Experimento

| Variável | Tipo | Descrição |
|---|---|---|
| **Variante CEGIS** | independente | Padrão vs Antitrapaça |
| **Tarefa ARC** | bloco | Par de tarefa avaliada simultaneamente |
| **Modelo LLM** | controlada | Fixo para todo o experimento |
| **MAX_CEGIS_ITERS** | controlada | Número máximo de iterações |
| **Temperatura** | controlada | 0.0 (determinístico) |
| **success** | dependente primária | Acurácia no conjunto de teste |
| **false_convergence** | dependente primária | Ocorrência de falsa convergência |
| **iterations_used** | dependente secundária | Eficiência do processo de refinamento |
| **converged_train** | dependente secundária | Taxa de convergência no treino |

### Controles Experimentais Importantes

- **Mesmo prompt inicial**: garante que a única diferença entre variantes seja o conteúdo do feedback.
- **Mesmo modelo e temperatura**: garante comparabilidade das respostas.
- **Execução paralela por tarefa**: ambas as variantes são executadas na mesma tarefa no mesmo run, eliminando variabilidade temporal do dataset.
- **Temperatura 0.0**: respostas determinísticas, eliminando variância estocástica.
- **Checkpoint/Resume**: permite pausas sem perda de dados, mantendo integridade experimental.

---

## 10. Coleta de Dados e Armazenamento

Cada tarefa produz um registro JSON com a estrutura:

```json
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
    "api_error": false,
    "converged_train": true,
    "false_convergence": false,
    "iterations_used": 3,
    "latency": 14.1,
    "generated_code": "def transform(grid): ...",
    "iteration_history": [...],
    "test_results": [...]
  }
}
```

O arquivo de checkpoint principal (`results_experiment.json`) é atualizado atomicamente (write → rename) após cada tarefa concluída.

---

## 11. Limitações e Ameaças à Validade

### 11.1 Contaminação do Dataset
O ARC-AGI-1 é um benchmark público, e é possível que os dados de treino dos LLMs modernos incluam soluções das tarefas. Isso pode inflar artificialmente a acurácia e tornar a falsa convergência menos distinguível. O experimento não controla esta variável.

### 11.2 Determinismo vs Pseudo-determinismo
Temperatura 0.0 garante que a mesma entrada produza a mesma saída para um dado modelo. Porém, diferentes versões do modelo ou diferentes backends de inferência podem produzir saídas distintas para a mesma entrada, mesmo com temperatura 0.

### 11.3 Tamanho do Conjunto de Avaliação
O experimento avalia um subconjunto das tarefas ARC-AGI-1. Resultados em subsets menores podem não ser estatisticamente representativos.

### 11.4 Confundimento da Variante
É possível que o prompt anti-cheat altere o estilo de raciocínio do modelo de formas além da simples proibição de hardcoding — por exemplo, induzindo maior cautela geral, que pode afetar a acurácia independentemente da redução de falsa convergência.

### 11.5 Definição Operacional de Falsa Convergência
A definição usada é conservadora: qualquer código que passe no treino e falhe no teste é classificado como falsa convergência, sem distinguir se a falha é por hardcoding ou por generalização incompleta de uma solução genuinamente tentada. Uma análise qualitativa do código gerado seria necessária para distinguir esses casos.
