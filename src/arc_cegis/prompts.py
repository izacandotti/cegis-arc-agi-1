"""
Prompt engineering and semantic counterexample feedback builders for ARC tasks.

TOKEN EFFICIENCY & TPM OPTIMIZATION:
- Compact Grid Serialization: Grids are serialized using `json.dumps(..., separators=(',', ':'))`
  to eliminate whitespace overhead, reducing prompt tokens by ~30-40% on large ARC grids.
- Concise Directives: Strict rules (anti-import, uniform transformation logic) are written compactly
  to minimize static prompt overhead while preserving reasoning clarity.

ANTI-CHEAT VARIANTS:
- Standard CEGIS: No anti-cheat rules anywhere. Model is free to learn any pattern.
- CEGIS+Anti-Cheat: Anti-cheat rules are injected in both the initial prompt and all feedback
  messages, explicitly forbidding hardcoded coordinates and example-index branching.
  Goal: reduce false convergence (superficial hardcoding that passes training but fails testing).
"""

import json
from typing import Dict, List, Optional

ANTI_IMPORT_RULES = (
    "RULES:\n"
    "- Do NOT use `import` statements; use only pure native Python (list, dict, set, range, len, min, max, sum, enumerate, zip, abs).\n"
)

ANTI_CHEAT_RULES = (
    "- Do NOT hardcode coordinates or branch on specific example indices; provide a single uniform geometric/mathematical transformation.\n"
    "- Do NOT memorize or replicate specific output grids from the examples; the function must generalize.\n"
)


def format_grid_repr(grid: Optional[List[List[int]]]) -> str:
    """Serializes a 2D ARC grid using standard JSON formatting with spaces for natural tokenization."""
    if grid is None:
        return "None"
    return json.dumps(grid)


def build_initial_prompt(
    task_train_pairs: List[Dict[str, List[List[int]]]],
    anti_cheat: bool = False,
) -> str:
    """
    Constructs the initial prompt presenting train demonstration pairs and requesting transform().
    Uses natural grid formatting for best model comprehension.

    Args:
        task_train_pairs: List of train input/output pairs.
        anti_cheat: If True, injects ANTI_CHEAT_RULES to prevent hardcoding/memorization.
                    Use for the CEGIS+Anti-Cheat variant. Default False (CEGIS Standard).
    """
    prompt = (
        "You are an expert Python programmer solving an ARC (Abstraction and Reasoning Corpus) puzzle.\n"
        "Analyze the input-output grid demonstration pairs to discover the underlying transformation rule.\n\n"
    )
    for i, pair in enumerate(task_train_pairs):
        prompt += f"--- Example {i} ---\n"
        prompt += f"Input:\n{format_grid_repr(pair['input'])}\n"
        prompt += f"Output:\n{format_grid_repr(pair['output'])}\n\n"

    prompt += (
        "Write a Python function `transform(grid: list[list[int]]) -> list[list[int]]` that implements the solution.\n\n"
        f"{ANTI_IMPORT_RULES}"
    )
    if anti_cheat:
        prompt += f"{ANTI_CHEAT_RULES}"
    prompt += (
        "Requirements:\n"
        "- Input: 2D list of integers (input grid). Return: 2D list of integers (transformed grid).\n"
        "- Be concise: briefly state the transformation rule and return valid Python code in a ```python ... ``` block.\n"
    )
    return prompt


def build_counterexample_feedback(
    example_idx: int,
    input_grid: List[List[int]],
    expected_grid: List[List[int]],
    actual_grid: Optional[List[List[int]]],
    error_msg: str,
    anti_cheat: bool = False,
) -> str:
    """
    Builds semantic counterexample feedback when code fails on a training pair.

    Args:
        example_idx: Index of the failed training example.
        input_grid: The input grid of the failed example.
        expected_grid: The expected output grid.
        actual_grid: The actual (wrong) output produced by the model's code, or None on error.
        error_msg: Error message if execution failed, empty string otherwise.
        anti_cheat: If True, injects ANTI_CHEAT_RULES in the feedback message.
                    Should match the value used in build_initial_prompt for consistency.
    """
    output_repr = format_grid_repr(actual_grid) if not error_msg else f"Execution Error: {error_msg}"
    feedback = (
        f"Your code failed on Training Example {example_idx}.\n"
        f"- Input:\n{format_grid_repr(input_grid)}\n"
        f"- Expected Output:\n{format_grid_repr(expected_grid)}\n"
        f"- Produced Output:\n{output_repr}\n\n"
        f"{ANTI_IMPORT_RULES}"
    )
    if anti_cheat:
        feedback += f"{ANTI_CHEAT_RULES}"
    feedback += "Fix the logic and provide the updated `transform(grid)` function in a ```python ... ``` block."
    return feedback
