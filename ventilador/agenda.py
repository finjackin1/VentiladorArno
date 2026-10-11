"""Agenda por horario, cumprida pelo PC (o ventilador nao tem relogio no
protocolo). Cada item: {"id","hora":"HH:MM","dias":[0..6] (0 = segunda),
"acao": "v0".."v3" | "rotina:<id>", "ligado": bool}.

`vencidos(agora)` devolve os itens cuja hora chegou neste minuto e ainda
nao rodaram hoje. Se o PC estava desligado na hora, o item NAO roda depois.
"""
from __future__ import annotations

import datetime

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


class Agenda:
    def __init__(self):
        self._feitos: set[tuple[str, str]] = set()

    def vencidos(self, itens: list[dict], agora: datetime.datetime | None = None) -> list[dict]:
        agora = agora or datetime.datetime.now()
        hoje = agora.date().isoformat()
        hm = agora.strftime("%H:%M")
        saida = []
        for it in itens:
            if not it.get("ligado", True) or it.get("hora") != hm:
                continue
            if agora.weekday() not in it.get("dias", list(range(7))):
                continue
            chave = (it.get("id", ""), hoje + hm)
            if chave in self._feitos:
                continue
            self._feitos.add(chave)
            saida.append(it)
        return saida


def dias_texto(dias: list[int]) -> str:
    d = sorted(set(dias))
    if len(d) == 7:
        return "todo dia"
    if d == [0, 1, 2, 3, 4]:
        return "seg a sex"
    if d == [5, 6]:
        return "fim de semana"
    if not d:
        return "nenhum dia"
    return ", ".join(DIAS[i] for i in d)
