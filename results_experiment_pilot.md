# 📊 Relatório: CEGIS Padrão vs CEGIS Antitrapaça

- **Modelo:** `gemini-3.1-flash-lite`
- **Progresso:** **10/10** tarefas concluídas (**100.0%**)
- **Total de Requisições LLM:** 70

## 🔬 Hipótese

O prompt anti-cheat (que proíbe hardcoding e memorização de saídas) reduz a **falsa convergência**:
situações em que o modelo passa em todos os exemplos de treino (`converged_train=True`) mas falha
nos pares de teste ocultos (`success=False`). A métrica central é a taxa de falsa convergência.

## 📈 Resultados Comparativos

| Métrica | CEGIS Standard | CEGIS+Anti-Cheat | Δ Ganho |
| :--- | :---: | :---: | :---: |
| **Acurácia (sucesso no teste)** | 50.00% | 70.00% | **+20.00%** |
| **Tarefas Corretas** | 5/10 | 7/10 | +2 |
| **Falsas Convergências** | 0 | 0 | **+0** |

## 📝 Log por Tarefa

| # | Task ID | Padrão | Antitrapaça | Iter P | Iter AT | FC-P | FC-AT | Impacto |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | `007bbfb7` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 2 | `00d62c1b` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 3 | `017c7c7b` | ❌ | ✅ | 5 | 5 | — | — | 🚀 **Antitrapaça corrigiu** |
| 4 | `025d127b` | ❌ | ✅ | 5 | 5 | — | — | 🚀 **Antitrapaça corrigiu** |
| 5 | `045e512c` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 6 | `0520fde7` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 7 | `05269061` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 8 | `05f2a901` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 9 | `06df4c85` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 10 | `08ed6ac7` | ✅ | ✅ | 2 | 2 | — | — | 🎯 Ambos corretos |
