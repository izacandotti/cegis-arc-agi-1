"""
LLM Client Module for interacting with Google Gemini or OpenAI-compatible APIs such as Groq.
Includes proactive Rate Limiting (RPM), Daily Quota Guard (RPD),
and intelligent 429/RPM wait-and-retry protections.
"""

import random
import re
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import errors, types

from . import config


logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when authentication with the Google Gemini API fails (e.g. 401, 403, invalid key)."""
    pass


class QuotaExceededError(Exception):
    """Raised when the session/daily request count reaches the Free Tier safety limit."""
    pass


# Global tracking for API calls and proactive rate limiting
_REQUEST_COUNT: int = 0
_LAST_REQUEST_TIME: float = 0.0
_POOL_REQUEST_COUNTS: Dict[str, int] = {}
_POOL_LAST_REQUEST_TIMES: Dict[str, float] = {}
_POOL_SEMAPHORES: Dict[str, threading.BoundedSemaphore] = {}
_CLIENT_CACHE: Dict[str, Any] = {}
_REQUEST_LOCK = threading.Lock()


def get_request_count() -> int:
    """Returns the total number of API requests made in this session."""
    with _REQUEST_LOCK:
        return _REQUEST_COUNT


def reset_request_count(value: int = 0) -> None:
    """Resets or initializes the session request counter."""
    global _REQUEST_COUNT
    with _REQUEST_LOCK:
        _REQUEST_COUNT = value
        _POOL_REQUEST_COUNTS.clear()
        _POOL_LAST_REQUEST_TIMES.clear()
        _POOL_SEMAPHORES.clear()


def _reserve_request_slot(llm_config: config.LLMConfig) -> None:
    """Serializes rate-limit waiting and quota accounting for concurrent workers."""
    global _REQUEST_COUNT, _LAST_REQUEST_TIME

    pool_key = f"{llm_config.pool_index}:{llm_config.provider}:{llm_config.model}"
    with _REQUEST_LOCK:
        semaphore = _POOL_SEMAPHORES.setdefault(
            pool_key, threading.BoundedSemaphore(max(1, llm_config.max_concurrent_tasks))
        )
    semaphore.acquire()

    with _REQUEST_LOCK:
        pool_count = _POOL_REQUEST_COUNTS.get(pool_key, 0)
        if pool_count >= llm_config.max_daily_requests:
            semaphore.release()
            raise QuotaExceededError(
                f"Daily request safety limit reached for {pool_key} ({pool_count}/{llm_config.max_daily_requests} requests). "
                "Execution paused gracefully. Use checkpoint resume to continue when quota resets."
            )

        _wait_for_rate_limit(llm_config.request_delay, _POOL_LAST_REQUEST_TIMES.get(pool_key, 0.0))
        _LAST_REQUEST_TIME = time.time()
        _REQUEST_COUNT += 1
        _POOL_REQUEST_COUNTS[pool_key] = pool_count + 1
        _POOL_LAST_REQUEST_TIMES[pool_key] = _LAST_REQUEST_TIME


def _extract_retry_delay(error: Exception) -> Optional[float]:
    """
    Extracts retry delay in seconds from Gemini API errors if present.
    Checks structured error details, dictionaries, and regex matches in the error message.
    """
    # 1. Check structured details or response dictionary if available
    details = getattr(error, "details", None) or getattr(error, "errors", None)
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                # Check for RetryInfo (e.g. {'@type': '...RetryInfo', 'retryDelay': '24s'})
                delay_val = item.get("retryDelay") or item.get("retry_delay")
                if delay_val:
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(delay_val))
                    if m:
                        try:
                            return float(m.group(1))
                        except ValueError:
                            pass

    # 2. Check regex patterns on string representation
    err_str = str(error)

    # Pattern: "Please retry in 24.367063794s" or "retry in 24s"
    m = re.search(r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)\s*s", err_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    # Pattern: 'retryDelay': '24s' or "retry_delay": "24s"
    m = re.search(r"retry_?delay['\"]\s*:\s*['\"]([0-9]+(?:\.[0-9]+)?)\s*s?['\"]", err_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    # Pattern: "retry after 24" / "retry-after: 24"
    m = re.search(r"retry[-_\s]after[:\s]+([0-9]+(?:\.[0-9]+)?)", err_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    return None


def _wait_for_rate_limit(request_delay: float, last_request_time: float) -> None:
    """
    Enforces minimum delay between API calls to guarantee compliance with Free Tier RPM limits.
    """
    if request_delay > 0 and last_request_time > 0:
        elapsed = time.time() - last_request_time
        if elapsed < request_delay:
            sleep_needed = request_delay - elapsed
            time.sleep(sleep_needed)


def _release_request_slot(llm_config: config.LLMConfig) -> None:
    pool_key = f"{llm_config.pool_index}:{llm_config.provider}:{llm_config.model}"
    semaphore = _POOL_SEMAPHORES.get(pool_key)
    if semaphore is not None:
        semaphore.release()


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Initializes and caches a Google GenAI Client instance to prevent repeated
    initialization warnings and overhead on every request.
    """
    global _CLIENT_CACHE
    key = api_key or config.get_api_key("gemini")
    if not key:
        raise AuthError(
            "Google Gemini API Key is missing. "
            "Please export GEMINI_API_KEY or GOOGLE_API_KEY in your environment."
        )
    if key not in _CLIENT_CACHE:
        _CLIENT_CACHE[key] = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=120000))
    return _CLIENT_CACHE[key]


