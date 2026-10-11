"""
O que faz os atalhos funcionarem com o programa em segundo plano.

SEM BIBLIOTECA NOVA, DE PROPOSITO
----------------------------------
Eu tinha avisado que este bloco precisaria de uma biblioteca de teclado.
Precisaria, se fosse pelo caminho comum: as bibliotecas de atalho global em
Python (keyboard, pynput) funcionam instalando um GANCHO DE TECLADO no
Windows -- elas passam a ver TODA tecla digitada na maquina inteira, em
qualquer programa, e cada tecla digitada passa pelo nosso codigo antes de
chegar no destino.

Para um programa que so acende uma lampada isso e desproporcional em tres
frentes: e o mesmo mecanismo de um capturador de teclas, e por isso costuma
ser barrado por antivirus; poe o nosso programa no caminho de cada tecla do
computador, contra a regra de nao atrapalhar as outras tarefas; e traz uma
dependencia a mais num programa que quer ser pequeno.

O Windows ja resolve isso sozinho, com `RegisterHotKey`: a gente REGISTRA a
combinacao e o sistema avisa quando ela for pressionada. Quem faz a
comparacao e o proprio Windows -- as outras teclas nunca passam por aqui.
Nao ha dependencia (e a `ctypes`, que vem no Python), nao ha gancho, e nao
ha antivirus reclamando.

DE BRINDE, CONFLITO COM OUTRO PROGRAMA APARECE. Se a combinacao ja for de
outro aplicativo, o Windows recusa o registro e a gente sabe na hora -- da
para marcar na tela em vez de deixar o atalho quieto sem funcionar.

CUIDADO COM THREADS, DE NOVO
-----------------------------
O aviso do Windows chega numa fila que pertence a THREAD que registrou o
atalho -- entao registrar, escutar e cancelar acontecem tudo dentro da
thread daqui. E, como na bandeja, nada aqui toca na interface: o aviso vira
um pedido na fila, e a janela consome no proprio laco, na thread certa.
"""

from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger(__name__)

# -- o que o Windows entende ------------------------------------------------

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# Nao repetir enquanto a tecla fica segurada. Sem isto, segurar a combinacao
# de alternar mandaria a lampada ligar e desligar dezenas de vezes por
# segundo -- e cada uma dessas e um comando de rede.
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

# Mensagem so nossa, para acordar a thread. A faixa a partir de WM_USER e
# reservada pelo Windows justamente para isso -- mandar uma mensagem do
# sistema no lugar funcionaria por acidente e confundiria quem lesse depois.
WM_USER = 0x0400
NOSSO_AVISO = WM_USER + 1

BITS = {
    "Ctrl": MOD_CONTROL,
    "Alt": MOD_ALT,
    "Shift": MOD_SHIFT,
    "Win": MOD_WIN,
}

# O codigo de cada tecla para o Windows. So as de nome comprido: letra,
# numero e pontuacao sao resolvidas perguntando ao Windows (ver `_codigo`).
#
# As chaves aqui TEM que bater com `TECLAS_ESPECIAIS` do `atalhos.py` --
# nome que exista la e nao aqui vira atalho aceito na tela e recusado no
# registro, que foi o problema do `Ctrl+Alt+\` (06/set/2026).
CODIGOS = {
    "Esquerda": 0x25,
    "Cima": 0x26,
    "Direita": 0x27,
    "Baixo": 0x28,
    "Espaco": 0x20,
    "Enter": 0x0D,
    "Backspace": 0x08,
    "Del": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PgUp": 0x21,
    "PgDn": 0x22,
}
for _n in range(1, 25):                     # F1..F24
    CODIGOS["F%d" % _n] = 0x6F + _n


