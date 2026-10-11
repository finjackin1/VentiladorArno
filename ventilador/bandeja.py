"""
Icone na bandeja do sistema.

DOIS GESTOS, NENHUM MENU (06/set/2026)
---------------------------------------
Um clique alterna a luz; dois cliques abrem a janela; o botao direito nao
faz nada. Foi ele quem pediu assim -- antes havia um menu de contexto com
Abrir / Ligar-desligar / opcoes / Sair, e ele mandou tirar.

Com o menu fora, a pystray perde o unico jeito dela de reagir a clique: a
acao "padrao" e um ITEM do menu, e sem menu nao ha acao padrao. Por isso
este modulo passa a tratar o clique por conta propria (ver
`_icone_de_cliques`), e o icone e criado sem menu nenhum.

CUIDADO COM THREADS
-------------------
A pystray roda o icone na propria thread, e o Tkinter so aceita ser mexido
pela thread que criou a janela. Chamar a janela direto de dentro do clique
trava ou quebra de um jeito dificil de reproduzir.

Por isso nada aqui toca na interface: o clique apenas EMPILHA um pedido, e
a janela consome essa fila no proprio laco, na thread certa. E a mesma
ideia de uma caixa de entrada -- quem escreve e quem le nunca se encontram.
Vale tambem para o relogio do clique duplo, que dispara numa terceira
thread e igualmente so empilha.

Se a pystray nao estiver instalada, o app continua funcionando sem bandeja.
E um recurso a mais, nao um requisito.
"""

from __future__ import annotations

import logging
import queue
import threading

from . import __version__, icones

log = logging.getLogger(__name__)

# (VentiladorArno, portado do LightWireless 10/out/2026: mesmos gestos --
# clique alterna ligado/desligado, duplo clique abre a janela, sem menu.)
TITULO = f"Ventilador Arno {__version__}"

# Quanto esperar por um segundo clique quando o Windows nao souber dizer.
ESPERA_DUPLO_PADRAO_S = 0.5


def _icone_de_cliques(pystray, ao_clique_esquerdo, **kwargs):
    """
    Cria um `pystray.Icon` que entrega o clique esquerdo para nos e ignora
    o direito.

    POR QUE PRECISA REESCREVER CODIGO DA PYSTRAY
    ----------------------------------------------
    A API publica dela so oferece duas reacoes a clique, e as duas saem do
    menu: a acao do item marcado `default=True` (clique esquerdo) e o
    proprio menu (clique direito). Sem menu -- que e o que ele pediu -- nao
    sobra nenhuma.

    A saida e reescrever o metodo PRIVADO `_on_notify` do backend do
    Windows (`pystray._win32.Icon`), que e onde os cliques chegam. Ficamos
    so com o de soltar o botao esquerdo; o direito nao ganha tratamento
    nenhum, entao nada acontece.

    FRAGIL POR SER CODIGO INTERNO DA LIB: uma atualizacao da pystray pode
    mudar esse metodo e desfazer isto sem avisar. Se um dia o clique
    direito voltar a abrir menu, ou o esquerdo parar de responder, o
    primeiro lugar a olhar e aqui.
    """
    from pystray._util import win32 as pystray_win32

    class _IconDeCliques(pystray.Icon):
        def _on_notify(self, wparam, lparam):
            if lparam == pystray_win32.WM_LBUTTONUP:
                ao_clique_esquerdo()
            # WM_RBUTTONUP proposital sem tratamento: sem menu de contexto.

    return _IconDeCliques(**kwargs)


def _espera_de_duplo_clique() -> float:
    """
    A janela de duplo clique CONFIGURADA NO WINDOWS, em segundos.

    Perguntar ao sistema em vez de cravar meio segundo: quem mexeu nessa
    preferencia (mouse lento, acessibilidade) espera que ela valha aqui
    tambem. Valor fora do razoavel ou pergunta que falhou caem no padrao.
    """
    try:
        import ctypes

        ms = int(ctypes.windll.user32.GetDoubleClickTime())
        if 100 <= ms <= 2000:
            return ms / 1000.0
    except Exception:
        pass
    return ESPERA_DUPLO_PADRAO_S


