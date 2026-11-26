"""Caminhos do clone, independentes do cwd (instalação editável)."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "dados"
