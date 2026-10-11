"""Conversa BLE com o ventilador (bleak), numa thread propria com asyncio.

A janela nunca espera por aqui: manda pedidos (`enviar`, `soltar`, `retomar`,
`procurar_agora`) e le os eventos numa fila (`eventos()`), no laco dela.
Eventos: ("estado", nome), ("status", dict), ("aparelho", endereco, nome),
("dica", codigo | None).
Estados: procurando, conectando, conectado, solto, sem_bluetooth.
Dicas (o que provavelmente esta errado, para a tela explicar):
  bt_desligado, bt_ausente, bt_negado  -- o Bluetooth do PC
  nao_achado   -- procurando ha tempo sem ver o ventilador anunciar
  recusou      -- viu o ventilador mas nao conectou (celular conectado nele?)
  caiu         -- estava conectado e caiu; reconectando sozinho
  aparelho_errado -- conectou num "FAN" sem o servico do ventilador

ESTABILIDADE (10/out/2026, pedido dele):
- toda operacao BLE tem tempo limite (nada pendura a thread);
- pedidos acumulados viram UM: cada comando substitui o estado inteiro do
  ventilador, entao so o ultimo importa (clique rapido nao enfileira);
- queda detectada na hora (callback) e por leituras falhas seguidas;
- a thread se reergue se algo inesperado derrubar o laco.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time

from . import protocolo as P

log = logging.getLogger(__name__)

LEITURA_S = 1.0           # o app le o status a cada 1 s
ESPERA_REPETIR_S = 3.0
SCAN_S = 10.0
LIMITE_OP_S = 5.0         # tempo maximo de uma leitura/escrita
NAO_ACHADO_APOS_S = 20.0
FALHAS_PARA_CAIR = 3


class Conexao:
    def __init__(self, endereco_salvo: str = ""):
        self.endereco = (endereco_salvo or "").upper()
        self.estado = "procurando"
        self._fila_ui: queue.Queue = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pedido: bytes | None = None          # so o ultimo comando importa
        self._trava = threading.Lock()
        self._solto = False
        self._fim = False
        self._acordar: asyncio.Event | None = None
        self._ultimo_cru = None
        self._dica = None
        self._thread = threading.Thread(target=self._rodar, name="ble", daemon=True)

    # -- o que a janela chama ------------------------------------------------
    def iniciar(self):
        self._thread.start()

    def eventos(self) -> list:
        saida = []
        while True:
            try:
                saida.append(self._fila_ui.get_nowait())
            except queue.Empty:
                return saida

    def conectado(self) -> bool:
        return self.estado == "conectado"

    def enviar(self, dado: bytes) -> bool:
        """Guarda o pacote (substitui o anterior ainda nao enviado). False se
        nao estiver conectado (a tela volta)."""
        if not self.conectado() or self._loop is None:
            return False
        with self._trava:
            self._pedido = dado
        self._cutucar()
        return True

    def soltar(self):
        """Larga o ventilador (para o celular poder usar) ate `retomar`."""
        self._solto = True
        self._cutucar()

    def retomar(self):
        self._solto = False
        self._cutucar()

    def procurar_agora(self):
        """Pula a espera entre tentativas (botao "procurar agora")."""
        self._cutucar()

    def encerrar(self):
        """Ao SAIR (pedido dele, 10/out/2026): manda o disconnect e ESPERA ele
        terminar, para o ventilador ficar livre na hora (celular pode usar).
        A busca em curso e cancelada; o limite so evita prender a saida."""
        self._fim = True
        self._cutucar()
        self._thread.join(timeout=6.0)
        if self._thread.is_alive():
            log.warning("saida: a conexao nao terminou a tempo")
        else:
            log.info("saida: ventilador liberado")

    # -- a thread --------------------------------------------------------------
    def _cutucar(self):
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._acordar.set)
            except RuntimeError:
                pass

    def _avisar(self, *ev):
        self._fila_ui.put(ev)

    def _mudar(self, estado: str):
        if estado != self.estado:
            log.info("estado: %s", estado)
            self.estado = estado
            self._avisar("estado", estado)

    def _dar_dica(self, codigo):
        if codigo != self._dica:
            if codigo:
                log.info("dica: %s", codigo)
            self._dica = codigo
            self._avisar("dica", codigo)

    def _rodar(self):
        while not self._fim:
            try:
                asyncio.run(self._principal())
            except Exception:
                log.exception("a thread BLE caiu; reerguendo em 3 s")
                self._mudar("procurando")
                time.sleep(3)

    async def _dormir(self, s: float):
        try:
            await asyncio.wait_for(self._acordar.wait(), s)
        except asyncio.TimeoutError:
            pass
        self._acordar.clear()

    async def _ou_acordar(self, coro):
        """Roda `coro`, mas desiste se for acordado para sair/soltar (busca de
        10 s nao segura a saida). Devolve o resultado ou None."""
        tarefa = asyncio.ensure_future(coro)
        espera = asyncio.ensure_future(self._acordar.wait())
        await asyncio.wait({tarefa, espera}, return_when=asyncio.FIRST_COMPLETED)
        espera.cancel()
        if tarefa.done():
            return tarefa.result()
        if self._fim or self._solto:
            tarefa.cancel()
            try:
                await tarefa
            except (asyncio.CancelledError, Exception):
                pass
            return None
        self._acordar.clear()           # acordado por outro motivo (procurar agora): segue esperando
        return await tarefa

    async def _principal(self):
        from bleak import BleakScanner
        from bleak.backends.device import BLEDevice
        from bleak.exc import BleakBluetoothNotAvailableError

        self._loop = asyncio.get_running_loop()
        self._acordar = asyncio.Event()
        sem_ver_desde = time.monotonic()
        recusas = 0
        direto_em = 0.0
        while not self._fim:
            if self._solto:
                self._mudar("solto")
                self._dar_dica(None)
                await self._dormir(3600)
                sem_ver_desde = time.monotonic()
                direto_em = 0.0
                continue
            # RECONECTAR AO ABRIR (pedido dele, 10/out/2026): com o endereco salvo,
            # conecta DIRETO, sem esperar o anuncio -- funciona mesmo se o Windows
            # ainda segura a conexao antiga (ai o ventilador nao anuncia). Tenta
            # no maximo a cada 30 s; se falhar, cai na busca normal.
            if self.endereco and time.monotonic() - direto_em > 30:
                direto_em = time.monotonic()
                self._mudar("conectando")
                try:
                    r = await self._sessao(BLEDevice(self.endereco, "", None), limite=8.0)
                    if r == "conectou":
                        direto_em = 0.0
                        if not self._fim and not self._solto:
                            self._dar_dica("caiu")
                            self._mudar("procurando")
                            await self._dormir(1.0)
                        continue
                except Exception as e:
                    log.info("reconexao direta nao deu (%s: %s); buscando", type(e).__name__, e)
                if self._fim or self._solto:
                    continue
            self._mudar("procurando")
            alvo = self.endereco

            def serve(d, a):
                nome = (a.local_name or d.name) or ""
                return (alvo and d.address.upper() == alvo) or P.NOME_CONTEM in nome

            try:
                disp = await self._ou_acordar(BleakScanner.find_device_by_filter(serve, timeout=SCAN_S))
            except BleakBluetoothNotAvailableError as e:
                motivo = getattr(e, "reason", None)
                nome = getattr(motivo, "name", "")
                self._mudar("sem_bluetooth")
                self._dar_dica("bt_desligado" if nome == "POWERED_OFF" else
                               "bt_negado" if nome.startswith("DENIED") else "bt_ausente")
                await self._dormir(ESPERA_REPETIR_S)
                continue
            except Exception as e:
                log.warning("scan falhou: %s: %s", type(e).__name__, e)
                self._mudar("sem_bluetooth")
                self._dar_dica("bt_ausente")
                await self._dormir(ESPERA_REPETIR_S * 2)
                continue
            if self._fim or self._solto:
                continue
            if disp is None:
                if time.monotonic() - sem_ver_desde > NAO_ACHADO_APOS_S:
                    self._dar_dica("nao_achado")
                await self._dormir(ESPERA_REPETIR_S)
                continue
            sem_ver_desde = time.monotonic()
            if self._dica in ("nao_achado", "bt_desligado", "bt_ausente", "bt_negado"):
                self._dar_dica(None)
            self._mudar("conectando")
            resultado = "falhou"
            try:
                resultado = await self._sessao(disp)
            except Exception as e:
                log.warning("conexao: %s: %s", type(e).__name__, e)
            if resultado == "conectou":          # estava conectado e caiu
                recusas = 0
                if not self._fim and not self._solto:
                    self._dar_dica("caiu")
            elif resultado == "errado":
                self._dar_dica("aparelho_errado")
            else:
                recusas += 1
                if recusas >= 2:
                    self._dar_dica("recusou")
            if not self._fim and not self._solto:
                self._mudar("procurando")
                await self._dormir(ESPERA_REPETIR_S if resultado != "conectou" else 1.0)

    async def _sessao(self, disp, limite: float = 20.0) -> str:
        from bleak import BleakClient

        caiu = asyncio.Event()

        def desconectou(_cli):
            self._loop.call_soon_threadsafe(caiu.set)
            self._cutucar()

        cli = BleakClient(disp, timeout=limite, disconnected_callback=desconectou)
        conectado = await self._ou_acordar(cli.connect())
        if self._fim or self._solto or not conectado and not cli.is_connected:
            await self._desligar(cli)
            return "falhou"
        try:
            return await self._usar(cli, disp, caiu)
        finally:
            await self._desligar(cli)

    async def _desligar(self, cli):
        """Disconnect EXPLICITO (sair, soltar, queda): o ventilador fica livre."""
        try:
            if cli.is_connected:
                await asyncio.wait_for(cli.disconnect(), 4.0)
                log.info("desconectado do ventilador")
        except Exception as e:
            log.info("disconnect: %s: %s", type(e).__name__, e)

    async def _usar(self, cli, disp, caiu) -> str:
        carac = cli.services.get_characteristic(P.CONTROLE)
        if carac is None or cli.services.get_characteristic(P.STATUS) is None:
            log.warning("aparelho %s sem as caracteristicas esperadas", disp.address)
            return "errado"
        com_resposta = "write" in carac.properties
        self.endereco = disp.address.upper()
        self._avisar("aparelho", self.endereco, disp.name or "")
        with self._trava:
            self._pedido = None                # pedido velho de antes da conexao
        self._ultimo_cru = None
        self._mudar("conectado")
        self._dar_dica(None)
        falhas = 0
        proxima_leitura = 0.0
        while not caiu.is_set() and cli.is_connected and not self._fim and not self._solto:
            with self._trava:
                dado, self._pedido = self._pedido, None
            try:
                if dado:
                    log.info("escreve %s", dado.hex(" "))
                    await asyncio.wait_for(
                        cli.write_gatt_char(P.CONTROLE, dado, response=com_resposta), LIMITE_OP_S)
                    await asyncio.sleep(0.12)   # o ventilador aplica antes de responder o status
                    proxima_leitura = 0.0
                if time.monotonic() >= proxima_leitura:
                    await self._ler(cli)
                    proxima_leitura = time.monotonic() + LEITURA_S
                falhas = 0
            except Exception as e:
                falhas += 1
                log.warning("operacao falhou (%s/%s): %s: %s", falhas, FALHAS_PARA_CAIR,
                            type(e).__name__, e)
                if falhas >= FALHAS_PARA_CAIR:
                    break
                proxima_leitura = time.monotonic() + 0.5
            with self._trava:
                tem_pedido = self._pedido is not None
            if not tem_pedido:
                await self._dormir(max(0.02, proxima_leitura - time.monotonic()))
        # SAINDO com pedido na mao ("ao sair" da janela): escreve antes do disconnect
        with self._trava:
            dado, self._pedido = self._pedido, None
        if dado and self._fim and cli.is_connected and not caiu.is_set():
            try:
                log.info("escreve ao sair %s", dado.hex(" "))
                await asyncio.wait_for(cli.write_gatt_char(P.CONTROLE, dado, response=com_resposta), LIMITE_OP_S)
            except Exception as e:
                log.warning("pedido de saida nao foi: %s: %s", type(e).__name__, e)
        return "conectou"

    async def _ler(self, cli):
        cru = bytes(await asyncio.wait_for(cli.read_gatt_char(P.STATUS), LIMITE_OP_S))
        if cru != self._ultimo_cru:
            log.info("status %s", cru.hex(" "))   # diagnostico: bytes ainda nao mapeados
            self._ultimo_cru = cru
        # manda toda leitura (nao so mudanca): a tela ignora o status logo
        # depois de um comando e precisa da leitura seguinte para se acertar
        st = P.ler_status(cru)
        if st is not None:
            self._avisar("status", st)
