# Relatório do Piloto — CEGIS Padrão vs CEGIS Antitrapaça
**Data:** 2026-09-05 | **Modelo:** `gemini-3.1-flash-lite` | **Tasks:** 10 (training set)

---

## Sumário Executivo

| Métrica | Padrão | Antitrapaça | Δ |
|---|---|---|---|
| **Acurácia** | 50.0% (5/10) | **70.0% (7/10)** | **+20 pp** |
| **Falsas convergências** | 0 | 0 | 0 |
| **Iterações médias** | 3.10 | 3.10 | 0.00 |
| **API calls usadas** | — | — | 70/490 |
| **Tarefas com api_error** | — | — | 0 |

> ✅ Pipeline de rate limiting funcionando: 70 chamadas em ~6 min, zero erros 429. Alguns 503 resolvidos por retry automático.

---

## Resultado por Tarefa

| Task ID | Padrão | Iters P | Antitrapaça | Iters AT | Categoria |
|---|---|---|---|---|---|
| `007bbfb7` | ✅ (train✓) | 1 | ✅ (train✓) | 1 | 🎯 Ambos pass |
| `00d62c1b` | ✅ (train✓) | 1 | ✅ (train✓) | 1 | 🎯 Ambos pass |
| `017c7c7b` | ❌ (sem conv) | 5 | ✅ | 5 | 🚀 **Só Antitrapaça** |
| `025d127b` | ❌ (sem conv) | 5 | ✅ | 5 | 🚀 **Só Antitrapaça** |
| `045e512c` | ❌ | 5 | ❌ | 5 | ❌ Ambos fail |
| `0520fde7` | ✅ (train✓) | 1 | ✅ (train✓) | 1 | 🎯 Ambos pass |
| `05269061` | ❌ | 5 | ❌ | 5 | ❌ Ambos fail |
| `05f2a901` | ✅ (train✓) | 1 | ✅ (train✓) | 1 | 🎯 Ambos pass |
| `06df4c85` | ❌ | 5 | ❌ | 5 | ❌ Ambos fail |
| `08ed6ac7` | ✅ (train✓) | 2 | ✅ (train✓) | 2 | 🎯 Ambos pass |

### Distribuição dos desfechos

```
🎯 Ambos corretos    : 5 (50%)
❌ Ambos incorretos  : 3 (30%)
🚀 Só Antitrapaça   : 2 (20%)  ← ganho do anti-cheat
⚠️  Só Padrão        : 0  (0%)  ← sem regressões
```

---

## Análise de Falsa Convergência

**FC Padrão: 0 | FC Antitrapaça: 0**

Nenhuma falsa convergência detectada neste piloto de 10 tasks. Isso é esperado para amostras pequenas: as tasks onde ambos falharam nunca convergiram no treino (esgotaram as 5 iterações sem satisfazer os exemplos de treino), portanto o critério `converged_train=True AND success=False` não foi atingido.

> **Implicação**: para detectar FCs em quantidade suficiente, o experimento completo com 100+ tasks será necessário. Em benchmarks maiores, espera-se que tarefas mais complexas provoquem convergência superficial no treino.

---

## Teste de McNemar

```
Tabela 2×2:
                    Antitrapaça ✅   Antitrapaça ❌
Padrão ✅           5 (both_pass)    0 (only_std, b=0)
Padrão ❌           2 (only_ac, c=2) 3 (both_fail)

χ² = (|0 - 2| - 1)² / (0 + 2) = 0.50
```

⚠️ **Amostra insuficiente** para significância estatística: b + c = 2 ≤ 25.
O resultado **não pode ser interpretado como evidência estatística** — é apenas uma tendência exploratória. O experimento completo (100 tasks) é necessário.

---

## Auditoria LLM-as-a-Judge

Não houve casos de `fc_fixed` ou `fc_introduced` neste piloto (zero FCs detectadas), portanto o pipeline do juiz não teve tarefas para auditar. O pipeline está funcional e será ativado automaticamente quando houver FCs no experimento completo.

---

## Validação do Pipeline

| Componente | Status | Observação |
|---|---|---|
| `.venv` criado | ✅ | Python 3.14, todas as dependências instaladas |
| Rate limiting | ✅ | 4.2s delay, 14.3 RPM efetivos, zero 429s |
| Multi-key pool | ✅ | 6 chaves configuradas, 70/490 RPD usados |
| Retry em 503 | ✅ | Recuperação automática, sem perda de tasks |
| Checkpoint | ✅ | `results_experiment_pilot_10_10.json` salvo |
| Filtro api_error | ✅ | 0 tarefas removidas |
| McNemar | ✅ | Calculado (amostra insuficiente, esperado) |
| LLM-as-a-Judge | ✅ | Pipeline funcional (sem FCs para auditar neste piloto) |

---

## Próximos Passos

1. **Escalar para 100 tasks** — necessário para detectar FCs em quantidade e ter poder estatístico no McNemar:
   ```bash
   DOTENV=.env .venv/bin/python main.py \
     --tasks ./data/training \
     --max-tasks 100 \
     --output results_experiment.json \
     --markdown results_experiment.md
   ```

2. **Análise completa com juiz** (após experimento de 100 tasks):
   ```bash
   DOTENV=.env .venv/bin/python analysis/analyze_false_convergence.py \
     results_experiment.json --verbose --judge --judge-max-per-bucket 10
   ```

3. **Resultado esperado em 100 tasks** (estimativa):
   - Tempo: ~3–4h com 6 chaves em pool
   - API calls: ~700–1400 (dentro dos 2940 RPD disponíveis)
   - FCs esperadas: 5–20 (base para análise qualitativa do juiz)
