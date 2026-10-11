"""
Janela sem a moldura do Windows.

POR QUE
-------
A janela inteira precisa ser tematizada, incluindo minimizar e fechar. A
moldura do Windows nao aceita tema: ela vem com a cor do sistema e nao ha API
para pintar so ela. A saida e a do DSE e do AmbiSync -- tirar a moldura e
desenhar a barra de titulo como conteudo da janela.

No Tkinter isso e `overrideredirect(True)`, que resolve o desenho e cria TRES
problemas que este modulo trata:

1. A JANELA SOME DA BARRA DE TAREFAS e do Alt+Tab, porque `overrideredirect`
   liga `WS_EX_TOOLWINDOW`. `_fixar_barra_de_tarefas` desliga esse bit.

2. OS CANTOS FICAM RETOS. O arredondado do Windows 11 vem do compositor e da
   para pedir por `DwmSetWindowAttribute`. Em Windows mais antigo a chamada
   falha calada e os cantos ficam retos -- que e aceitavel.

3. NAO DA MAIS PARA ARRASTAR. `Arrasto` repoe isso.

Nada aqui e obrigatorio: em qualquer sistema que nao seja Windows, ou se
alguma chamada falhar, a janela continua funcionando sem moldura e sem canto
redondo. Uma janela feia e melhor que uma janela que nao abre.

NAO EXISTE MAXIMIZAR, de proposito. A janela tem tamanho util fixo e esticar
so criaria espaco vazio. O DSE e o AmbiSync tambem nao tem, pela mesma razao.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk

log = logging.getLogger(__name__)

NO_WINDOWS = sys.platform == "win32"

# Estilo estendido da janela.
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

# Cantos arredondados (Windows 11).
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def _identificador(janela: tk.Tk) -> int | None:
    """
    O HWND real da janela.

    `winfo_id` devolve o handle do widget, que no Windows e uma janela FILHA.
    Quem tem o estilo estendido e a de cima -- por isso o `GetParent`.
    """
    try:
        import ctypes

        janela.update_idletasks()
        return ctypes.windll.user32.GetParent(janela.winfo_id())
    except Exception as erro:
        log.debug("nao consegui o identificador da janela: %s", erro)
        return None


def pintar_icone(janela: tk.Tk) -> None:
    """
    Poe a marca na barra de tarefas e no Alt+Tab.

    O icone da JANELA e outra coisa que o icone do ARQUIVO: o `.ico` do
    executavel resolve so o Explorer. Sem isto aqui, a barra de tarefas mostra
    a pena, que e o icone padrao do Tk.

    DEPOIS da correcao da barra de tarefas, nao antes: `_fixar_barra_de_tarefas`
    esconde e mostra a janela para o Windows reler o estilo, e o icone definido
    antes desse ciclo se perde.

    AS IMAGENS PRECISAM SOBREVIVER. O Tk nao segura referencia para
    `PhotoImage`; se o Python coletar, o icone some. Ficam presas na propria
    janela, para viverem exatamente o tempo dela.
    """
    try:
        from PIL import ImageTk

        from . import icones
    except ImportError:
        log.info("sem Pillow: a janela fica com o icone padrao do Tk")
        return

    try:
        # Varios tamanhos: o Windows escolhe conforme o lugar (16 no Alt+Tab,
        # 32 na barra de tarefas, 48 em telas grandes).
        imagens = []
        for lado in (16, 32, 48, 64):
            desenho = icones.marca(lado, "#FF5A1F")
            if desenho is not None:
                imagens.append(ImageTk.PhotoImage(desenho))

        if not imagens:
            return

        janela._icones_marca = imagens  # type: ignore[attr-defined]
        janela.iconphoto(True, *imagens)
    except Exception as erro:
        log.debug("nao consegui pintar o icone da janela: %s", erro)


def preparar(janela: tk.Tk, visivel: bool = True) -> None:
    """
    Tira a moldura e repoe o que o Windows tira junto.

    `visivel=False` quando o programa nasce escondido na bandeja. Nesse caso a
    correcao da barra de tarefas NAO roda agora: ela precisa esconder e
    mostrar a janela para o Windows reler o estilo, e fazer isso com o
    programa nascendo oculto colocaria a janela na tela por um instante --
    exatamente o que a opcao existe para evitar. Ela roda na primeira vez que
    a janela aparecer (ver `mostrar` na interface).
    """
    janela.overrideredirect(True)

    # O icone nao depende do Windows: em qualquer sistema, uma janela sem
    # icone proprio mostra o do Tk.
    janela.after(20, lambda: pintar_icone(janela))

    if not NO_WINDOWS:
        return

    janela.after(10, lambda: arredondar(janela))

    if visivel:
        # Precisa da janela ja mapeada.
        janela.after(10, lambda: _fixar_barra_de_tarefas(janela))


def fixar_barra_de_tarefas(janela: tk.Tk) -> None:
    """Publico, para quem nasceu oculto chamar na primeira aparicao."""
    _fixar_barra_de_tarefas(janela)


def _fixar_barra_de_tarefas(janela: tk.Tk) -> None:
    """
    Devolve a janela para a barra de tarefas e para o Alt+Tab.

    Sem isto o programa vira um fantasma: aparece na tela e nao existe em
    lugar nenhum do sistema.

    O `withdraw`/`deiconify` no fim nao e enfeite: o Windows so re-avalia o
    estilo estendido quando a janela e escondida e mostrada de novo.
    """
    identificador = _identificador(janela)
    if not identificador:
        return

    try:
        import ctypes

        user32 = ctypes.windll.user32
        estilo = user32.GetWindowLongW(identificador, GWL_EXSTYLE)
        estilo = (estilo & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        user32.SetWindowLongW(identificador, GWL_EXSTYLE, estilo)

        if janela.winfo_viewable():
            janela.withdraw()
            # (VentiladorArno, 10/out/2026) o withdraw do Tk pode valer DEPOIS
            # do deiconify de 10 ms e a janela ficava escondida para sempre
            # (abria "minimizado"). Confere e repete ate aparecer.
            def garantir(tentativas=20):
                # sem parar cedo: o Tk diz "normal" e o withdraw ainda chega depois
                if janela.state() == "withdrawn":
                    janela.deiconify()
                if tentativas:
                    janela.after(50, lambda: garantir(tentativas - 1))
            janela.after(10, garantir)
    except Exception as erro:
        log.debug("nao consegui devolver a janela a barra de tarefas: %s", erro)


def arredondar(janela: tk.Tk) -> None:
    """Pede cantos arredondados ao compositor. Falha calada em Windows 10."""
    identificador = _identificador(janela)
    if not identificador:
        return

    try:
        import ctypes

        preferencia = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(identificador),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(preferencia),
            ctypes.sizeof(preferencia),
        )
    except Exception as erro:
        log.debug("cantos arredondados indisponiveis: %s", erro)


def app_em_primeiro_plano() -> bool:
    """
    A janela em primeiro plano do Windows e deste programa?

    PARA QUE
    --------
    O popover de configuracoes fecha ao clicar fora, e "fora" tem duas
    metades bem diferentes. Clique em outro widget NOSSO o Tk enxerga e
    entrega -- e disso o proprio popover ja cuida. Clique em outro
    programa, na barra de tarefas ou na area de trabalho NUNCA chega ao
    laco de eventos do Tk: para ele, nada aconteceu. Quem sabe dessa
    metade e o Windows, e so respondendo quando perguntado -- nao ha
    evento de "o usuario foi mexer noutro programa" que chegue ate aqui.

    COMPARA PROCESSO, NAO JANELA
    -----------------------------
    A janela principal, o popover, as dicas e o icone da bandeja sao
    janelas diferentes e todas nossas. Comparar o PROCESSO dono da janela
    de primeiro plano com o nosso resolve as quatro de uma vez, sem
    precisar manter uma lista de identificadores que envelhece a cada
    janelinha nova.

    NA DUVIDA, DEVOLVE True (= "ainda e nosso"). Fora do Windows, ou se a
    chamada falhar, fechar o popover seria adivinhar: o preco de errar
    para o lado de deixar aberto e um clique a mais; para o outro lado, e
    o popover sumindo na cara de quem ia usar.
    """
    if not NO_WINDOWS:
        return True

    try:
        import ctypes
        import os
        from ctypes import wintypes

        # OS TIPOS SAO DECLARADOS, e nao deixados no padrao do ctypes.
        #
        # Sem `restype`, o ctypes trata o retorno como inteiro de 32 bits e
        # o identificador da janela viria cortado num Windows de 64 bits.
        # Na pratica o Windows mantem esses identificadores dentro dos 32
        # bits e o corte nao apareceria -- mas o erro, se um dia
        # aparecesse, seria a vigia simplesmente nunca disparar, sem nada
        # no registro dizendo por que. Barato demais de evitar.
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        em_primeiro = user32.GetForegroundWindow()
        if not em_primeiro:
            return True

        dono = wintypes.DWORD()
        user32.GetWindowThreadProcessId(em_primeiro, ctypes.byref(dono))
        if not dono.value:
            return True

        return dono.value == os.getpid()
    except Exception as erro:
        log.debug("nao consegui ver quem esta em primeiro plano: %s", erro)
        return True


def minimizar(janela: tk.Tk) -> bool:
    """
    Minimiza de verdade, pela API do Windows.

    `janela.iconify()` NAO funciona aqui: numa janela `overrideredirect` o Tk
    recusa com "can't iconify: override-redirect flag is set". O caminho e
    pedir direto ao Windows, que aceita porque `_fixar_barra_de_tarefas` ja
    devolveu a janela para a barra de tarefas -- entao existe um botao para
    restaurar depois.
    """
    if not NO_WINDOWS:
        try:
            janela.iconify()
            return True
        except Exception as erro:
            log.debug("nao consegui minimizar: %s", erro)
            return False

    identificador = _identificador(janela)
    if not identificador:
        return False

    try:
        import ctypes

        # 6 = SW_MINIMIZE
        ctypes.windll.user32.ShowWindow(identificador, 6)
        return True
    except Exception as erro:
        log.debug("nao consegui minimizar: %s", erro)
        return False


def area_util() -> tuple[int, int, int, int] | None:
    """(x, y, largura, altura) da tela SEM a barra de tarefas."""
    if not NO_WINDOWS:
        return None

    try:
        import ctypes
        from ctypes import wintypes

        retangulo = wintypes.RECT()
        # 0x0030 = SPI_GETWORKAREA
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(retangulo), 0
        )
        if not ok:
            return None
        return (
            retangulo.left,
            retangulo.top,
            retangulo.right - retangulo.left,
            retangulo.bottom - retangulo.top,
        )
    except Exception as erro:
        log.debug("nao consegui a area util: %s", erro)
        return None


def centralizar(janela: tk.Tk, largura: int, altura: int) -> None:
    """Poe a janela no meio da area util, ou no meio da tela se nao souber."""
    area = area_util()
    if area is not None:
        x0, y0, disponivel_l, disponivel_a = area
    else:
        x0, y0 = 0, 0
        disponivel_l = janela.winfo_screenwidth()
        disponivel_a = janela.winfo_screenheight()

    x = x0 + max(0, (disponivel_l - largura) // 2)
    y = y0 + max(0, (disponivel_a - altura) // 2)
    janela.geometry(f"{largura}x{altura}+{x}+{y}")


class Arrasto:
    """
    Deixa a janela ser arrastada por um widget.

    Guarda o deslocamento entre o ponteiro e o canto da janela no momento do
    clique. Sem isso a janela pula para debaixo do cursor no primeiro pixel de
    movimento, que e o defeito classico de barra de titulo caseira.
    """

    def __init__(self, janela: tk.Tk):
        self.janela = janela
        self._dx = 0
        self._dy = 0

    def ligar(self, widget: tk.Misc) -> None:
        widget.bind("<Button-1>", self._pegou, add="+")
        widget.bind("<B1-Motion>", self._moveu, add="+")

    def _pegou(self, evento) -> None:
        self._dx = evento.x_root - self.janela.winfo_x()
        self._dy = evento.y_root - self.janela.winfo_y()

    def _moveu(self, evento) -> None:
        self.janela.geometry(
            f"+{evento.x_root - self._dx}+{evento.y_root - self._dy}"
        )