def get_openai_compatible_client(provider: str, api_key: Optional[str] = None) -> Any:
    """Initializes and caches an OpenAI-compatible client, including Groq."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "The OpenAI SDK is required for OpenAI-compatible providers. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from e

    key = api_key or config.get_api_key(provider)
    if not key:
        raise AuthError(
            f"{provider.title()} API key is missing. Please export {provider.upper()}_API_KEY."
        )

    base_url = config.get_api_base_url(provider)
    cache_key = f"{provider}:{key}:{base_url}"
    if cache_key not in _CLIENT_CACHE:
        client_kwargs: Dict[str, str] = {"api_key": key}
        if base_url:
            client_kwargs["base_url"] = base_url
        _CLIENT_CACHE[cache_key] = OpenAI(**client_kwargs)
    return _CLIENT_CACHE[cache_key]


def _call_openai_compatible(
    messages: List[Dict[str, str]],
    model: str,
    provider: str,
    api_key: Optional[str],
    max_retries: int,
    llm_config: config.LLMConfig,
) -> str:
    """Calls an OpenAI-compatible chat-completions endpoint with retries."""
    client = get_openai_compatible_client(provider, api_key=api_key)
    base_delay = 2.0

    for attempt in range(1, max_retries + 1):
        slot_reserved = False
        try:
            _reserve_request_slot(llm_config)
            slot_reserved = True
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config.TEMPERATURE,
                stream=False
            )
            result = response.choices[0].message.content or ""
            _release_request_slot(llm_config)
            return result
        except Exception as e:
            if slot_reserved:
                _release_request_slot(llm_config)
            status_code = getattr(e, "status_code", None) or getattr(e, "code", None)
            err_msg = str(e).lower()

            if status_code in (401, 403) or any(
                term in err_msg for term in ["unauthorized", "invalid api key", "authentication"]
            ):
                raise AuthError(f"Fatal {provider.title()} authentication error: {e}") from e

            if status_code == 404 or "model not found" in err_msg or "not_found" in err_msg:
                raise RuntimeError(
                    f"Fatal {provider.title()} model error: model '{model}' was not found.\n{e}"
                ) from e

            if status_code == 429 or "rate limit" in err_msg or "too many requests" in err_msg:
                if attempt == max_retries:
                    raise QuotaExceededError(
                        f"{provider.title()} rate limit exceeded after {max_retries} retries: {e}"
                    ) from e
                time.sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0.5, 1.5))
                continue

            if attempt == max_retries:
                raise RuntimeError(
                    f"{provider.title()} API call failed after {max_retries} attempts: {e}"
                ) from e
            time.sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0.5, 1.5))

    return ""


def format_messages_for_gemini(
    messages: List[Dict[str, str]]
) -> tuple[Optional[str], List[types.Content]]:
    """
    Separates system instructions and formats conversation history into Gemini Content objects.
    """
    system_parts: List[str] = []
    contents: List[types.Content] = []

    for msg in messages:
        role = msg.get("role", "user").lower()
        content_text = msg.get("content", "")

        if role == "system":
            if content_text:
                system_parts.append(content_text)
        elif role in ("assistant", "model"):
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=content_text)]
                )
            )
        else:  # "user" or any other role
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=content_text)]
                )
            )

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, contents


def call_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    max_retries: int = 36,
) -> str:
    """
    Sends chat messages to the Google Gemini API with proactive rate limiting,
    daily quota guard, and intelligent 429/RPM wait-and-retry.
    
    Args:
        messages: List of message dicts with 'role' and 'content'.
        model: Target Gemini model identifier (e.g. 'gemini-3.1-flash-lite').
        api_key: Optional Gemini API key override.
        max_retries: Maximum retry attempts for transient errors (429, 503, timeouts).
        
    Returns:
        Generated text response from the model.
        
    Raises:
        QuotaExceededError: If the daily request ceiling (e.g. 1450) is reached or hard quota lock.
        AuthError: If authentication fails (401/403 or missing API key).
        RuntimeError: If all retries are exhausted.
    """
    global _REQUEST_COUNT, _LAST_REQUEST_TIME

    system_instruction, contents = format_messages_for_gemini(messages)

    gen_config = types.GenerateContentConfig(
        temperature=config.TEMPERATURE,
        max_output_tokens=2048,
        system_instruction=system_instruction,
    )

    if not contents:
        raise ValueError("At least one user message is required")

    base_delay = 2.0

    for attempt in range(1, max_retries + 1):
        llm_config = config.get_next_llm() if provider is None and model is None else config.LLMConfig(
            provider=(provider or config.LLM_PROVIDER).strip().lower(),
            model=model or config.MODEL_NAME,
            request_delay=config.REQUEST_DELAY,
            max_daily_requests=config.MAX_DAILY_REQUESTS,
            max_concurrent_tasks=config.MAX_CONCURRENT_TASKS,
        )
        selected_provider = llm_config.provider
        target_model = llm_config.model

        if selected_provider not in ("gemini", "google"):
            if config.get_api_base_url(selected_provider):
                if api_key or config.get_api_key(selected_provider):
                    return _call_openai_compatible(
                        messages, target_model, selected_provider, api_key or llm_config.api_key, max_retries, llm_config
                    )
                else:
                    raise ValueError(f"Empty API_KEY")

        client = get_gemini_client(api_key=api_key or llm_config.api_key)
        slot_reserved = False
        try:
            # Reserve the quota and rate-limit slot before making the request.
            _reserve_request_slot(llm_config)
            slot_reserved = True
            logger.debug(
                "Starting API request: model=%s key_idx=%s attempt=%s request=%s/%s",
                target_model,
                llm_config.pool_index,
                attempt,
                get_request_count(),
                config.MAX_DAILY_REQUESTS,
            )

            response = client.models.generate_content(
                model=target_model,
                contents=contents,
                config=gen_config,
            )

            if response.text:
                logger.debug(
                    "API request succeeded: model=%s chars=%s attempt=%s request=%s/%s",
                    target_model,
                    len(response.text),
                    attempt,
                    get_request_count(),
                    config.MAX_DAILY_REQUESTS,
                )
                _release_request_slot(llm_config)
                return response.text
            _release_request_slot(llm_config)
            return ""

        except errors.APIError as e:
            if slot_reserved:
                _release_request_slot(llm_config)
            status_code = getattr(e, "code", None) or getattr(e, "status_code", None)
            err_msg = str(e).lower()

            if status_code in (401, 403) or any(term in err_msg for term in ["unauthorized", "invalid api key", "unauthenticated"]):
                raise AuthError(f"Fatal Gemini Authentication Error (Status: {status_code}): {e}") from e

            if status_code == 404 or "not_found" in err_msg or "no longer available" in err_msg:
                raise RuntimeError(
                    f"Fatal Gemini Model Error (404 NOT_FOUND): Model '{target_model}' was not found or is no longer available.\n{e}"
                ) from e

            # Handle 429 Rate Limit / Quota Exhaustion
            if status_code == 429 or "resource_exhausted" in err_msg or "quota" in err_msg:
                retry_delay = _extract_retry_delay(e)
                if retry_delay is not None and retry_delay > 1800:
                    raise QuotaExceededError(
                        f"Google AI Studio Daily Quota Exceeded (Reset in {retry_delay:.0f}s): {e}"
                    ) from e

                if attempt == max_retries:
                    raise QuotaExceededError(
                        f"Google AI Studio Quota/Rate Limit Exceeded after {max_retries} retries: {e}"
                    ) from e

                # Sleep a short delay and let next attempt rotate to next API key in pool
                sleep_duration = min(6.0, (retry_delay or 4.0)) + random.uniform(0.5, 1.5)
                time.sleep(sleep_duration)
                continue

            # Retry other transient errors (500, 503, etc.)
            if attempt == max_retries:
                raise RuntimeError(
                    f"Gemini API call failed after {max_retries} attempts (Status: {status_code}): {e}"
                ) from e

            sleep_duration = min(10.0, base_delay + attempt * 0.5) + random.uniform(0.5, 1.5)
            time.sleep(sleep_duration)

        except Exception as e:
            if slot_reserved:
                _release_request_slot(llm_config)
            err_msg = str(e).lower()
            if any(term in err_msg for term in ["401", "403", "unauthorized", "invalid api key", "unauthenticated"]):
                raise AuthError(f"Fatal Gemini Authentication Error: {e}") from e

            if "404" in err_msg or "not_found" in err_msg or "no longer available" in err_msg:
                raise RuntimeError(
                    f"Fatal Gemini Model Error (404 NOT_FOUND): Model '{target_model}' was not found or is no longer available.\n{e}"
                ) from e

            if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                retry_delay = _extract_retry_delay(e)
                if retry_delay is not None and retry_delay > 1800:
                    raise QuotaExceededError(
                        f"Google AI Studio Daily Quota Exceeded (Reset in {retry_delay:.0f}s): {e}"
                    ) from e

                if attempt == max_retries:
                    raise QuotaExceededError(
                        f"Google AI Studio Quota/Rate Limit Exceeded after {max_retries} retries: {e}"
                    ) from e

                sleep_duration = min(6.0, (retry_delay or 4.0)) + random.uniform(0.5, 1.5)
                time.sleep(sleep_duration)
                continue

            if attempt == max_retries:
                raise RuntimeError(
                    f"Gemini API call failed after {max_retries} attempts: {e}"
                ) from e

            sleep_duration = min(10.0, base_delay + attempt * 0.5) + random.uniform(0.5, 1.5)
            time.sleep(sleep_duration)

    return ""
