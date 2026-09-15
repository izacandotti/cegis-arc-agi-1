"""
Pacote de análise e auditoria de convergência para o benchmark ARC-AGI CEGIS.
Inclui cálculo de métricas estatísticas e pipeline LLM-as-a-Judge.
"""

from .analyze_false_convergence import (
    OutcomeBuckets,
    VariantStats,
    compute_stats,
    filter_valid_tasks,
    main as run_analysis,
)

__all__ = [
    "OutcomeBuckets",
    "VariantStats",
    "compute_stats",
    "filter_valid_tasks",
    "run_analysis",
]
