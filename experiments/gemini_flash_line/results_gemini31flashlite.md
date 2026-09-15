# 📊 Relatório: CEGIS Padrão vs CEGIS Antitrapaça

- **Modelo:** `gemini-3.1-flash-lite`
- **Progresso:** **100/100** tarefas concluídas (**100.0%**)
- **Total de Requisições LLM:** 632

## 🔬 Hipótese

O prompt anti-cheat (que proíbe hardcoding e memorização de saídas) reduz a **falsa convergência**:
situações em que o modelo passa em todos os exemplos de treino (`converged_train=True`) mas falha
nos pares de teste ocultos (`success=False`). A métrica central é a taxa de falsa convergência.

## 📈 Resultados Comparativos

| Métrica | CEGIS Standard | CEGIS+Anti-Cheat | Δ Ganho |
| :--- | :---: | :---: | :---: |
| **Acurácia (sucesso no teste)** | 52.00% | 56.00% | **+4.00%** |
| **Tarefas Corretas** | 52/100 | 56/100 | +4 |
| **Falsas Convergências** | 2 | 2 | **+0** |

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
| 11 | `09629e4f` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 12 | `0962bcdd` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 13 | `0a938d79` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 14 | `0b148d64` | ✅ | ❌ | 2 | 4 | — | ⚠️ | ⚠️ Padrão ganhou |
| 15 | `0ca9ddb6` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 16 | `0d3d703e` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 17 | `0dfd9992` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 18 | `0e206a2e` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 19 | `10fcaaa3` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 20 | `11852cab` | ❌ | ❌ | 5 | 2 | ⚠️ | ⚠️ | ❌ Ambos falharam |
| 21 | `1190e5a7` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 22 | `137eaa0f` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 23 | `150deff5` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 24 | `178fcbfb` | ❌ | ✅ | 5 | 5 | — | — | 🚀 **Antitrapaça corrigiu** |
| 25 | `1a07d186` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 26 | `1b2d62fb` | ✅ | ❌ | 2 | 5 | — | — | ⚠️ Padrão ganhou |
| 27 | `1b60fb0c` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 28 | `1bfc4729` | ✅ | ❌ | 4 | 5 | — | — | ⚠️ Padrão ganhou |
| 29 | `1c786137` | ✅ | ✅ | 5 | 2 | — | — | 🎯 Ambos corretos |
| 30 | `1caeab9d` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 31 | `1cf80156` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 32 | `1e0a9b12` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 33 | `1e32b0e9` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 34 | `1f0c79e5` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 35 | `1f642eb9` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 36 | `1f85a75f` | ✅ | ✅ | 2 | 2 | — | — | 🎯 Ambos corretos |
| 37 | `1f876c06` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 38 | `1fad071e` | ❌ | ✅ | 5 | 2 | — | — | 🚀 **Antitrapaça corrigiu** |
| 39 | `2013d3e2` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 40 | `2204b7a8` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 41 | `22168020` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 42 | `22233c11` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 43 | `2281f1f4` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 44 | `228f6490` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 45 | `22eb0ac0` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 46 | `234bbc79` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 47 | `23581191` | ✅ | ✅ | 2 | 2 | — | — | 🎯 Ambos corretos |
| 48 | `239be575` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 49 | `23b5c85d` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 50 | `253bf280` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 51 | `25d487eb` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 52 | `25d8a9c8` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 53 | `25ff71a9` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 54 | `264363fd` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 55 | `272f95fa` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 56 | `27a28665` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 57 | `28bf18c6` | ✅ | ✅ | 3 | 2 | — | — | 🎯 Ambos corretos |
| 58 | `28e73c20` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 59 | `29623171` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 60 | `29c11459` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 61 | `29ec7d0e` | ✅ | ✅ | 2 | 2 | — | — | 🎯 Ambos corretos |
| 62 | `2bcee788` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 63 | `2bee17df` | ❌ | ✅ | 5 | 4 | — | — | 🚀 **Antitrapaça corrigiu** |
| 64 | `2c608aff` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 65 | `2dc579da` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 66 | `2dd70a9a` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 67 | `2dee498d` | ✅ | ✅ | 2 | 5 | — | — | 🎯 Ambos corretos |
| 68 | `31aa019c` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 69 | `321b1fc6` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 70 | `32597951` | ✅ | ✅ | 4 | 2 | — | — | 🎯 Ambos corretos |
| 71 | `3345333e` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 72 | `3428a4f5` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 73 | `3618c87e` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 74 | `3631a71a` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 75 | `363442ee` | ✅ | ❌ | 3 | 5 | — | — | ⚠️ Padrão ganhou |
| 76 | `36d67576` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 77 | `36fdfd69` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 78 | `3906de3d` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 79 | `39a8645d` | ❌ | ✅ | 4 | 2 | ⚠️ | — | 🚀 **Antitrapaça corrigiu** |
| 80 | `39e1d7f9` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 81 | `3aa6fb7a` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 82 | `3ac3eb23` | ✅ | ✅ | 5 | 2 | — | — | 🎯 Ambos corretos |
| 83 | `3af2c5a8` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 84 | `3bd67248` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 85 | `3bdb4ada` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 86 | `3befdf3e` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 87 | `3c9b0459` | ✅ | ✅ | 2 | 5 | — | — | 🎯 Ambos corretos |
| 88 | `3de23699` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 89 | `3e980e27` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 90 | `3eda0437` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 91 | `3f7978a0` | ❌ | ✅ | 5 | 5 | — | — | 🚀 **Antitrapaça corrigiu** |
| 92 | `40853293` | ✅ | ✅ | 2 | 2 | — | — | 🎯 Ambos corretos |
| 93 | `4093f84a` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 94 | `41e4d17e` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 95 | `4258a5f9` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 96 | `4290ef0e` | ❌ | ❌ | 5 | 5 | — | — | ❌ Ambos falharam |
| 97 | `42a50994` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 98 | `4347f46a` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
| 99 | `444801d8` | ❌ | ✅ | 5 | 5 | — | — | 🚀 **Antitrapaça corrigiu** |
| 100 | `445eab21` | ✅ | ✅ | 1 | 1 | — | — | 🎯 Ambos corretos |
