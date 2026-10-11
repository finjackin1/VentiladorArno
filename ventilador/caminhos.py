"""Onde ficam config e relatorios: na pasta do programa (portable)."""
from __future__ import annotations

import sys
from pathlib import Path


def pasta_do_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def arquivo(nome: str) -> Path:
    return pasta_do_programa() / nome


def relatorios() -> Path:
    p = pasta_do_programa() / "relatorios"
    p.mkdir(exist_ok=True)
    return p
