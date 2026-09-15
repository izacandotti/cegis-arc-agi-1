## 📊 Experimental Results

A comparative evaluation was performed across `100 tasks` from the ARC-AGI-1 training benchmark to measure the impact of **Semantic Counterexample-Guided Inductive Synthesis (CEGIS)** against a **1-Shot Baseline** using `gemini-3.1-flash-lite`.

### Summary Statistics

| Approach | Exact Accuracy | Solved Tasks | Total API Requests | Avg. Requests/Task |
| :--- | :---: | :---: | :---: | :---: |
| **Baseline (1-Shot)** | **39.0%** | 39 / 100 | 100 | 1.00 |
| **CEGIS (Semantic Feedback)** | **47.0%** | 47 / 100 | 341 | 3.41 |
| **Delta / Impact** | **+8.0%** *(+20.5% rel.)* | **+8 tasks** | +241 requests | +2.41x cost |

---

