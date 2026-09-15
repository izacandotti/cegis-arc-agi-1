"""
Experiment workflows for ARC-AGI CEGIS comparison study.

STRATEGIES:
- Baseline (1-shot):   Single LLM call, no feedback loop. Reference only (--include-baseline).
- CEGIS Padrão:        Counterexample feedback loop WITHOUT any anti-cheat rules.
                       The model receives only structural constraints (no imports).
                       This is the control group — may produce false convergences via hardcoding.
- CEGIS Antitrapaça:   Counterexample feedback loop WITH anti-cheat rules injected in every
                       feedback message (NOT in the initial prompt — the model hasn't seen any
                       expected output yet at that point, so hardcoding is not applicable).
                       Explicitly forbids hardcoding coordinates and memorizing example outputs.
                       Goal: reduce FALSE CONVERGENCE without changing the initial specification.

KEY DESIGN DECISION — Anti-cheat only in feedback:
  Both variants use IDENTICAL initial prompts (build_initial_prompt with anti_cheat=False).
  The only difference is the counterexample feedback message: Padrão sends plain feedback,
  Antitrapaça appends ANTI_CHEAT_RULES. This makes existing CEGIS data (which already had
  anti-cheat in feedback) directly reusable as cegis_antitrapaca results.

FALSE CONVERGENCE:
  A task has false convergence when converged_train=True but success=False:
  the model's code passes all training examples (possibly via hardcoding) but fails
  on the hidden test pairs. This is the primary failure mode targeted by Antitrapaça.

TOKEN EFFICIENCY & TPM OPTIMIZATIONS:
- Compact Grids: Baseline and CEGIS use compact serialization without whitespace padding.
- CEGIS Context Pruning: Prompt = initial spec + latest code + active counterexample.
  Maintains constant-bounded size across all iterations (TPM guard).
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .llm import AuthError, QuotaExceededError, call_llm
from .prompts import build_counterexample_feedback, build_initial_prompt
from .sandbox import extract_python_code, run_transform


def evaluate_on_test(
    code_str: str,
    test_pairs: List[Dict[str, List[List[int]]]]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Evaluates the generated transform function against all test pairs.
    Returns (all_passed: bool, test_results: list).
    """
    test_results = []
    all_passed = True
    for i, pair in enumerate(test_pairs):
        inp = pair["input"]
        expected = pair["output"]
        success, actual, error_msg = run_transform(code_str, inp)
        is_match = (success and actual == expected)
        if not is_match:
            all_passed = False
        test_results.append({
            "test_idx": i,
            "success": success,
            "is_correct": is_match,
            "error_msg": error_msg,
            "actual_output": actual,
            "expected_output": expected,
        })
    return all_passed, test_results


def run_baseline(task: Dict[str, Any], model: Optional[str] = None) -> Dict[str, Any]:
    """
    Baseline Strategy: Single-turn LLM generation and evaluation on test pairs.
    Reference strategy only — not the primary comparison focus.
    """
    train_pairs = task.get("train", [])
    test_pairs = task.get("test", [])

    messages = [
        {"role": "system", "content": "You are an expert AI solving ARC-AGI puzzles by writing Python code."},
        {"role": "user", "content": build_initial_prompt(train_pairs, anti_cheat=False)},
    ]

    start_time = time.time()
    try:
        response_text = call_llm(messages, model=model) if model else call_llm(messages)
    except (AuthError, QuotaExceededError):
        raise
    except Exception as e:
        return {
            "strategy": "baseline",
            "success": False,
            "api_error": True,
            "error": f"LLM Call Failed: {str(e)}",
            "latency": time.time() - start_time,
            "generated_code": "",
            "test_results": [],
        }

    code_str = extract_python_code(response_text)
    all_test_passed, test_results = evaluate_on_test(code_str, test_pairs)
    latency = time.time() - start_time

    return {
        "strategy": "baseline",
        "success": all_test_passed,
        "api_error": False,
        "latency": latency,
        "generated_code": code_str,
        "test_results": test_results,
    }