class Bandeja:
    """
    Icone na bandeja, com dois gestos e sem menu.

    Uso:
        bandeja = Bandeja()
        if bandeja.disponivel:
            bandeja.iniciar()
        ...
        # no laco da janela:
        for pedido in bandeja.pedidos():
            ...
    """

    def __init__(self, titulo: str = TITULO):
        self.titulo = titulo
        self.fila: queue.Queue[str] = queue.Queue()
        self._icone = None
        self._thread: threading.Thread | None = None
        self._cor_atual: str | None = None

        # O relogio do clique: existe so entre o primeiro clique e o fim da
        # janela de duplo. A trava protege ele das duas threads que mexem
        # nele -- a da pystray (clique) e a do proprio relogio.
        self._relogio: threading.Timer | None = None
        self._trava = threading.Lock()

        self.disponivel = self._checar()

    @staticmethod
    def _checar() -> bool:
        try:
            import PIL  # noqa: F401
            import pystray  # noqa: F401

            return True
        except ImportError:
            return False

    # -- desenho do icone ----------------------------------------------------

    def _desenhar_icone(self, cor_luz: str | None):
        """
        A lampada, pintada com a cor que a luz esta dando agora.

        `cor_luz` None quer dizer apagada ou sem conexao, e sai cinza. Acesa,
        sai no tom real da temperatura -- quente amarelado, frio azulado.

        E a mesma ideia do circulo grande da janela: o desenho MOSTRA o estado
        do aparelho em vez de descreve-lo. So que aqui vale mais, porque a
        bandeja e o unico lugar visivel quando a janela esta escondida --
        que e como o programa passa a maior parte do tempo.
        """
        return icones.marca(64, cor_luz)

    # -- os cliques -----------------------------------------------------------

    def _clicou(self) -> None:
        """
        Chegou um clique esquerdo (na thread da pystray).

        O WINDOWS NAO DIZ SE FOI UM CLIQUE OU O PRIMEIRO DE UM DUPLO. Os
        dois chegam identicos; o que separa os dois e o TEMPO ate o
        proximo. Por isso o primeiro clique nao age na hora: ele arma um
        relogio do tamanho da janela de duplo clique do sistema. Se um
        segundo clique chegar antes, era duplo -- abre a janela. Se o
        relogio vencer, era simples -- alterna a luz.

        O PRECO E ASSUMIDO: alternar a luz pela bandeja custa essa espera
        (meio segundo, no padrao do Windows). Agir na hora e desmarcar
        depois seria pior -- a luz piscaria a cada duplo clique.
        """
        with self._trava:
            if self._relogio is not None:
                self._relogio.cancel()
                self._relogio = None
                self.fila.put("mostrar")
                return

            self._relogio = threading.Timer(
                _espera_de_duplo_clique(), self._venceu_o_relogio
            )
            self._relogio.daemon = True
            self._relogio.start()

    def _venceu_o_relogio(self) -> None:
        """Passou a janela de duplo sem segundo clique: era clique simples."""
        with self._trava:
            self._relogio = None
        self.fila.put("alternar")

    def _parar_o_relogio(self) -> None:
        with self._trava:
            if self._relogio is not None:
                self._relogio.cancel()
                self._relogio = None

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self) -> bool:
        """Sobe o icone numa thread propria. False se nao der."""
        if not self.disponivel:
            return False

        try:
            import pystray

            self._icone = _icone_de_cliques(
                pystray,
                self._clicou,
                name="ventiladorarno",
                icon=self._desenhar_icone(self._cor_atual),
                title=self.titulo,
                menu=None,
            )

            self._thread = threading.Thread(
                target=self._icone.run, daemon=True, name="bandeja"
            )
            self._thread.start()
            return True

        except Exception as erro:
            log.warning("bandeja indisponivel: %s", erro)
            self.disponivel = False
            return False

    def pedidos(self) -> list[str]:
        """Retira tudo que foi empilhado desde a ultima chamada."""
        saida = []
        while True:
            try:
                saida.append(self.fila.get_nowait())
            except queue.Empty:
                break
        return saida

    def definir_titulo(self, titulo: str) -> None:
        if titulo == self.titulo:
            return
        self.titulo = titulo
        if self._icone is not None:
            try:
                self._icone.title = titulo
            except Exception:
                pass

    def definir_cor(self, cor_luz: str | None) -> None:
        """
        Repinta o icone com a cor da luz. `None` = apagada ou sem conexao.

        Sai cedo quando a cor nao mudou: o estado da lampada e relido de tempos
        em tempos e a maioria das leituras nao muda nada. Sem esta guarda,
        redesenhar e reenviar o icone para o Windows viraria rotina de fundo
        sem motivo.
        """
        if cor_luz == self._cor_atual:
            return
        self._cor_atual = cor_luz

        if self._icone is None:
            return
        try:
            self._icone.icon = self._desenhar_icone(cor_luz)
        except Exception:
            pass

    def encerrar(self) -> None:
        self._parar_o_relogio()
        if self._icone is not None:
            try:
                self._icone.stop()
            except Exception:
                pass
            self._icone = None