def traduzir(teclas: str) -> tuple[int, int] | None:
    """
    "Ctrl+Alt+L" -> (modificadores, codigo da tecla), como o Windows quer.

    Devolve None quando a combinacao nao da para registrar -- sem tecla
    final, sem modificador, ou com uma tecla que nao esta na tabela.
    """
    partes = [p.strip() for p in (teclas or "").split("+") if p.strip()]
    if len(partes) < 2:
        return None

    modificadores = 0
    final = ""
    for parte in partes:
        if parte in BITS:
            modificadores |= BITS[parte]
        else:
            final = parte

    if not modificadores or not final:
        return None

    codigo = _codigo(final)
    if codigo is None:
        return None

    return (modificadores | MOD_NOREPEAT, codigo)


def _codigo(tecla: str) -> int | None:
    """
    O numero que o Windows usa para esta tecla, ou None se nao der.

    PERGUNTA AO WINDOWS EM VEZ DE CHUTAR. Letra e numero cairiam bem numa
    conta simples, mas pontuacao NAO: onde fica a barra invertida, o ponto
    e virgula ou o Ç muda conforme o teclado -- num teclado brasileiro nem
    sao as mesmas teclas de um americano. `VkKeyScanW` responde isso para o
    teclado que a pessoa esta usando agora, que e a unica resposta certa.
    """
    if tecla in CODIGOS:
        return CODIGOS[tecla]
    if len(tecla) != 1:
        return None

    try:
        import ctypes
        from .atalhos import TECLAS_OEM, caractere_da_tecla, layout_atual

        # pontuacao: a tecla cujo caractere (sem modificador) e este, no layout
        # da JANELA -- o mesmo que a captura usou (11/out/2026). Esta thread tem
        # o layout dela, que pode ser outro.
        for vk in TECLAS_OEM:
            if caractere_da_tecla(vk) == tecla.lower():
                return vk
        u = ctypes.windll.user32
        u.VkKeyScanExW.argtypes = [ctypes.c_wchar, ctypes.c_void_p]
        u.VkKeyScanExW.restype = ctypes.c_short
        resposta = u.VkKeyScanExW(tecla, layout_atual())
        if resposta != -1:
            codigo = resposta & 0xFF
            if codigo:
                return codigo
    except Exception as erro:
        log.debug("nao consegui perguntar o codigo de %r: %s", tecla, erro)

    # Ultimo recurso, para letra e numero: no teclado deles o codigo e o
    # proprio caractere em maiuscula.
    if tecla.isalnum() and tecla.isascii():
        return ord(tecla.upper())
    return None


