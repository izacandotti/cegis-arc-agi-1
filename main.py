#!/usr/bin/env python3
"""
Entry point raiz para o experimento ARC-AGI CEGIS.
Redireciona a chamada para src.main para máxima conveniência e compatibilidade.
"""

import sys
from pathlib import Path

# Adiciona o diretório 'src' ao sys.path
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from main import main

if __name__ == "__main__":
    main()
