"""
Global configuration settings for the ARC-CEGIS experiment.

Experiment focus: CEGIS Standard vs CEGIS+Anti-Cheat.
The anti-cheat variant injects rules forbidding hardcoding into both the initial
prompt and counterexample feedback, aiming to reduce false convergence.
"""

import os
import threading
from dataclasses import dataclass

from dotenv import dotenv_values, find_dotenv


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    request_delay: float
    max_daily_requests: int
    max_concurrent_tasks: int
    api_key: str | None = None
    pool_index: int | None = None


def _dotenv_paths_from_env() -> list[str]:
    raw = os.getenv("DOTENV", "").strip()
    if not raw:
        return [find_dotenv()]

    return [path.strip() for path in raw.split(os.pathsep) if path.strip()]


def _load_dotenv_values() -> None:
    merged: dict[str, str | None] = {}
    for dotenv_path in _dotenv_paths_from_env():
        if dotenv_path:
            merged.update(dotenv_values(dotenv_path))

    for key, value in merged.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


_load_dotenv_values()

# Model Definition (Official Google AI Studio / Gemini SDK)
# Default: "gemini-3.1-flash-lite" (High quota Free Tier: 1500 RPD / 250K TPM / 15 RPM)
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
API_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1/",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1/",
    "mistral": "https://api.mistral.ai/v1",
}
API_BASE_URL = os.getenv("API_BASE_URL") or API_BASE_URLS.get(LLM_PROVIDER)
API_KEYS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "groq": ("GROQ_API_KEY", "OPENAI_API_KEY"),
    "nvidia": ("NVIDIA_API_KEY", "OPENAI_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    "mistral": ("MISTRAL_API_KEY", "OPENAI_API_KEY")
}


def get_api_base_url(provider: str | None = None) -> str | None:
    """Returns an explicit API base URL or the default for the selected provider."""
    selected_provider = (provider or LLM_PROVIDER).strip().lower()
    return os.getenv("API_BASE_URL") or API_BASE_URLS.get(selected_provider)


def get_api_key(provider: str | None = None) -> str:
    """
    Returns the resolved API key for the selected provider.
    """
    selected_provider = (provider or LLM_PROVIDER).strip().lower()
    key_names = API_KEYS.get(selected_provider, ())
    return next((key for name in key_names if (key:=os.getenv(name))), "")


# Backward-compatible API_KEY resolution
API_KEY = get_api_key()

# Execution Parameters & Reproducibility
MAX_CEGIS_ITERS = int(os.getenv("MAX_CEGIS_ITERS", "5"))
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "2.0"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))  # 0.0 ensures deterministic output

# Rate Limit Prevention (Google AI Studio Free Tier: 15 RPM limit)
# 4.2s delay ensures <= 14.3 RPM to strictly avoid 429 Resource Exhausted
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "4.2"))

# Daily Quota Guard (Google AI Studio Free Tier: 1500 RPD limit / 250K TPM)
# Hard safety ceiling of 1450 requests before gracefully pausing
MAX_DAILY_REQUESTS = int(os.getenv("MAX_DAILY_REQUESTS", "1450"))

# Maximum number of ARC tasks evaluated concurrently.
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "8"))


def _load_llm_pool() -> list[LLMConfig]:
    """Parse provider:model entries and let each entry override global limits."""
    raw_pool = os.getenv("LLM_POOL", "")
    if not raw_pool.strip():
        return []

    pool = []
    for index, raw_entry in enumerate(raw_pool.split(","), start=1):
        parts = [part.strip() for part in raw_entry.split(":", 2)]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid LLM_POOL entry {raw_entry!r}; expected provider:model")
        provider, model = parts
        pool.append(LLMConfig(
            provider=provider.lower(),
            model=model,
            api_key=os.getenv(f"LLM_POOL_{index}_API_KEY"),
            request_delay=float(os.getenv(f"LLM_POOL_{index}_REQUEST_DELAY", str(REQUEST_DELAY))),
            max_daily_requests=int(os.getenv(
                f"LLM_POOL_{index}_MAX_DAILY_REQUESTS", str(MAX_DAILY_REQUESTS)
            )),
            max_concurrent_tasks=int(os.getenv(
                f"LLM_POOL_{index}_MAX_CONCURRENT_TASKS", str(MAX_CONCURRENT_TASKS)
            )),
            pool_index=index - 1,
        ))
    return pool


LLM_POOL = _load_llm_pool()
_POOL_INDEX = 0
_POOL_LOCK = threading.Lock()


def get_next_llm() -> LLMConfig:
    """Return the next pool entry in round-robin order, or the global config."""
    global _POOL_INDEX
    with _POOL_LOCK:
        if LLM_POOL:
            selected = LLM_POOL[_POOL_INDEX % len(LLM_POOL)]
            _POOL_INDEX += 1
            return selected
    return LLMConfig(LLM_PROVIDER, MODEL_NAME, REQUEST_DELAY, MAX_DAILY_REQUESTS, MAX_CONCURRENT_TASKS)

# Log file is truncated whenever a new experiment process starts.
LOG_FILE = os.getenv("LOG_FILE", "experiment.log")

THINKING = os.getenv("THINKING", "")

# Experiment variant controls
# ANTI_CHEAT: when "true", forces single-variant runs (only cegis_anticheat).
# In normal comparative runs, both variants are always executed.
ANTI_CHEAT = os.getenv("ANTI_CHEAT", "false").lower() == "true"

# INCLUDE_BASELINE: when "true", also runs the 1-shot baseline strategy alongside both CEGIS variants.
INCLUDE_BASELINE = os.getenv("INCLUDE_BASELINE", "false").lower() == "true"