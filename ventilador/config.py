"""Config em dicionario, mesclado sobre o padrao campo a campo (molde LightWireless).

Mora em config.json na pasta do programa (portable). Opcao nova entra so no PADRAO.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import uuid

from .caminhos import arquivo

log = logging.getLogger(__name__)
ARQUIVO = arquivo("config.json")

# Proposta minha (no app as 4 vem sem passos); ele ajusta no editor.
ROTINAS_PADRAO = [
    {"id": "default1", "nome": "Manhã quente", "passos": [[3, 60], [2, 120]]},
    {"id": "default2", "nome": "Tarde intensa", "passos": [[3, 180], [2, 60]]},
    {"id": "default3", "nome": "Noite tranquila", "passos": [[2, 120], [1, 120]]},
    {"id": "default4", "nome": "Sono profundo", "passos": [[2, 30], [1, 360]]},
]

PADRAO = {
    "endereco": "",
    "ultima_velocidade": 1,
    "timer_minutos": 60,
    "rotinas": ROTINAS_PADRAO,
    # agenda: {"id", "hora": "22:00", "dias": [0..6] (0 = segunda), "acao", "ligado"}
    "agenda": [],
    "atalhos": {},
    "opcoes": {
        "iniciar_com_windows": False,
        "comecar_na_bandeja": False,
        "ao_abrir": "nada",          # nada | v0 | v1 | v2 | v3 | rotina:<id>
        "ao_sair": "nada",           # idem, ao fechar o programa (segurar o X)
    },
    "janela": {"x": None, "y": None},
}


def _mesclar(padrao, lido):
    if isinstance(padrao, dict) and isinstance(lido, dict):
        saida = dict(padrao)
        for k, v in lido.items():
            saida[k] = _mesclar(padrao[k], v) if k in padrao else v
        return saida
    if lido is None or (padrao is not None and type(lido) is not type(padrao)
                        and not (isinstance(padrao, (int, float)) and isinstance(lido, (int, float)))):
        return copy.deepcopy(padrao)
    return lido


class Config(dict):
    @classmethod
    def carregar(cls) -> "Config":
        lido = {}
        try:
            with open(ARQUIVO, encoding="utf-8") as f:
                lido = json.load(f)
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("config.json ilegivel (%s): usando o padrao", e)
        return cls(_mesclar(copy.deepcopy(PADRAO), lido))

    def gravar(self) -> bool:
        try:
            tmp = str(ARQUIVO) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self, f, ensure_ascii=False, indent=2)
            os.replace(tmp, ARQUIVO)
            return True
        except Exception as e:
            log.warning("nao gravei o config: %s", e)
            return False

    @property
    def opcoes(self) -> dict:
        return self["opcoes"]

    @property
    def atalhos(self) -> dict:
        return self["atalhos"]

    def rotina(self, rid: str) -> dict | None:
        return next((r for r in self["rotinas"] if r.get("id") == rid), None)


def novo_id() -> str:
    return uuid.uuid4().hex[:8]