def _run_cegis_core(
    task: Dict[str, Any],
    anti_cheat: bool,
    max_iters: int = config.MAX_CEGIS_ITERS,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Internal CEGIS engine shared by both variants.
    Iteratively refines code using failed training examples as counterexamples.
    Applies Context Pruning to ensure token usage per request remains bounded (TPM guard).

    Args:
        task: ARC task dict with 'train' and 'test' pairs.
        anti_cheat: If True, injects ANTI_CHEAT_RULES only in counterexample feedback messages.
                    The initial prompt is IDENTICAL in both variants (anti_cheat=False always).
                    This is the key experimental variable for studying false convergence.
        max_iters: Maximum refinement iterations.
        model: Optional model name override.
    """
    strategy_name = "cegis_antitrapaca" if anti_cheat else "cegis_padrao"
    train_pairs = task.get("train", [])
    test_pairs = task.get("test", [])

    # Both variants use the SAME initial prompt — anti-cheat only applies to feedback.
    # Rationale: on the first attempt, the LLM has not received any expected output yet,
    # so there is nothing to hardcode. The anti-cheat restriction only becomes relevant
    # after the first counterexample reveals the expected output.
    initial_prompt = build_initial_prompt(train_pairs, anti_cheat=False)
    messages = [
        {"role": "system", "content": "You are an expert AI solving ARC-AGI puzzles by writing Python code."},
        {"role": "user", "content": initial_prompt},
    ]

    start_time = time.time()
    iteration_history = []
    converged_train = False
    current_code = ""
    had_api_error = False

    for iteration in range(1, max_iters + 1):
        try:
            response_text = call_llm(messages, model=model) if model else call_llm(messages)
        except (AuthError, QuotaExceededError):
            raise
        except Exception as e:
            had_api_error = True
            iteration_history.append({"iteration": iteration, "error": f"LLM Call Failed: {str(e)}"})
            break

        current_code = extract_python_code(response_text)

        # Validate against all training examples
        failed_example: Optional[Tuple[int, List[List[int]], List[List[int]], Optional[List[List[int]]], str]] = None
        for idx, pair in enumerate(train_pairs):
            inp = pair["input"]
            expected = pair["output"]
            success, actual, error_msg = run_transform(current_code, inp)

            if not success or actual != expected:
                failed_example = (idx, inp, expected, actual, error_msg)
                break

        if failed_example is None:
            # Successfully passed 100% of training demonstrations
            converged_train = True
            iteration_history.append({
                "iteration": iteration,
                "status": "passed_all_train",
                "code": current_code
            })
            break
        else:
            idx, inp, expected, actual, error_msg = failed_example
            iteration_history.append({
                "iteration": iteration,
                "status": "failed_train_example",
                "failed_index": idx,
                "error_msg": error_msg,
                "code": current_code
            })
            # Generate semantic counterexample feedback.
            # KEY: anti_cheat flag applies ONLY here, not in the initial prompt.
            feedback_msg = build_counterexample_feedback(
                idx, inp, expected, actual, error_msg, anti_cheat=anti_cheat
            )

            # Context Pruning (TPM Protection):
            # Prompt = initial spec + latest code candidate + active counterexample.
            # Maintains constant-bounded size across all CEGIS iterations.
            messages = [
                {"role": "system", "content": "You are an expert AI solving ARC-AGI puzzles by writing Python code."},
                {"role": "user", "content": initial_prompt},
                {"role": "assistant", "content": f"```python\n{current_code}\n```"},
                {"role": "user", "content": feedback_msg},
            ]

    # Evaluate final candidate code on test pairs
    all_test_passed, test_results = evaluate_on_test(current_code, test_pairs) if current_code else (False, [])
    latency = time.time() - start_time

    # Detect false convergence: model passed training but failed on the hidden test
    false_convergence = converged_train and not all_test_passed

    return {
        "strategy": strategy_name,
        "success": all_test_passed,
        "api_error": had_api_error,
        "converged_train": converged_train,
        "false_convergence": false_convergence,  # Key metric for the experiment
        "iterations_used": len(iteration_history),
        "latency": latency,
        "generated_code": current_code,
        "iteration_history": iteration_history,
        "test_results": test_results,
    }


def run_cegis_padrao(
    task: Dict[str, Any],
    max_iters: int = config.MAX_CEGIS_ITERS,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    CEGIS Padrão: Counterexample feedback loop WITHOUT any anti-cheat rules.
    Initial prompt and all feedback messages contain only structural constraints (no imports).
    This is the control group — the model may produce false convergences via hardcoding.
    """
    return _run_cegis_core(task, anti_cheat=False, max_iters=max_iters, model=model)


def run_cegis_antitrapaca(
    task: Dict[str, Any],
    max_iters: int = config.MAX_CEGIS_ITERS,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    CEGIS Antitrapaça: Counterexample feedback loop WITH anti-cheat rules injected
    in every counterexample feedback message (but NOT the initial prompt).

    Rationale for feedback-only: on the first attempt, the model has not yet seen any
    expected output, so hardcoding is not possible. The anti-cheat constraint only
    becomes relevant after the first counterexample reveals the expected output.
    This also makes existing CEGIS experiment data directly reusable as Antitrapaça results.

    The anti-cheat rules injected in feedback explicitly forbid:
    - Hardcoding specific coordinates or grid values
    - Branching on example indices
    - Memorizing/replicating specific output grids from the feedback

    Hypothesis: Reduces false convergence (converged_train=True, success=False)
    by steering the model toward generalizable geometric/mathematical transformations.
    """
    return _run_cegis_core(task, anti_cheat=True, max_iters=max_iters, model=model)


# Backward-compatible aliases
def run_cegis_standard(
    task: Dict[str, Any],
    max_iters: int = config.MAX_CEGIS_ITERS,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for run_cegis_padrao. Kept for backward compatibility."""
    return run_cegis_padrao(task, max_iters=max_iters, model=model)


def run_cegis(
    task: Dict[str, Any],
    max_iters: int = config.MAX_CEGIS_ITERS,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for run_cegis_padrao. Kept for backward compatibility."""
    return run_cegis_padrao(task, max_iters=max_iters, model=model)
