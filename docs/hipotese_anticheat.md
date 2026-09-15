# Hipótese: Prompt Anti-Cheat para Redução de Falsa Convergência no CEGIS

## Contexto

O CEGIS (Counterexample-Guided Inductive Synthesis) aplicado a puzzles ARC-AGI utiliza um laço de feedback onde:
1. O modelo gera uma função `transform(grid)` candidata.
2. A função é testada contra todos os exemplos de treino.
3. Se falhar em algum, o exemplo falho é enviado como **contraexemplo** no prompt seguinte.
4. O processo se repete até o modelo convergir (passar em todos os exemplos de treino) ou esgotar as iterações.

## O Problema: Falsa Convergência

**Falsa convergência** ocorre quando:
- `converged_train = True` (o código passa em TODOS os exemplos de treino), MAS
- `success = False` (o código FALHA nos pares de teste ocultos).

Isso indica que o modelo "resolveu" o treino de forma superficial — possivelmente por **hardcoding**:
- Memorizando coordenadas específicas dos exemplos de treino
- Ramificando com `if example_index == 0: ...`
- Replicando os outputs de treino diretamente no código
- Usando heurísticas específicas ao conjunto de treino que não generalizam

Esta é a forma mais enganosa de falha: o CEGIS encerra o loop crendo ter encontrado uma solução correta, mas a função não captura a transformação subjacente real.

## A Intervenção: Prompt Anti-Cheat

O **CEGIS+Anti-Cheat** adiciona regras explícitas de proibição em dois pontos do fluxo:

### 1. Prompt Inicial (`build_initial_prompt` com `anti_cheat=True`)
```
RULES:
- Do NOT use `import` statements; use only pure native Python.
- Do NOT hardcode coordinates or branch on specific example indices; 
  provide a single uniform geometric/mathematical transformation.
- Do NOT memorize or replicate specific output grids from the examples; 
  the function must generalize.
```

### 2. Mensagens de Feedback (`build_counterexample_feedback` com `anti_cheat=True`)
As mesmas regras são repetidas em cada mensagem de contraexemplo, reforçando a restrição durante o processo de refinamento.

## Hipótese Principal

> **O CEGIS+Anti-Cheat terá uma taxa de falsa convergência significativamente menor que o CEGIS Standard, sem perda proporcional de acurácia geral.**

### Sub-hipóteses

1. **Redução de FC**: O prompt anti-cheat desestimula estratégias de hardcoding, forçando o modelo a buscar padrões mais geralizáveis.
2. **Custo em acurácia**: Algumas tarefas que o Standard "resolvia" via hardcoding podem passar a falhar com o Anti-Cheat (perdas legítimas).
3. **Ganho líquido**: O número de tarefas corretamente resolvidas (treinadas E testadas) deve aumentar ou se manter.

## Definição das Variantes

| Variante | Prompt Inicial | Feedback de Counterexample |
|---|---|---|
| **CEGIS Padrão** | Sem anti-cheat | **Sem** anti-cheat |
| **CEGIS Antitrapaça** | Sem anti-cheat | **Com** anti-cheat |

> **Nota de design**: o prompt inicial é idêntico em ambas as variantes. As regras anti-cheat são injetadas **apenas no feedback** de counterexemplo porque, na primeira iteração, o modelo ainda não viu os outputs esperados — portanto hardcoding é impossível. A restrição só se torna relevante após o primeiro counterexemplo revelar um output concreto.

O CEGIS Padrão é o **grupo controle** — sem qualquer restrição além de proibir `import`.

## Métricas Primárias

| Métrica | Definição |
|---|---|
| **Acurácia** | `success=True` no par de teste oculto |
| **Taxa de Falsa Convergência** | `converged_train=True AND success=False` / n_tasks |
| **Redução de FC** | `FC_padrao - FC_antitrapaca` |
| **Ganho de Acurácia** | `acc_antitrapaca - acc_padrao` |

## Análise dos Resultados

Use o script de análise para quantificar todos os indicadores:

```bash
python3 analysis/analyze_false_convergence.py results_experiment.json
python3 analysis/analyze_false_convergence.py results_experiment.json --verbose
```

---

## Documentos Relacionados

- [Metodologia Detalhada do Experimento](metodologia_experimento.md) — descrição científica completa
- [Documentação do Script de Análise](analise_false_convergence.md) — todas as métricas e interpretação
- [Guia de Replicação](guia_replicacao.md) — passo a passo para reproduzir o experimento
