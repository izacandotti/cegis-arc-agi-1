"""
Main entry point for the ARC-AGI CEGIS comparison experiment.

PRIMARY COMPARISON: CEGIS Padrão vs CEGIS Antitrapaça
Research question: Does injecting anti-cheat rules (forbidding hardcoding/memorization)
in counterexample feedback messages reduce false convergence?

FALSE CONVERGENCE definition:
  A task is considered a false convergence when converged_train=True but success=False:
  the model's code passes all training examples (possibly via hardcoding) but fails
  on the hidden test pairs. This is the primary failure mode CEGIS+Anti-Cheat targets.

OPTIONAL: Pass --include-baseline to also run a 1-shot baseline for historical comparison.

Includes Proactive Rate Limiter (RPM), Daily Quota Guard (RPD), and Checkpoint/Resume.
Supports Google Gemini and OpenAI-compatible providers (Groq, Mistral, OpenRouter, etc.).
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
import re
from typing import Any, Dict, List, Set

from arc_cegis import (
    AuthError,
    QuotaExceededError,
    config,
    get_request_count,
    load_tasks,
    run_baseline,
    run_cegis_padrao,
    run_cegis_antitrapaca,
    call_llm,
)


logger = logging.getLogger(__name__)
PROGRESS_CHECKPOINT_INTERVAL = 5


_EMERGENCY_STATE: Dict[str, Any] = {
    "output_path": "results_experiment.json",
    "model": config.MODEL_NAME,
    "max_iters": config.MAX_CEGIS_ITERS,
    "total_tasks": 0,
    "detailed_results": [],
    "cegis_padrao_correct": 0,
    "cegis_antitrapaca_correct": 0,
    "baseline_correct": 0,
    "faulty_task_ids": set(),
}


_LONG_NUMERIC_LIST_RE = re.compile(r"\[(?:\s+\d+,?)+\s*\]")
_LONG_NUMERIC_LIST_ITEM_RE = re.compile(r"\s*(\d)(,?)\s*")
def compact_long_numeric_lists(serialized: str) -> str:
    """Keep long numeric JSON arrays on one line to reduce checkpoint size."""
    def compact(match: re.Match[str]) -> str:
        return _LONG_NUMERIC_LIST_ITEM_RE.sub(r"\1\2", match.group(0))

    return _LONG_NUMERIC_LIST_RE.sub(compact, serialized)


def perform_health_check(model: str | None) -> None:
    """
    Executes a fast test query to validate API key, connectivity, and model availability.
    Terminates execution immediately if the check fails.
    """
    logger.info("Performing initial %s API health check...", config.LLM_PROVIDER)
    test_messages = [{"role": "user", "content": "Responda apenas 'OK'"}]
    try:
        response = call_llm(test_messages, model=model, max_retries=3) if model else call_llm(
            test_messages, max_retries=3
        )
        logger.info("Health check PASSED! Model '%s' responded successfully: %s", model, response.strip()[:30])
    except AuthError as auth_err:
        logger.critical("FATAL AUTHENTICATION ERROR: %s", auth_err)
        logger.critical("Please verify the API key for provider '%s' is correctly set.", config.LLM_PROVIDER)
        raise SystemExit(1)
    except QuotaExceededError as q_err:
        logger.critical("FATAL QUOTA ERROR: %s", q_err)
        raise SystemExit(1)
    except Exception as err:
        logger.critical("FATAL HEALTH CHECK ERROR: Failed to connect to %s API: %s", config.LLM_PROVIDER, err)
        logger.critical("Verify internet connectivity and model name '%s'.", model)
        raise SystemExit(1)


def save_checkpoint(
    output_path: str,
    model: str,
    max_iters: int,
    total_tasks: int,
    detailed_results: List[Dict[str, Any]],
    cegis_padrao_correct: int,
    cegis_antitrapaca_correct: int,
    faulty_task_ids: Set[str],
    baseline_correct: int = 0,
    include_baseline: bool = False,
    checkpoint_error: str = "",
) -> None:
    """
    Safely writes current experiment state and results to JSON disk.
    Primary summary focuses on the CEGIS Padrão vs CEGIS Antitrapaça comparison.
    """
    completed_count = len(detailed_results)
    padrao_acc = (cegis_padrao_correct / completed_count) * 100 if completed_count > 0 else 0.0
    antitrapaca_acc = (cegis_antitrapaca_correct / completed_count) * 100 if completed_count > 0 else 0.0
    gain = antitrapaca_acc - padrao_acc

    # Compute false convergence rates
    padrao_false_conv = sum(
        1 for r in detailed_results
        if r.get("cegis_padrao", {}).get("false_convergence", False)
    )
    antitrapaca_false_conv = sum(
        1 for r in detailed_results
        if r.get("cegis_antitrapaca", {}).get("false_convergence", False)
    )

    summary: Dict[str, Any] = {
        "cegis_padrao_accuracy": padrao_acc,
        "cegis_antitrapaca_accuracy": antitrapaca_acc,
        "absolute_gain": gain,
        "cegis_padrao_correct": cegis_padrao_correct,
        "cegis_antitrapaca_correct": cegis_antitrapaca_correct,
        "false_convergence_padrao": padrao_false_conv,
        "false_convergence_antitrapaca": antitrapaca_false_conv,
        "false_convergence_reduction": padrao_false_conv - antitrapaca_false_conv,
    }
    if include_baseline:
        base_acc = (baseline_correct / completed_count) * 100 if completed_count > 0 else 0.0
        summary["baseline_accuracy"] = base_acc
        summary["baseline_correct"] = baseline_correct

    total_llm_requests = sum(
        (r.get("cegis_padrao", {}).get("iterations_used") or len(r.get("cegis_padrao", {}).get("iteration_history", []))) +
        (r.get("cegis_antitrapaca", {}).get("iterations_used") or len(r.get("cegis_antitrapaca", {}).get("iteration_history", []))) +
        (1 if ("baseline" in r and r.get("baseline", {}).get("generated_code")) else 0)
        for r in detailed_results
    )

    output_payload = {
        "config": {
            "model": model,
            "max_cegis_iters": max_iters,
            "timeout_seconds": config.TIMEOUT_SECONDS,
            "request_delay_seconds": config.REQUEST_DELAY,
            "max_daily_requests": config.MAX_DAILY_REQUESTS,
            "total_tasks_in_dataset": total_tasks,
            "completed_tasks": completed_count,
            "faulty_tasks": len(faulty_task_ids),
            "total_requests_used": total_llm_requests,
            "include_baseline": include_baseline,
        },
        "summary": summary,
        "results": detailed_results,
        "faulty_task_ids": sorted(faulty_task_ids),
    }
    if checkpoint_error:
        output_payload["emergency_error"] = checkpoint_error

    temp_path = f"{output_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        serialized_payload = json.dumps(output_payload, indent=2)
        f.write(compact_long_numeric_lists(serialized_payload))
    os.replace(temp_path, output_path)


def save_markdown_report(
    report_path: str,
    model: str,
    total_tasks: int,
    detailed_results: List[Dict[str, Any]],
    cegis_padrao_correct: int,
    cegis_antitrapaca_correct: int,
    faulty_task_ids: Set[str],
    baseline_correct: int = 0,
    include_baseline: bool = False,
) -> None:
    """
    Saves a Markdown report focused on the CEGIS Padrão vs CEGIS Antitrapaça comparison.
    Highlights false convergence rates as the primary research metric.
    """
    completed_count = len(detailed_results)
    padrao_acc = (cegis_padrao_correct / completed_count) * 100 if completed_count > 0 else 0.0
    antitrapaca_acc = (cegis_antitrapaca_correct / completed_count) * 100 if completed_count > 0 else 0.0
    gain = antitrapaca_acc - padrao_acc
    gain_sign = "+" if gain > 0 else ""
    progress_pct = (completed_count / total_tasks * 100) if total_tasks > 0 else 0.0

    padrao_false_conv = sum(
        1 for r in detailed_results
        if r.get("cegis_padrao", {}).get("false_convergence", False)
    )
    antitrapaca_false_conv = sum(
        1 for r in detailed_results
        if r.get("cegis_antitrapaca", {}).get("false_convergence", False)
    )
    fc_reduction = padrao_false_conv - antitrapaca_false_conv

    total_llm_requests = sum(
        (r.get("cegis_padrao", {}).get("iterations_used") or len(r.get("cegis_padrao", {}).get("iteration_history", []))) +
        (r.get("cegis_antitrapaca", {}).get("iterations_used") or len(r.get("cegis_antitrapaca", {}).get("iteration_history", []))) +
        (1 if ("baseline" in r and r.get("baseline", {}).get("generated_code")) else 0)
        for r in detailed_results
    )

    lines = [
        "# 📊 Relatório: CEGIS Padrão vs CEGIS Antitrapaça",
        "",
        f"- **Modelo:** `{model}`",
        f"- **Progresso:** **{completed_count}/{total_tasks}** tarefas concluídas (**{progress_pct:.1f}%**)",
        f"- **Total de Requisições LLM:** {total_llm_requests}",
        "",
        "## 🔬 Hipótese",
        "",
        "O prompt anti-cheat (que proíbe hardcoding e memorização de saídas) reduz a **falsa convergência**:",
        "situações em que o modelo passa em todos os exemplos de treino (`converged_train=True`) mas falha",
        "nos pares de teste ocultos (`success=False`). A métrica central é a taxa de falsa convergência.",
        "",
        "## 📈 Resultados Comparativos",
        "",
        "| Métrica | CEGIS Standard | CEGIS+Anti-Cheat | Δ Ganho |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Acurácia (sucesso no teste)** | {padrao_acc:.2f}% | {antitrapaca_acc:.2f}% | **{gain_sign}{gain:.2f}%** |",
        f"| **Tarefas Corretas** | {cegis_padrao_correct}/{completed_count} | {cegis_antitrapaca_correct}/{completed_count} | {cegis_antitrapaca_correct - cegis_padrao_correct:+d} |",
        f"| **Falsas Convergências** | {padrao_false_conv} | {antitrapaca_false_conv} | **{fc_reduction:+d}** |",
    ]

    if include_baseline and baseline_correct > 0:
        base_acc = (baseline_correct / completed_count) * 100 if completed_count > 0 else 0.0
        lines.append(f"| **Baseline 1-shot (ref.)** | {base_acc:.2f}% | — | — |")

    lines += [
        "",
        "## 📝 Log por Tarefa",
        "",
        "| # | Task ID | Padrão | Antitrapaça | Iter P | Iter AT | FC-P | FC-AT | Impacto |",
        "| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for idx, item in enumerate(detailed_results, 1):
        task_id = item.get("task_id", f"task_{idx}")
        padrao_res = item.get("cegis_padrao", {})
        at_res = item.get("cegis_antitrapaca", {})
        padrao_ok = padrao_res.get("success", False)
        at_ok = at_res.get("success", False)
        padrao_iters = padrao_res.get("iterations_used", 1)
        at_iters = at_res.get("iterations_used", 1)
        padrao_fc = "⚠️" if padrao_res.get("false_convergence", False) else "—"
        at_fc = "⚠️" if at_res.get("false_convergence", False) else "—"

        padrao_str = "✅" if padrao_ok else "❌"
        at_str = "✅" if at_ok else "❌"

        if not padrao_ok and at_ok:
            impact = "🚀 **Antitrapaça corrigiu**"
        elif padrao_ok and not at_ok:
            impact = "⚠️ Padrão ganhou"
        elif padrao_ok and at_ok:
            impact = "🎯 Ambos corretos"
        else:
            impact = "❌ Ambos falharam"

        lines.append(
            f"| {idx} | `{task_id}` | {padrao_str} | {at_str} | {padrao_iters} | {at_iters} | {padrao_fc} | {at_fc} | {impact} |"
        )

    if faulty_task_ids:
        lines.append("")
        lines.append("## ⚠️ Tarefas com Erro de Execução")
        for ft in sorted(faulty_task_ids):
            lines.append(f"- `{ft}`")

    content = "\n".join(lines) + "\n"
    temp_path = f"{report_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(temp_path, report_path)


def progress_checkpoint_path(output_path: str, completed_count: int, total_tasks: int) -> str:
    """Build a progress-labelled checkpoint path beside the main output file."""
    output_root, extension = os.path.splitext(output_path)
    return f"{output_root}_{completed_count}_{total_tasks}{extension}"


def load_checkpoint(output_path: str) -> tuple[List[Dict[str, Any]], int, int, int, Set[str], Set[str]]:
    """
    Loads completed task results from an existing checkpoint file.
    Returns (detailed_results, cegis_padrao_correct, cegis_antitrapaca_correct,
             baseline_correct, completed_task_ids, faulty_task_ids).
    """
    if not os.path.exists(output_path):
        return [], 0, 0, 0, set(), set()

    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        detailed_results = data.get("results", [])
        cegis_padrao_correct = 0
        cegis_antitrapaca_correct = 0
        baseline_correct = 0
        completed_task_ids = set()
        faulty_task_ids = set(data.get("faulty_task_ids", []))

        valid_results = []
        for item in detailed_results:
            task_id = item.get("task_id")
            # If the task suffered an API failure, don't consider it completed so it can be retried
            padrao_api_err = item.get("cegis_padrao", {}).get("api_error", False)
            if padrao_api_err:
                logger.info("Task %s had API error in previous checkpoint; discarding to retry.", task_id)
                continue
            if task_id:
                completed_task_ids.add(task_id)
            if item.get("cegis_padrao", {}).get("success"):
                cegis_padrao_correct += 1
            if item.get("cegis_antitrapaca", {}).get("success"):
                cegis_antitrapaca_correct += 1
            if item.get("baseline", {}).get("success"):
                baseline_correct += 1
            valid_results.append(item)

        return valid_results, cegis_padrao_correct, cegis_antitrapaca_correct, baseline_correct, completed_task_ids, faulty_task_ids
    except Exception as e:
        logger.warning("Failed to read checkpoint from '%s': %s. Starting fresh.", output_path, e)
        return [], 0, 0, 0, set(), set()


def save_emergency_checkpoint(error: BaseException) -> None:
    """Best-effort save to a separate file when main exits unexpectedly."""
    state = _EMERGENCY_STATE
    emergency_path = f"{state['output_path']}.emergency.json"
    error_message = f"{type(error).__name__}: {error}"
    try:
        save_checkpoint(
            output_path=emergency_path,
            model=state["model"],
            max_iters=state["max_iters"],
            total_tasks=state["total_tasks"],
            detailed_results=state["detailed_results"],
            cegis_padrao_correct=state["cegis_padrao_correct"],
            cegis_antitrapaca_correct=state["cegis_antitrapaca_correct"],
            baseline_correct=state["baseline_correct"],
            faulty_task_ids=state["faulty_task_ids"],
            checkpoint_error=error_message,
        )
        logger.critical("Emergency checkpoint saved to '%s'.", emergency_path)
    except Exception:
        logger.exception("Emergency checkpoint failed; attempting raw fallback.")
        try:
            with open(f"{emergency_path}.raw", "w", encoding="utf-8") as file:
                json.dump({"error": error_message, "state": state}, file, default=str, indent=2)
        except Exception:
            logger.exception("Raw emergency checkpoint also failed.")


def _run_main() -> None:
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    file_handler = logging.FileHandler(config.LOG_FILE, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler], force=True)

    if config.LLM_POOL:
        parsed_pool = [
            {
                "provider": llm_config.provider,
                "model": llm_config.model,
                "request_delay": llm_config.request_delay,
                "max_daily_requests": llm_config.max_daily_requests,
                "max_concurrent_tasks": llm_config.max_concurrent_tasks,
                "pool_index": llm_config.pool_index,
            }
            for llm_config in config.LLM_POOL
        ]
        logger.info("Parsed LLM pool: %s", parsed_pool)
    else:
        logger.info("Parsed LLM pool: empty; using global configuration.")

    parser = argparse.ArgumentParser(
        description="ARC-AGI CEGIS Experiment: Standard vs Anti-Cheat (False Convergence Study)"
    )
    parser.add_argument(
        "--tasks",
        type=str,
        default="./data",
        help="Path to ARC task JSON file or directory (default: ./data)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate (default: all)",
    )
    parser.add_argument(
        "--max-iters",
        type=int,
        default=config.MAX_CEGIS_ITERS,
        help=f"Maximum CEGIS refinement iterations per task (default: {config.MAX_CEGIS_ITERS})",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=("gemini", "groq", "nvidia", "openrouter", "mistral"),
        default=config.LLM_PROVIDER,
        help=f"LLM provider (default: {config.LLM_PROVIDER})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=config.MODEL_NAME,
        help=f"Model name / endpoint (default: {config.MODEL_NAME})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results_experiment.json",
        help="Output JSON path (default: results_experiment.json)",
    )
    parser.add_argument(
        "--markdown",
        type=str,
        default="progresso_experimento.md",
        help="Path to markdown progress report (default: progresso_experimento.md)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Automatically resume from existing checkpoint (default: True)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Overwrite existing output file and restart from scratch",
    )
    parser.add_argument(
        "--include-baseline",
        action="store_true",
        default=config.INCLUDE_BASELINE,
        help="Also run 1-shot baseline strategy for historical comparison (default: False)",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip the initial provider API connectivity check (not recommended)",
    )
    parser.add_argument(
        "--reuse-anticheat-from",
        type=str,
        default=None,
        help="Path to existing experiment JSON to reuse as the anti-cheat variant (avoids re-running it)",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=config.REQUEST_DELAY,
        help=f"Minimum delay between requests in seconds (default: {config.REQUEST_DELAY}s)",
    )
    parser.add_argument(
        "--max-daily-requests",
        type=int,
        default=config.MAX_DAILY_REQUESTS,
        help=f"Maximum daily requests ceiling (default: {config.MAX_DAILY_REQUESTS})",
    )
    args = parser.parse_args()

    _EMERGENCY_STATE.update({
        "output_path": args.output,
        "model": args.model,
        "max_iters": args.max_iters,
    })

    # Update dynamic config overrides
    config.REQUEST_DELAY = args.request_delay
    config.MAX_DAILY_REQUESTS = args.max_daily_requests
    config.LLM_PROVIDER = args.provider
    config.API_BASE_URL = config.get_api_base_url(args.provider)

    rpm_effective = int(60.0 / config.REQUEST_DELAY) if config.REQUEST_DELAY > 0 else 0

    logger.info("ARC-AGI CEGIS Experiment: Padrão vs Antitrapaça (%s)", config.LLM_PROVIDER)
    logger.info("Model: %s | Max CEGIS Iters: %s | Timeout: %ss", args.model, args.max_iters, config.TIMEOUT_SECONDS)
    logger.info(
        "Rate Delay: %ss (<= %s RPM) | Daily Quota Guard: %s RPD | Include Baseline: %s",
        config.REQUEST_DELAY, rpm_effective, config.MAX_DAILY_REQUESTS, args.include_baseline
    )

    # 1. Health check
    if not args.skip_health_check:
        perform_health_check(None if config.LLM_POOL else args.model)

    # 2. Load tasks
    tasks_dict = load_tasks(args.tasks)

    # 2b. Optional reuse of anti-cheat results from historical runs
    reused_anticheat_map: Dict[str, Dict[str, Any]] = {}
    reused_baseline_map: Dict[str, Dict[str, Any]] = {}
    if args.reuse_anticheat_from and os.path.exists(args.reuse_anticheat_from):
        try:
            with open(args.reuse_anticheat_from, "r", encoding="utf-8") as f:
                reused_data = json.load(f)
                for item in reused_data.get("results", []):
                    tid = item.get("task_id")
                    if tid:
                        ac_data = item.get("cegis_antitrapaca") or item.get("cegis")
                        if ac_data:
                            ac_copy = dict(ac_data)
                            ac_copy["strategy"] = "cegis_antitrapaca"
                            if "false_convergence" not in ac_copy:
                                ac_copy["false_convergence"] = bool(
                                    ac_copy.get("converged_train", False) and not ac_copy.get("success", False)
                                )
                            reused_anticheat_map[tid] = ac_copy
                        if "baseline" in item:
                            reused_baseline_map[tid] = item["baseline"]
            logger.info("Loaded %d anti-cheat result(s) from '%s' for reuse.", len(reused_anticheat_map), args.reuse_anticheat_from)
            if reused_anticheat_map:
                ordered_tasks = {}
                for tid in reused_anticheat_map:
                    if tid in tasks_dict:
                        ordered_tasks[tid] = tasks_dict[tid]
                tasks_dict = ordered_tasks
        except Exception as err:
            logger.warning("Failed to load reuse file '%s': %s", args.reuse_anticheat_from, err)

    if args.max_tasks:
        tasks_dict = dict(list(tasks_dict.items())[:args.max_tasks])

    total_tasks = len(tasks_dict)
    logger.info("Loaded %s task(s) in evaluation set.", total_tasks)
    _EMERGENCY_STATE["total_tasks"] = total_tasks
    task_order = {tid: i for i, tid in enumerate(tasks_dict.keys())}

    # 3. Checkpoint / Resume recovery
    detailed_results: List[Dict[str, Any]] = []
    cegis_padrao_correct = 0
    cegis_antitrapaca_correct = 0
    baseline_correct = 0
    completed_task_ids: Set[str] = set()
    faulty_task_ids: Set[str] = set()
    _EMERGENCY_STATE.update({
        "detailed_results": detailed_results,
        "faulty_task_ids": faulty_task_ids,
    })

    if args.resume and os.path.exists(args.output):
        (
            detailed_results,
            cegis_padrao_correct,
            cegis_antitrapaca_correct,
            baseline_correct,
            completed_task_ids,
            faulty_task_ids,
        ) = load_checkpoint(args.output)
        detailed_results.sort(key=lambda r: task_order.get(r.get("task_id", ""), 999999))
        _EMERGENCY_STATE.update({
            "detailed_results": detailed_results,
            "cegis_padrao_correct": cegis_padrao_correct,
            "cegis_antitrapaca_correct": cegis_antitrapaca_correct,
            "baseline_correct": baseline_correct,
            "faulty_task_ids": faulty_task_ids,
        })
        if completed_task_ids or faulty_task_ids:
            logger.info(
                "Checkpoint found. Resuming from '%s': %s completed, %s faulty "
                "(Padrão: %s, Antitrapaça: %s).",
                args.output, len(completed_task_ids), len(faulty_task_ids),
                cegis_padrao_correct, cegis_antitrapaca_correct,
            )

    if args.markdown:
        save_markdown_report(
            args.markdown, args.model, total_tasks, detailed_results,
            cegis_padrao_correct, cegis_antitrapaca_correct, faulty_task_ids,
            baseline_correct=baseline_correct, include_baseline=args.include_baseline,
        )

    consecutive_api_failures = 0
    CIRCUIT_BREAKER_THRESHOLD = 10
    quota_exhausted = False
    auth_failed = False

    def evaluate_task(task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run standard CEGIS (and reuse or run anti-cheat) for one task in a worker thread."""
        selected_model = None if config.LLM_POOL else args.model
        padrao_res = run_cegis_padrao(task_data, max_iters=args.max_iters, model=selected_model)
        if task_id in reused_anticheat_map:
            at_res = reused_anticheat_map[task_id]
        else:
            at_res = run_cegis_antitrapaca(task_data, max_iters=args.max_iters, model=selected_model)
        result: Dict[str, Any] = {
            "task_id": task_id,
            "cegis_padrao": padrao_res,
            "cegis_antitrapaca": at_res,
        }
        if args.include_baseline:
            if task_id in reused_baseline_map:
                result["baseline"] = reused_baseline_map[task_id]
            else:
                result["baseline"] = run_baseline(task_data, model=selected_model)
        return result

    # 4. Run evaluations with Protections and Incremental Checkpointing
    current_task_id: str | None = None
    previous_progress_path: str | None = None
    try:
        pending_tasks = [
            (task_id, task_data)
            for task_id, task_data in tasks_dict.items()
            if task_id not in completed_task_ids and task_id not in faulty_task_ids
        ]
        worker_count = max(1, config.MAX_CONCURRENT_TASKS)
        logger.info("Running %s task(s) with %s concurrent worker(s).", len(pending_tasks), worker_count)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_task = {
                executor.submit(evaluate_task, task_id, task_data): task_id
                for task_id, task_data in pending_tasks
            }

            for future in as_completed(future_to_task):
                task_id = future_to_task[future]
                current_task_id = task_id
                if future.cancelled():
                    continue
                try:
                    result = future.result()
                except AuthError as auth_err:
                    auth_failed = True
                    logger.error("AUTH ERROR: %s", auth_err)
                    for pending in future_to_task:
                        pending.cancel()
                    continue
                except QuotaExceededError as quota_err:
                    quota_exhausted = True
                    logger.error("SAFE PAUSE / DAILY QUOTA GUARD: %s", quota_err)
                    for pending in future_to_task:
                        pending.cancel()
                    continue
                except Exception as err:
                    faulty_task_ids.add(task_id)
                    logger.exception("TASK ERROR: %s failed: %s", task_id, err)
                    continue

                padrao_res = result["cegis_padrao"]
                at_res = result["cegis_antitrapaca"]
                task_api_error = padrao_res.get("api_error", False) or at_res.get("api_error", False)

                if padrao_res["success"]:
                    cegis_padrao_correct += 1
                if at_res["success"]:
                    cegis_antitrapaca_correct += 1
                if args.include_baseline and result.get("baseline", {}).get("success"):
                    baseline_correct += 1

                padrao_fc = padrao_res.get("false_convergence", False)
                at_fc = at_res.get("false_convergence", False)

                if task_api_error:
                    consecutive_api_failures += 1
                else:
                    consecutive_api_failures = 0

                detailed_results.append(result)
                detailed_results.sort(key=lambda r: task_order.get(r.get("task_id", ""), 999999))
                completed_task_ids.add(task_id)
                _EMERGENCY_STATE.update({
                    "cegis_padrao_correct": cegis_padrao_correct,
                    "cegis_antitrapaca_correct": cegis_antitrapaca_correct,
                    "baseline_correct": baseline_correct,
                })

                logger.info(
                    "[%s/%s] %s: Padrão=%s%s, Antitrapaça=%s%s | Iters: P=%s AT=%s | API: %s/%s",
                    len(detailed_results), total_tasks, task_id,
                    "PASS" if padrao_res["success"] else "FAIL",
                    " FC!" if padrao_fc else "",
                    "PASS" if at_res["success"] else "FAIL",
                    " FC!" if at_fc else "",
                    padrao_res.get("iterations_used", 1),
                    at_res.get("iterations_used", 1),
                    get_request_count(), config.MAX_DAILY_REQUESTS,
                )

                save_checkpoint(
                    output_path=args.output,
                    model=args.model,
                    max_iters=args.max_iters,
                    total_tasks=total_tasks,
                    detailed_results=detailed_results,
                    cegis_padrao_correct=cegis_padrao_correct,
                    cegis_antitrapaca_correct=cegis_antitrapaca_correct,
                    baseline_correct=baseline_correct,
                    faulty_task_ids=faulty_task_ids,
                    include_baseline=args.include_baseline,
                )
                if args.markdown:
                    save_markdown_report(
                        args.markdown, args.model, total_tasks, detailed_results,
                        cegis_padrao_correct, cegis_antitrapaca_correct, faulty_task_ids,
                        baseline_correct=baseline_correct, include_baseline=args.include_baseline,
                    )

                completed_count = len(detailed_results)
                if completed_count % PROGRESS_CHECKPOINT_INTERVAL == 0:
                    progress_path = progress_checkpoint_path(args.output, completed_count, total_tasks)
                    save_checkpoint(
                        output_path=progress_path,
                        model=args.model,
                        max_iters=args.max_iters,
                        total_tasks=total_tasks,
                        detailed_results=detailed_results,
                        cegis_padrao_correct=cegis_padrao_correct,
                        cegis_antitrapaca_correct=cegis_antitrapaca_correct,
                        baseline_correct=baseline_correct,
                        faulty_task_ids=faulty_task_ids,
                        include_baseline=args.include_baseline,
                    )
                    if previous_progress_path and os.path.exists(previous_progress_path):
                        os.remove(previous_progress_path)
                    previous_progress_path = progress_path
                    logger.info("Progress checkpoint saved to '%s'.", progress_path)

                if consecutive_api_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    logger.error("CIRCUIT BREAKER: %s consecutive tasks had API errors.", CIRCUIT_BREAKER_THRESHOLD)
                    for pending in future_to_task:
                        pending.cancel()
                    break

        if auth_failed:
            logger.error("Experiment stopped because API authentication failed.")
        elif quota_exhausted:
            logger.error("Progress safely saved to '%s'; rerun to resume after quota reset.", args.output)

    except KeyboardInterrupt:
        logger.warning("Interrupted. Saving current checkpoint...")
        raise SystemExit(0)
    except Exception as err:
        if current_task_id is not None:
            faulty_task_ids.add(current_task_id)
        logger.exception("EXPERIMENT ERROR: %s", err)
        raise
    finally:
        try:
            save_checkpoint(
                output_path=args.output,
                model=args.model,
                max_iters=args.max_iters,
                total_tasks=total_tasks,
                detailed_results=detailed_results,
                cegis_padrao_correct=cegis_padrao_correct,
                cegis_antitrapaca_correct=cegis_antitrapaca_correct,
                baseline_correct=baseline_correct,
                faulty_task_ids=faulty_task_ids,
                include_baseline=args.include_baseline,
            )
            if args.markdown:
                save_markdown_report(
                    args.markdown, args.model, total_tasks, detailed_results,
                    cegis_padrao_correct, cegis_antitrapaca_correct, faulty_task_ids,
                    baseline_correct=baseline_correct, include_baseline=args.include_baseline,
                )
            logger.info("Checkpoint safely saved to '%s'. You can resume at any time.", args.output)
        except Exception:
            logger.exception("Failed to save checkpoint to '%s'.", args.output)

    # 5. Print Summary
    evaluated_count = len(detailed_results)
    padrao_acc = (cegis_padrao_correct / evaluated_count) * 100 if evaluated_count > 0 else 0.0
    antitrapaca_acc = (cegis_antitrapaca_correct / evaluated_count) * 100 if evaluated_count > 0 else 0.0
    padrao_fc = sum(1 for r in detailed_results if r.get("cegis_padrao", {}).get("false_convergence", False))
    antitrapaca_fc = sum(1 for r in detailed_results if r.get("cegis_antitrapaca", {}).get("false_convergence", False))

    logger.info("=" * 60)
    logger.info("EXPERIMENT SUMMARY%s", " (PAUSED - DAILY QUOTA REACHED)" if quota_exhausted else "")
    logger.info("Total Tasks: %s | Completed: %s | Faulty: %s", total_tasks, evaluated_count, len(faulty_task_ids))
    logger.info("API Calls Used: %s/%s", get_request_count(), config.MAX_DAILY_REQUESTS)
    logger.info("--- PRIMARY COMPARISON ---")
    logger.info(
        "CEGIS Padrão:       %s/%s (%.2f%%) | False Convergências: %s",
        cegis_padrao_correct, evaluated_count, padrao_acc, padrao_fc
    )
    logger.info(
        "CEGIS Antitrapaça:  %s/%s (%.2f%%) | False Convergências: %s",
        cegis_antitrapaca_correct, evaluated_count, antitrapaca_acc, antitrapaca_fc
    )
    logger.info("Ganho de Acurácia: %+.2f%% | Redução de FC: %+d", antitrapaca_acc - padrao_acc, padrao_fc - antitrapaca_fc)
    if args.include_baseline:
        base_acc = (baseline_correct / evaluated_count) * 100 if evaluated_count > 0 else 0.0
        logger.info("Baseline (1-shot) [ref.]: %s/%s (%.2f%%)", baseline_correct, evaluated_count, base_acc)
    logger.info("Results saved to: %s", args.output)
    logger.info("=" * 60)


def main() -> None:
    """Run the experiment and preserve state if any failure escapes handling."""
    try:
        _run_main()
    except BaseException as error:
        save_emergency_checkpoint(error)
        raise


if __name__ == "__main__":
    main()