class Motor:
    """
    Mantem os atalhos registrados no Windows e empilha o que foi apertado.

    Uso:
        motor = Motor()
        motor.iniciar()
        motor.aplicar({"alternar": "Ctrl+Alt+L"})
        ...
        for acao in motor.pedidos():
            ...
    """

    def __init__(self) -> None:
        self.fila: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self._pronto = threading.Event()

        # O que a janela quer registrado. A thread le isto quando acorda.
        self._desejado: dict[str, str] = {}
        self._trava = threading.Lock()
        self._pedido_de_troca = threading.Event()

        # acao -> numero que o Windows usa para identificar o atalho
        self._registrados: dict[str, int] = {}
        self._falhas: set[str] = set()
        self._id_da_vez = 1

        self.disponivel = self._checar()

    @staticmethod
    def _checar() -> bool:
        try:
            import ctypes
            import sys

            return sys.platform == "win32" and hasattr(ctypes, "windll")
        except Exception:
            return False

    # -- o que a janela chama -------------------------------------------------

    def iniciar(self) -> bool:
        if not self.disponivel or self._thread is not None:
            return False

        self._parar.clear()
        self._thread = threading.Thread(
            target=self._rodar, name="atalhos", daemon=True
        )
        self._thread.start()
        return True

    def aplicar(self, atalhos: dict[str, str]) -> None:
        """
        Diz quais atalhos devem estar valendo agora.

        Chamado toda vez que a lista muda. Nao registra nada aqui: so anota
        e acorda a thread, que e quem pode falar com o Windows sobre isso.
        """
        with self._trava:
            self._desejado = {a: t for a, t in (atalhos or {}).items() if t}
        self._pedido_de_troca.set()
        self._cutucar()

    def pedidos(self) -> list[str]:
        """As acoes cujos atalhos foram apertados desde a ultima chamada."""
        saida = []
        while True:
            try:
                saida.append(self.fila.get_nowait())
            except queue.Empty:
                break
        return saida

    def falhas(self) -> set[str]:
        """
        As acoes cujo atalho o Windows RECUSOU -- quase sempre porque outro
        programa ja usa a combinacao.
        """
        with self._trava:
            return set(self._falhas)

    def encerrar(self) -> None:
        self._parar.set()
        self._cutucar()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- a thread -------------------------------------------------------------

    def _cutucar(self) -> None:
        """
        Acorda a thread, que fica parada esperando aviso do Windows.

        `GetMessage` dorme ate chegar alguma coisa; sem uma mensagem
        qualquer, um atalho novo so passaria a valer no proximo aperto de
        outro atalho -- ou seja, nunca.
        """
        if self._thread is None or not self._pronto.is_set():
            return
        try:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(
                self._id_da_thread, NOSSO_AVISO, 0, 0
            )
        except Exception as erro:
            log.debug("nao consegui acordar a thread dos atalhos: %s", erro)

    def _rodar(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL

        self._id_da_thread = ctypes.windll.kernel32.GetCurrentThreadId()

        # A fila de mensagens da thread so existe depois que alguem pergunta
        # por ela. Sem isto, o primeiro `PostThreadMessage` se perde.
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._pronto.set()

        self._sincronizar(user32)

        try:
            while not self._parar.is_set():
                pegou = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if pegou in (0, -1):
                    break

                if msg.message == WM_HOTKEY:
                    self._disparou(int(msg.wParam))

                if self._pedido_de_troca.is_set():
                    self._pedido_de_troca.clear()
                    self._sincronizar(user32)
        except Exception as erro:
            log.warning("o laco dos atalhos parou: %s", erro)
        finally:
            self._soltar_tudo(user32)

    def _disparou(self, identificador: int) -> None:
        with self._trava:
            for acao, meu_id in self._registrados.items():
                if meu_id == identificador:
                    self.fila.put(acao)
                    return

    def _sincronizar(self, user32) -> None:
        """
        Faz o que esta registrado no Windows virar o que a janela pediu.

        Solta tudo e registra de novo, em vez de calcular a diferenca: sao
        no maximo sete atalhos, a conta da diferenca custaria mais codigo do
        que economiza, e refazer do zero nao deixa sobra de registro antigo
        -- que e o tipo de sobra que ninguem descobre ate um atalho parar de
        funcionar sem motivo.
        """
        self._soltar_tudo(user32)

        with self._trava:
            desejado = dict(self._desejado)

        registrados: dict[str, int] = {}
        falhas: set[str] = set()

        for acao, teclas in desejado.items():
            traduzido = traduzir(teclas)
            if traduzido is None:
                falhas.add(acao)
                log.info("atalho de %s nao da para registrar: %s", acao, teclas)
                continue

            modificadores, codigo = traduzido
            self._id_da_vez += 1
            identificador = self._id_da_vez

            if user32.RegisterHotKey(None, identificador, modificadores, codigo):
                registrados[acao] = identificador
            else:
                falhas.add(acao)
                log.info("o Windows recusou o atalho de %s (%s); provavelmente"
                         " ja e de outro programa", acao, teclas)

        with self._trava:
            self._registrados = registrados
            self._falhas = falhas

    def _soltar_tudo(self, user32) -> None:
        with self._trava:
            antigos = list(self._registrados.values())
            self._registrados = {}

        for identificador in antigos:
            try:
                user32.UnregisterHotKey(None, identificador)
            except Exception:
                pass
