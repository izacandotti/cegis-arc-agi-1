"""
ARC-AGI CEGIS Comparison Experiment Package.

Primary comparison: CEGIS Padrão vs CEGIS Antitrapaça.
Research goal: quantify false convergence reduction from anti-cheat feedback prompting.
"""

from .config import (
    API_BASE_URL,
    API_BASE_URLS,
    API_KEYS,
    LLM_PROVIDER,
    MODEL_NAME,
    MAX_CEGIS_ITERS,
    TIMEOUT_SECONDS,
    REQUEST_DELAY,
    MAX_DAILY_REQUESTS,
    MAX_CONCURRENT_TASKS,
    ANTI_CHEAT,
    INCLUDE_BASELINE,
    LLMConfig,
    LLM_POOL,
    get_next_llm,
    get_api_key,
    get_api_base_url,
)
from .data_loader import load_tasks
from .experiment import (
    evaluate_on_test,
    run_baseline,
    run_cegis,               # backward-compat alias → run_cegis_padrao
    run_cegis_standard,      # backward-compat alias → run_cegis_padrao
    run_cegis_padrao,
    run_cegis_antitrapaca,
)
from .llm import (
    AuthError,
    QuotaExceededError,
    call_llm,
    get_request_count,
    reset_request_count,
)
from .prompts import build_counterexample_feedback, build_initial_prompt
from .sandbox import extract_python_code, run_transform

__all__ = [
    "API_BASE_URL",
    "API_BASE_URLS",
    "API_KEYS",
    "LLM_PROVIDER",
    "MODEL_NAME",
    "MAX_CEGIS_ITERS",
    "TIMEOUT_SECONDS",
    "REQUEST_DELAY",
    "MAX_DAILY_REQUESTS",
    "MAX_CONCURRENT_TASKS",
    "ANTI_CHEAT",
    "INCLUDE_BASELINE",
    "LLMConfig",
    "LLM_POOL",
    "get_next_llm",
    "get_api_key",
    "get_api_base_url",
    "load_tasks",
    "evaluate_on_test",
    "run_baseline",
    "run_cegis",
    "run_cegis_standard",
    "run_cegis_padrao",
    "run_cegis_antitrapaca",
    "call_llm",
    "AuthError",
    "QuotaExceededError",
    "get_request_count",
    "reset_request_count",
    "build_counterexample_feedback",
    "build_initial_prompt",
    "extract_python_code",
    "run_transform",
]
