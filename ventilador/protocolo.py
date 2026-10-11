"""Monta e le os pacotes do ventilador. Sem Bluetooth aqui: so bytes.

Origem: leitura estatica do app 1.0.33 (docs/contexto/protocolo.md).
Velocidade na tela: 0 = desligado, 1 (minima) .. 3 (maxima).
No fio o codigo e INVERTIDO: 1 -> 0x03, 2 -> 0x02, 3 -> 0x01, 0 -> 0x00.
"""
from __future__ import annotations

SERVICO = "01000000-8000-1000-8000-111111111111"
STATUS = "02000000-8000-1000-8000-111111111111"
CONTROLE = "03000000-8000-1000-8000-111111111111"
NOME_CONTEM = "FAN"

_PARA_FIO = {0: 0x00, 1: 0x03, 2: 0x02, 3: 0x01}
_DO_FIO = {v: k for k, v in _PARA_FIO.items()}

MINUTOS_MAX = 0xFFFF
PASSOS_MAX = 255


def codigo(velocidade: int) -> int:
    return _PARA_FIO.get(int(velocidade), 0x00)


def pacote_velocidade(vel: int) -> bytes:
    """`00 VV`: muda a velocidade na hora (0 desliga)."""
    return bytes([0x00, codigo(vel)])


def pacote_programa(passos: list[tuple[int, int]]) -> bytes:
    """`02 N` + N x `[min_lo, min_hi, VV, 00]`. passos = [(velocidade, minutos)].

    O timer do app e um programa de 1 passo (velocidade atual, minutos).
    """
    passos = list(passos)[:PASSOS_MAX]
    saida = bytearray([0x02, len(passos)])
    for vel, minutos in passos:
        m = max(0, min(MINUTOS_MAX, int(minutos)))
        saida += bytes([m & 0xFF, (m >> 8) & 0xFF, codigo(vel), 0x00])
    return bytes(saida)


def ler_status(dado: bytes) -> dict | None:
    """Status lido de 02000000. None se curto demais (o app ignora).

    byte[1] == 0 -> velocidade em byte[2]; senao em byte[7] (HIPOTESE: senao =
    programa rodando).
    """
    if not dado or len(dado) <= 2:
        return None
    em_programa = dado[1] != 0
    i = 7 if em_programa else 2
    if i >= len(dado):
        return None
    return {"velocidade": _DO_FIO.get(dado[i], 0), "programa": em_programa,
            "cru": dado.hex(" ")}
