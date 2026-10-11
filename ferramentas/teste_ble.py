"""B0: prova do protocolo do ventilador Arno pelo PC, sem o app.

Uso: python ferramentas\\teste_ble.py [--so-scan] [--sem-comando]
Grava tudo em relatorios\\teste_ble_<data>.txt.
"""
import asyncio
import datetime
import os
import sys

from bleak import BleakClient, BleakScanner

SERVICO = "01000000-8000-1000-8000-111111111111"
STATUS = "02000000-8000-1000-8000-111111111111"
CONTROLE = "03000000-8000-1000-8000-111111111111"

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(RAIZ, "relatorios")
os.makedirs(PASTA, exist_ok=True)
ARQ = os.path.join(PASTA, datetime.datetime.now().strftime("teste_ble_%Y%m%d_%H%M%S.txt"))
_log = open(ARQ, "w", encoding="utf-8")


def log(*partes):
    linha = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3] + " " + " ".join(str(p) for p in partes)
    print(linha)
    _log.write(linha + "\n")
    _log.flush()


async def ler(cli, n=1, pausa=1.0):
    for _ in range(n):
        v = await cli.read_gatt_char(STATUS)
        log("STATUS", v.hex(" "), f"({len(v)} bytes)")
        await asyncio.sleep(pausa)


async def main():
    so_scan = "--so-scan" in sys.argv
    sem_comando = "--sem-comando" in sys.argv
    log("scan 15 s...")
    achados = await BleakScanner.discover(timeout=15.0, return_adv=True)
    alvo = None
    for disp, adv in sorted(achados.values(), key=lambda x: -x[1].rssi):
        nome = adv.local_name or disp.name
        log("visto", disp.address, repr(nome), "rssi", adv.rssi,
            "uuids", adv.service_uuids, "fab", {k: v.hex() for k, v in adv.manufacturer_data.items()})
        if nome and "FAN" in nome and alvo is None:
            alvo = disp
    if alvo is None:
        log("RESULTADO: nenhum aparelho com 'FAN' no nome")
        return
    log("ALVO", alvo.address, alvo.name)
    if so_scan:
        return
    async with BleakClient(alvo, timeout=20.0) as cli:
        log("conectado")
        for s in cli.services:
            log("servico", s.uuid)
            for c in s.characteristics:
                log("   carac", c.uuid, c.properties)
        await ler(cli, 5)
        if sem_comando:
            return
        log("ESCREVE vel.1 = 00 03")
        await cli.write_gatt_char(CONTROLE, bytes([0x00, 0x03]), response=True)
        await ler(cli, 5)
        log("ESCREVE desligar = 00 00")
        await cli.write_gatt_char(CONTROLE, bytes([0x00, 0x00]), response=True)
        await ler(cli, 3)
    log("RESULTADO: fim sem erro")


try:
    asyncio.run(main())
except Exception as e:
    log("ERRO", type(e).__name__, e)
finally:
    log("relatorio:", ARQ)
    _log.close()
