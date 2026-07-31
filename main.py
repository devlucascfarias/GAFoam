#!/usr/bin/env python3
"""Ponto de entrada do GAFoam.

Permite executar `python3 main.py` a partir do repositório, sem instalação:
o pacote vive em `src/`, que é acrescentado ao caminho de importação.
"""

import os
import sys

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from gafoam.app import run  # noqa: E402  (depende do sys.path acima)

if __name__ == "__main__":
    sys.exit(run())
