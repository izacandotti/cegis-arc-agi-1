"""
Safe execution environment and Python code extraction for ARC grid transformations.
"""

import multiprocessing as mp
import re
from typing import Any, Dict, List, Optional, Tuple

from . import config


def extract_python_code(response_text: str) -> str:
    """
    Extracts executable Python code from markdown response text.
    Matches ```python ... ``` or ``` ... ``` code fences, or defaults to raw text.
    """
    code_block_match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", response_text, re.IGNORECASE)
    if code_block_match:
        return code_block_match.group(1).strip()
    
    if "def transform" in response_text:
        start_idx = response_text.find("def transform")
        return response_text[start_idx:].strip()

    return response_text.strip()


def _worker_process_target(code_str: str, input_grid: List[List[int]], queue: mp.Queue) -> None:
    """
    Subprocess worker that executes transform(grid) in a restricted namespace.
    """
    try:
        safe_globals: Dict[str, Any] = {
            "__builtins__": {
                "range": range,
                "len": len,
                "min": min,
                "max": max,
                "sum": sum,
                "abs": abs,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "int": int,
                "float": float,
                "bool": bool,
                "all": all,
                "any": any,
                "sorted": sorted,
                "reversed": reversed,
                "isinstance": isinstance,
                "print": print,
            }
        }
        local_scope: Dict[str, Any] = {}
        
        exec(code_str, safe_globals, local_scope)
        
        if "transform" not in local_scope or not callable(local_scope["transform"]):
            queue.put((False, None, "Function 'transform(grid)' not found or not callable."))
            return
        
        # Deep copy to ensure input grid is not mutated
        input_copy = [row[:] for row in input_grid]
        result = local_scope["transform"](input_copy)
        
        if not isinstance(result, list):
            queue.put((False, None, f"Expected return type list[list[int]], got {type(result).__name__}"))
            return
        
        queue.put((True, result, ""))
    except Exception as e:
        queue.put((False, None, f"{type(e).__name__}: {str(e)}"))


def run_transform(
    code_str: str,
    input_grid: List[List[int]],
    timeout_seconds: float = config.TIMEOUT_SECONDS
) -> Tuple[bool, Optional[List[List[int]]], str]:
    """
    Executes transform() against input_grid inside a dedicated subprocess with strict timeout.
    Returns:
        (success: bool, output_grid: Optional[List[List[int]]], error_msg: str)
    """
    if not code_str:
        return False, None, "Empty code string provided."

    queue: mp.Queue = mp.Queue()
    proc = mp.Process(target=_worker_process_target, args=(code_str, input_grid, queue))
    proc.start()

    proc.join(timeout=timeout_seconds)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=0.5)
        if proc.is_alive():
            proc.kill()
        return False, None, f"Execution timed out (> {timeout_seconds}s)."

    if not queue.empty():
        return queue.get()

    return False, None, "Process terminated unexpectedly without returning output."
