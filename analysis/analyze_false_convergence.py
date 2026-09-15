#!/usr/bin/env python3
"""
Wrapper de compatibilidade para a ferramenta de análise pós-experimento.
Redireciona para src.analysis.analyze_false_convergence.
"""

import sys
from pathlib import Path

# Adiciona src ao sys.path
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from analysis.analyze_false_convergence import main

if __name__ == "__main__":
    main()
