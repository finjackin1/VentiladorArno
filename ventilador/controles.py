"""Controles do padrao "app simples": poucos, todos em Canvas com canto
redondo de verdade, teclado completo e foco visivel (borda clareia).

Botao, BotaoBarra (segurar para sair), Chave, Passo (- valor +), Painel,
Menu (menu da casa), Dica. Todo controle "escuta a funcao": se a funcao
devolver False ou levantar erro, ele volta ao estado anterior.
"""
from __future__ import annotations

import logging
import time
import tkinter as tk

from . import estilo as E

log = logging.getLogger(__name__)


def ouvir(funcao, *args) -> bool:
    """Roda a funcao do controle; False/erro = o controle desfaz."""
    try:
        return funcao(*args) is not False
    except Exception:
        log.exception("acao de controle falhou")
        return False


class _Cor:
    """Transicao curta de cor (120 ms) pelo relogio, sem pular."""

    def __init__(self, w: tk.Misc, aplicar):
        self.w, self.aplicar, self.atual, self._job = w, aplicar, None, None

    def ir(self, alvo: str, ms: int = 120):
        try:
            if self._job:
                self.w.after_cancel(self._job)
                self._job = None
            if self.atual is None or ms <= 0 or alvo == self.atual:
                self.atual = alvo
                self.aplicar(alvo)
                return
        except tk.TclError:          # widget ja destruido (troca de tela no meio)
            return
        de, t0 = self.atual, time.perf_counter()

        def passo():
            try:
                k = min(1.0, (time.perf_counter() - t0) * 1000 / ms)
                k2 = 1 - (1 - k) ** 2
                self.atual = E.misturar(alvo, de, k2) if k < 1 else alvo
                self.aplicar(self.atual)
                self._job = self.w.after(12, passo) if k < 1 else None
            except tk.TclError:
                self._job = None

        passo()


class Botao(tk.Canvas):
    """Botao arredondado. `selecionado` = laranja (acao/estado)."""

    def __init__(self, pai, texto="", icone=None, ao_clicar=None, largura=120, altura=40,
                 raio=10, fundo=E.FUNDO, cor=E.CAMADA_2, cor_texto=E.TEXTO, tam=11,
                 peso="semibold", lado_icone=18, dica=None):
        super().__init__(pai, width=E.px(largura), height=E.px(altura), bg=fundo,
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.texto, self.nome_icone, self.ao_clicar = texto, icone, ao_clicar
        self.fundo, self.cor_base, self.cor_texto = fundo, cor, cor_texto
        self.raio, self.tam, self.peso, self.lado_icone = raio, tam, peso, lado_icone
        self.selecionado = False
        self.habilitado = True
        self._mouse = False
        self._foco = False
        self._img = self.create_image(0, 0, anchor="nw")
        self._ico = self.create_image(0, 0)
        self._txt = self.create_text(0, 0, fill=cor_texto, font=E.fonte(tam, peso))
        self._cor = _Cor(self, self._pintar_cor)
        self.bind("<Configure>", lambda _e=None: self._pintar(0))
        self.bind("<Enter>", lambda _e=None: self._mouse_em(True))
        self.bind("<Leave>", lambda _e=None: self._mouse_em(False))
        self.bind("<ButtonRelease-1>", self._soltou)
        self.bind("<FocusIn>", lambda _e=None: self._foco_em(True))
        self.bind("<FocusOut>", lambda _e=None: self._foco_em(False))
        self.bind("<Return>", lambda _e=None: self._agir())
        self.bind("<space>", lambda _e=None: self._agir())
        if dica:
            Dica(self, dica)

    # -- estado
    def definir(self, selecionado: bool | None = None, texto: str | None = None,
                habilitado: bool | None = None, icone: str | None = None, ms: int = 120):
        if selecionado is not None:
            self.selecionado = selecionado
        if texto is not None:
            self.texto = texto
        if habilitado is not None:
            self.habilitado = habilitado
            self.config(cursor="hand2" if habilitado else "arrow")
        if icone is not None:
            self.nome_icone = icone
        self._pintar(ms)

    def _alvo(self):
        if self.selecionado:
            return E.ACENTO
        if self._mouse and self.habilitado:
            return E.misturar(E.TEXTO, self.cor_base, 0.10)
        return self.cor_base

    def _cor_frente(self):
        if self.selecionado:
            return "#FFFFFF"
        return self.cor_texto if self.habilitado else E.APAGADO

    def _pintar(self, ms=120):
        self._cor.ir(self._alvo(), ms)

    def _pintar_cor(self, cor):
        w, h = max(2, self.winfo_width()), max(2, self.winfo_height())
        if w <= 2:
            w, h = int(self["width"]), int(self["height"])
        borda = E.FOCO if self._foco else None
        self.itemconfig(self._img, image=E.ret(w, h, E.px(self.raio), cor, self.fundo, borda, max(1, E.px(1.2))))
        frente = self._cor_frente()
        tem_txt = bool(self.texto)
        if self.nome_icone:
            lado = E.px(self.lado_icone)
            self.itemconfig(self._ico, image=E.icone(self.nome_icone, lado, frente), state="normal")
            fnt = self.tk.call("font", "measure", E.fonte(self.tam, self.peso), self.texto) if tem_txt else 0
            vao = E.px(8) if tem_txt else 0
            x0 = (w - (lado + vao + fnt)) / 2
            if self.nome_icone == "seta_baixo":        # lista suspensa: seta depois do texto
                self.coords(self._txt, x0 + fnt / 2, h / 2)
                self.coords(self._ico, x0 + fnt + vao + lado / 2, h / 2)
            else:
                self.coords(self._ico, x0 + lado / 2, h / 2)
                self.coords(self._txt, x0 + lado + vao + fnt / 2, h / 2)
        else:
            self.itemconfig(self._ico, state="hidden")
            self.coords(self._txt, w / 2, h / 2)
        self.itemconfig(self._txt, text=self.texto, fill=frente)

    def _mouse_em(self, v):
        self._mouse = v
        self._pintar()

    def _foco_em(self, v):
        self._foco = v
        self._pintar(0)

    def _soltou(self, e):
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self._agir()

    def _agir(self):
        if self.habilitado and self.ao_clicar:
            self.ao_clicar()
        return "break"


class BotaoBarra(tk.Canvas):
    """Celula da barra de titulo: so o icone acende com o mouse.
    `ao_segurar` (fechar): segurar 1 s sai; a cor nasce do centro."""

    SEGURAR_S = 1.0

    def __init__(self, pai, icone, ao_clicar, largura=34, altura=34, ao_segurar=None,
                 cor_segurar=E.FECHAR_SEGURAR, dica=None):
        super().__init__(pai, width=E.px(largura), height=E.px(altura), bg=E.FUNDO_FUNDO,
                         highlightthickness=0, bd=0, takefocus=0)
        self.icone, self.ao_clicar, self.ao_segurar = icone, ao_clicar, ao_segurar
        self.cor_segurar = cor_segurar
        self.aceso = False            # tela aberta = icone laranja
        self._mouse = False
        self._t0 = None
        self._job = None
        self._enchido = self.create_image(0, 0)
        self._ico = self.create_image(0, 0)
        self.bind("<Configure>", lambda _e=None: self._pintar())
        self.bind("<Enter>", lambda _e=None: self._em(True))
        self.bind("<Leave>", lambda _e=None: self._em(False))
        self.bind("<ButtonPress-1>", self._apertou)
        self.bind("<ButtonRelease-1>", self._soltou)
        if dica:
            Dica(self, dica)

    def _em(self, v):
        self._mouse = v
        self._pintar()

    def acender(self, v: bool):
        self.aceso = v
        self._pintar()

    def _pintar(self, k: float = 0.0):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2:
            w, h = int(self["width"]), int(self["height"])
        lado = E.px(16)
        if k > 0:
            cw, ch = max(2, int(w * k)), max(2, int(h * k))
            self.itemconfig(self._enchido, image=E.ret(cw, ch, E.px(6) if k < 1 else 0, self.cor_segurar, E.FUNDO_FUNDO),
                            state="normal")
            self.coords(self._enchido, w / 2, h / 2)
            cor = "#FFFFFF"
        else:
            self.itemconfig(self._enchido, state="hidden")
            cor = E.ACENTO if self.aceso else (E.TEXTO if self._mouse else E.TEXTO_2)
        self.itemconfig(self._ico, image=E.icone(self.icone, lado, cor))
        self.coords(self._ico, w / 2, h / 2)

    def _apertou(self, _e=None):
        if not self.ao_segurar:
            return
        self._t0 = time.perf_counter()

        def passo():
            if self._t0 is None:
                return
            k = (time.perf_counter() - self._t0) / self.SEGURAR_S
            if k >= 1:
                self._t0 = None
                self._job = None
                self._pintar(1.0)
                self.ao_segurar()
                return
            try:
                self._pintar(max(0.05, k))
                self._job = self.after(12, passo)
            except tk.TclError:
                self._job = None

        self._job = self.after(150, passo)    # clique rapido nao pisca

    def _soltou(self, e):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self.ao_segurar and self._t0 is None:
            return                              # ja saiu pelo segurar
        self._t0 = None
        self._pintar()
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.ao_clicar()


class Chave(tk.Canvas):
    """Interruptor. Muda na hora e escuta a funcao (False = volta)."""

    def __init__(self, pai, ligado: bool, ao_mudar, fundo=E.CAMADA_1):
        super().__init__(pai, width=E.px(40), height=E.px(22), bg=fundo, highlightthickness=0,
                         bd=0, takefocus=1, cursor="hand2")
        self.ligado, self.ao_mudar, self.fundo = ligado, ao_mudar, fundo
        self._foco = False
        self._img = self.create_image(0, 0, anchor="nw")
        self._bola = self.create_image(0, 0)
        self._x = None
        self.bind("<ButtonRelease-1>", lambda _e=None: self.alternar())
        self.bind("<space>", lambda _e=None: self.alternar())
        self.bind("<Return>", lambda _e=None: self.alternar())
        self.bind("<FocusIn>", lambda _e=None: self._f(True))
        self.bind("<FocusOut>", lambda _e=None: self._f(False))
        self._pintar(animar=False)

    def _f(self, v):
        self._foco = v
        self._pintar(animar=False)

    def definir(self, ligado: bool):
        if ligado != self.ligado:
            self.ligado = ligado
            self._pintar()

    def alternar(self):
        antes = self.ligado
        self.ligado = not antes
        self._pintar()
        if not ouvir(self.ao_mudar, self.ligado):
            self.ligado = antes
            self._pintar()

    def _pintar(self, animar=True):
        w, h = E.px(40), E.px(22)
        cor = E.ACENTO if self.ligado else E.CAMADA_2
        borda = E.FOCO if self._foco else (None if self.ligado else E.BORDA_MOUSE)
        self.itemconfig(self._img, image=E.ret(w, h, h // 2, cor, self.fundo, borda, max(1, E.px(1))))
        lado = h - E.px(8)
        bola = E.ret(lado, lado, lado // 2, "#FFFFFF" if self.ligado else E.TEXTO_2, cor)
        self.itemconfig(self._bola, image=bola)
        alvo = (w - h / 2) if self.ligado else h / 2
        if not animar or self._x is None:
            self._x = alvo
            self.coords(self._bola, alvo, h / 2)
            return
        de, t0 = self._x, time.perf_counter()

        def passo():
            k = min(1.0, (time.perf_counter() - t0) / 0.15)
            k2 = 1 - (1 - k) ** 3
            self._x = de + (alvo - de) * k2
            try:
                self.coords(self._bola, self._x, h / 2)
                if k < 1:
                    self.after(12, passo)
            except tk.TclError:
                pass

        passo()


class Passo(tk.Frame):
    """[-] valor [+] com teclado (setas). `formatar(v)` -> texto."""

    def __init__(self, pai, valor: int, minimo: int, maximo: int, passo: int, formatar,
                 ao_mudar, fundo=E.CAMADA_1, largura_texto=70, passos=None):
        super().__init__(pai, bg=fundo)
        self.valor, self.minimo, self.maximo = valor, minimo, maximo
        self.passo, self.formatar, self.ao_mudar = passo, formatar, ao_mudar
        self.passos = passos     # lista de valores fixos (opcional)
        self.menos = Botao(self, icone="menos", ao_clicar=lambda: self.mudar(-1), largura=32,
                           altura=32, raio=8, fundo=fundo, lado_icone=14)
        self.mais = Botao(self, icone="mais", ao_clicar=lambda: self.mudar(+1), largura=32,
                          altura=32, raio=8, fundo=fundo, lado_icone=14)
        self.menos.pack(side="left")
        self.caixa = tk.Frame(self, bg=fundo, width=E.px(largura_texto), height=E.px(32))
        self.caixa.pack_propagate(False)
        self.caixa.pack(side="left")
        self.rot = tk.Label(self.caixa, text=formatar(valor), bg=fundo, fg=E.TEXTO,
                            font=E.fonte(11, "semibold"))
        self.rot.pack(expand=True)
        self.mais.pack(side="left")
        for w in (self.menos, self.mais):
            w.bind("<Left>", lambda _e=None: self.mudar(-1) or "break")
            w.bind("<Right>", lambda _e=None: self.mudar(+1) or "break")

    def _proximo(self, d):
        if self.passos:
            lst = self.passos
            if d > 0:
                return next((p for p in lst if p > self.valor), lst[-1])
            return next((p for p in reversed(lst) if p < self.valor), lst[0])
        return max(self.minimo, min(self.maximo, self.valor + d * self.passo))

    def mudar(self, d):
        novo = self._proximo(d)
        if novo == self.valor:
            return
        antes = self.valor
        self.valor = novo
        self.rot.config(text=self.formatar(novo))
        if not ouvir(self.ao_mudar, novo):
            self.valor = antes
            self.rot.config(text=self.formatar(antes))

    def definir(self, v):
        self.valor = v
        self.rot.config(text=self.formatar(v))


class Painel(tk.Canvas):
    """Segmento num painel sutil: meio tom acima do fundo, borda quase
    invisivel, cantos redondos. Conteudo vai em `self.dentro`."""

    def __init__(self, pai, fundo=E.FUNDO, cor=E.CAMADA_1, borda=E.LINHA, raio=12, folga=12,
                 encher=False):
        """encher=True: o painel ocupa o espaco que o pai der (janela de tamanho
        fixo) e o conteudo recebe a altura toda; senao, segue a altura do conteudo."""
        super().__init__(pai, bg=fundo, highlightthickness=0, bd=0, height=10)
        self.fundo, self.cor, self.borda, self.raio = fundo, cor, borda, raio
        self.encher = encher
        self.f = E.px(folga)
        self.dentro = tk.Frame(self, bg=cor)
        self._img = self.create_image(0, 0, anchor="nw")
        self._win = self.create_window(self.f, self.f, window=self.dentro, anchor="nw")
        self.dentro.bind("<Configure>", self._conteudo)
        self.bind("<Configure>", self._tamanho)

    def _conteudo(self, _e=None):
        if self.encher:
            return
        h = self.dentro.winfo_reqheight() + 2 * self.f
        if int(self["height"]) != h:
            self.config(height=h)

    @staticmethod
    def medir_todos(w: tk.Misc):
        """Antes de medir a janela: cada painel ja na altura do conteudo
        (o <Configure> do conteudo so chega depois de mapeado)."""
        for f in w.winfo_children():
            Painel.medir_todos(f)
            if isinstance(f, Painel) and not f.encher:
                f.update_idletasks()
                f._conteudo()

    def _tamanho(self, e):
        w, h = e.width, e.height
        if w < 4 or h < 4:
            return
        self.itemconfig(self._win, width=w - 2 * self.f)
        if self.encher:
            self.itemconfig(self._win, height=max(1, h - 2 * self.f))
        self.itemconfig(self._img, image=E.ret(w, h, E.px(self.raio), self.cor, self.fundo,
                                               self.borda, 1))


class Rolagem(tk.Canvas):
    """Area que rola (lista que pode passar da altura numa janela fixa).
    Conteudo em `self.dentro`. Rodinha do mouse em qualquer ponto dela;
    barra fina arredondada so quando passa da altura, num vao de 8 px a
    direita (janela embutida no canvas cobre os desenhos dele)."""

    VAO = 8
    _instalado: set = set()

    def __init__(self, pai, fundo=E.CAMADA_1):
        super().__init__(pai, bg=fundo, highlightthickness=0, bd=0, yscrollincrement=1)
        self.dentro = tk.Frame(self, bg=fundo)
        self._win = self.create_window(0, 0, window=self.dentro, anchor="nw")
        self._barra = self.create_line(0, 0, 0, 0, fill=E.misturar(E.TEXTO, fundo, 0.25),
                                       width=E.px(3), capstyle="round", state="hidden")
        # medir DEPOIS do Tk recalcular o tamanho pedido: no proprio <Configure>
        # a lista que encolheu ainda diz a altura velha e a rolagem ficava presa
        # la embaixo (achado no check, 10/out/2026)
        self._job = None
        self.dentro.bind("<Configure>", lambda _e=None: self._medir_depois())
        self.bind("<Configure>", self._tamanho)
        raiz = self.winfo_toplevel()
        if str(raiz) not in Rolagem._instalado:
            Rolagem._instalado.add(str(raiz))
            raiz.bind_all("<MouseWheel>", Rolagem._rodinha, add="+")

    @staticmethod
    def _rodinha(e):
        try:
            w = e.widget.winfo_containing(e.x_root, e.y_root)
        except (tk.TclError, AttributeError, KeyError):
            return
        while w is not None and not isinstance(w, Rolagem):
            w = w.master
        if w is not None:
            w.rolar(-e.delta / 120 * E.px(40))

    def rolar(self, px_: float):
        h_conteudo = self.dentro.winfo_reqheight()
        h = self.winfo_height()
        if h_conteudo <= h:
            return
        y = self.canvasy(0) + px_
        y = max(0, min(h_conteudo - h, y))
        self.yview_moveto(y / h_conteudo)
        self._pintar_barra()

    def topo(self):
        self.yview_moveto(0)
        self._pintar_barra()

    def mostrar(self, w: tk.Widget):
        """Rola ate `w` ficar a vista (item recem-adicionado nunca nasce
        escondido abaixo da dobra -- pedido dele, 10/out/2026)."""
        def ir():
            try:
                self.update_idletasks()
                self._medir()
                y, p = 0, w
                while p is not None and p is not self.dentro:
                    y += p.winfo_y()
                    p = p.master
                if p is None:
                    return
                h, alto = self.winfo_height(), w.winfo_height()
                topo = self.canvasy(0)
                if y < topo:
                    self.rolar(y - topo - E.px(8))
                elif y + alto > topo + h:
                    self.rolar(y + alto - (topo + h) + E.px(24))   # mostra tambem o fim do painel
            except tk.TclError:
                pass
        self.after_idle(ir)

    def _tamanho(self, e):
        self.itemconfig(self._win, width=max(1, e.width - E.px(self.VAO)))
        self._medir()

    def _medir_depois(self):
        if self._job is None:
            self._job = self.after_idle(self._medir)

    def _medir(self):
        self._job = None
        try:
            h_conteudo = self.dentro.winfo_reqheight()
        except tk.TclError:
            return
        h = self.winfo_height()
        total = max(h_conteudo, h)
        y = self.canvasy(0)
        self.configure(scrollregion=(0, 0, self.winfo_width(), total))
        # lista encolheu: nunca deixar a vista alem do fim (nem do topo)
        y = max(0, min(y, total - h))
        self.yview_moveto(y / max(1, total))
        self._pintar_barra()

    def atualizar(self):
        """Chamar depois de refazer o conteudo (lista nova)."""
        self._medir_depois()

    def _pintar_barra(self):
        h_conteudo = self.dentro.winfo_reqheight()
        h, w = self.winfo_height(), self.winfo_width()
        if h_conteudo <= h or h < 10:
            self.itemconfig(self._barra, state="hidden")
            return
        y0 = self.canvasy(0)
        alto = max(E.px(24), h * h / h_conteudo)
        topo = y0 + (h - alto) * (y0 / max(1, h_conteudo - h))
        x = w - E.px(3)
        r = E.px(2)
        self.coords(self._barra, x, topo + r, x, topo + alto - r)
        self.itemconfig(self._barra, state="normal")


class Menu:
    """Menu da casa: janelinha SUPERFICIE com curva do Windows, itens em
    pilula discreta, setas/Enter. Esmaece ao abrir.

    (10/out/2026, pedido dele) Fica SO no programa: janela "dona" = a janela
    principal (transient), nunca -topmost; vai para tras junto quando outro
    programa vem para a frente. Some com QUALQUER clique fora: dentro do
    programa (bind_all) ou em outro programa/area de trabalho (vigia de
    primeiro plano a cada 100 ms), e se a janela mexer ou esconder.
    Clicar na ancora com o menu aberto so fecha (nao reabre)."""

    _aberto: "Menu | None" = None
    _fechou = (None, 0.0)        # (ancora, quando) do ultimo fechamento por clique

    def __init__(self, ancora: tk.Widget, itens: list[tuple[str, object]], marcado=None,
                 alinhar="esquerda"):
        self.ancora = ancora
        self.top = None
        a, quando = Menu._fechou
        if a is ancora and time.perf_counter() - quando < 0.4:
            return                                   # o clique que fechou era na propria ancora
        if Menu._aberto:
            Menu._aberto.fechar()
        Menu._aberto = self
        dono = ancora.winfo_toplevel()
        self.top = top = tk.Toplevel(ancora)
        top.overrideredirect(True)
        _prender(top, dono)
        top.configure(bg=E.SUPERFICIE_BORDA)
        try:
            top.attributes("-alpha", 0.0)
        except Exception:
            pass
        caixa = tk.Frame(top, bg=E.SUPERFICIE, padx=E.px(4), pady=E.px(4))
        caixa.pack(padx=1, pady=1)
        self.linhas = []
        self.i = 0
        for n, (rotulo, acao) in enumerate(itens):
            l = tk.Label(caixa, text=rotulo, bg=E.SUPERFICIE, fg=E.TEXTO, anchor="w",
                         font=E.fonte(10.5, "semibold" if rotulo == marcado else "normal"),
                         padx=E.px(12), pady=E.px(6), cursor="hand2")
            l.pack(fill="x")
            l.bind("<Enter>", lambda _e=None, k=n: self._ir(k))
            l.bind("<ButtonRelease-1>", lambda _e=None, a=acao: self._escolher(a))
            self.linhas.append((l, acao))
            if rotulo == marcado:
                self.i = n
        top.update_idletasks()
        x = ancora.winfo_rootx()
        if alinhar == "direita":
            x = ancora.winfo_rootx() + ancora.winfo_width() - top.winfo_reqwidth()
        y = ancora.winfo_rooty() + ancora.winfo_height() + E.px(4)
        if y + top.winfo_reqheight() > ancora.winfo_screenheight() - E.px(48):
            y = ancora.winfo_rooty() - top.winfo_reqheight() - E.px(4)
        top.geometry(f"+{x}+{y}")
        _arredondar(top)
        _por_cima(top)
        self._ir(self.i)
        top.bind("<Up>", lambda _e=None: self._ir((self.i - 1) % len(self.linhas)))
        top.bind("<Down>", lambda _e=None: self._ir((self.i + 1) % len(self.linhas)))
        top.bind("<Return>", lambda _e=None: self._escolher(self.linhas[self.i][1]))
        top.bind("<Escape>", lambda _e=None: (self.fechar("Esc"), ativar(self._dono)))
        top.focus_force()
        # fecha com clique em qualquer lugar do programa fora do menu
        dono.bind_all("<ButtonPress>", self._clique_global, add="+")
        self._dono = dono
        self._pos_dono = (dono.winfo_x(), dono.winfo_y())
        self._fg0 = None
        top.after(100, self._vigiar)
        log.info("menu aberto (%s itens)", len(itens))
        t0 = time.perf_counter()

        def surgir():
            k = min(1.0, (time.perf_counter() - t0) / 0.2)
            try:
                top.attributes("-alpha", 1 - (1 - k) ** 3)
            except Exception:
                return
            if k < 1:
                top.after(10, surgir)

        surgir()

    def _ir(self, k):
        for n, (l, _a) in enumerate(self.linhas):
            l.config(bg=E.misturar(E.TEXTO, E.SUPERFICIE, 0.10) if n == k else E.SUPERFICIE)
        self.i = k

    def _clique_global(self, e):
        if self.top is None:
            return
        try:
            w = e.widget if isinstance(e.widget, tk.Misc) else self.top.nametowidget(str(e.widget))
            dentro = w.winfo_toplevel() is self.top
        except Exception:
            dentro = True              # na duvida nao fecha (fechar a toa era o bug)
        if not dentro:
            Menu._fechou = (self.ancora, time.perf_counter())
            self.fechar(f"clique fora no programa ({str(e.widget)[-40:]})")

    def _vigiar(self):
        """Fecha com clique de VERDADE fora do menu (botao do mouse apertado
        com o ponteiro fora dele e da ancora: pega outro programa e area de
        trabalho), com OUTRO programa vindo para a frente DEPOIS de abrir, ou
        se a janela mexer/esconder.

        (10/out/2026, bug relatado por ele: "clico no + e nada acontece") a
        versao anterior fechava se o programa nao estivesse em primeiro plano
        -- e a janela sem moldura nem sempre vira a ativa do Windows no clique:
        o menu abria e sumia em 0,1 s, em TODOS os menus."""
        if self.top is None:
            return
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            dono = self._dono
            if not dono.winfo_viewable() or (dono.winfo_x(), dono.winfo_y()) != self._pos_dono:
                self.fechar("janela mexeu/escondeu")
                return
            apertado = (u.GetAsyncKeyState(0x01) & 0x8000) or (u.GetAsyncKeyState(0x02) & 0x8000)
            if apertado and not self._ponteiro_no_programa():
                # clique em OUTRO programa ou na area de trabalho; clique dentro do
                # programa (menu, janela) e tratado pelo bind_all, que sabe o widget
                self.fechar("clique em outro programa")
                return
            u.GetForegroundWindow.restype = wintypes.HWND
            fg = u.GetForegroundWindow()
            if self._fg0 is None:
                self._fg0 = fg                      # quem estava na frente ao abrir
            elif fg and fg != self._fg0:
                from . import moldura
                if not moldura.app_em_primeiro_plano():
                    self.fechar("outro programa na frente")
                    return
        except Exception:
            log.debug("vigia do menu", exc_info=True)
        self.top.after(50, self._vigiar)

    @staticmethod
    def _ponteiro_no_programa() -> bool:
        """A janela sob o ponteiro e DESTE processo? Quem responde e o Windows
        (WindowFromPoint), sem conta de coordenada do Tk -- a conta anterior
        tomava o clique NUM ITEM do menu como "fora" e o menu fechava sem
        escolher (bug relatado por ele, 10/out/2026). Na duvida: True."""
        try:
            import ctypes
            import os
            from ctypes import wintypes
            u = ctypes.windll.user32
            pt = wintypes.POINT()
            u.GetCursorPos(ctypes.byref(pt))
            u.WindowFromPoint.argtypes = [wintypes.POINT]
            u.WindowFromPoint.restype = wintypes.HWND
            h = u.WindowFromPoint(pt)
            if not h:
                return True
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            return pid.value == os.getpid()
        except Exception:
            return True

    def _escolher(self, acao):
        self.fechar("escolheu")
        ativar(self._dono)          # o teclado volta para o programa (senao fica sem dono)
        if callable(acao):
            acao()

    def fechar(self, motivo: str = ""):
        if self.top is None:
            return
        log.info("menu fechado: %s", motivo or "pedido")
        try:
            self._dono.tk.call("bind", "all", "<ButtonPress>", "")
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass
        self.top = None
        if Menu._aberto is self:
            Menu._aberto = None


class Dica:
    """Dica ao repousar 0,6 s: SUPERFICIE, texto curto."""

    def __init__(self, w: tk.Widget, texto: str):
        self.w, self.texto, self.top, self._job = w, texto, None, None
        w.bind("<Enter>", self._entrou, add="+")
        w.bind("<Leave>", self._saiu, add="+")
        w.bind("<ButtonPress>", self._saiu, add="+")

    def _entrou(self, _e=None):
        self._job = self.w.after(600, self._mostrar)

    def _saiu(self, _e=None):
        if self._job:
            self.w.after_cancel(self._job)
            self._job = None
        if self.top:
            self.top.destroy()
            self.top = None

    def _mostrar(self):
        self._job = None
        try:
            if not self.w.winfo_viewable():
                return
        except tk.TclError:
            return
        self.top = t = tk.Toplevel(self.w)
        t.overrideredirect(True)
        _prender(t, self.w.winfo_toplevel())      # so no programa, nunca acima dos outros
        t.configure(bg=E.SUPERFICIE_BORDA)
        tk.Label(t, text=self.texto, bg=E.SUPERFICIE, fg=E.TEXTO, font=E.fonte(9.5),
                 padx=E.px(8), pady=E.px(4), justify="left").pack(padx=1, pady=1)
        t.update_idletasks()
        x = self.w.winfo_rootx() + self.w.winfo_width() // 2 - t.winfo_reqwidth() // 2
        x = min(x, self.w.winfo_screenwidth() - t.winfo_reqwidth() - 4)
        t.geometry(f"+{max(0, x)}+{self.w.winfo_rooty() + self.w.winfo_height() + E.px(4)}")
        _arredondar(t)
        _por_cima(t)


def _prender(top: tk.Toplevel, dono: tk.Misc):
    """Dono de verdade no Windows: o Tk aceita `transient` numa janela sem
    moldura mas nao muda o dono (achado 10/out/2026). Com dono, a janelinha
    fica acima SO da janela do programa e vai para tras junto com ela."""
    top.transient(dono)
    try:
        import ctypes
        top.update_idletasks()
        u = ctypes.windll.user32
        u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        u.SetWindowLongPtrW(int(top.wm_frame(), 16), -8, int(dono.wm_frame(), 16))   # GWLP_HWNDPARENT
    except Exception:
        log.debug("nao prendi a janelinha ao dono", exc_info=True)


def ativar(janela: tk.Misc, widget: tk.Misc | None = None):
    """Devolve o TECLADO ao programa: janela ativa no Windows + foco no widget.
    A janela sem moldura nao recupera o teclado sozinha quando a janelinha do
    menu fecha (o foco ficava None e as teclas do atalho iam para outro
    programa -- bug relatado por ele, 10/out/2026)."""
    try:
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(int(janela.winfo_toplevel().wm_frame(), 16))
    except Exception:
        pass
    try:
        (widget or janela).focus_force()
    except tk.TclError:
        pass


def _por_cima(top: tk.Toplevel):
    """Traz a janelinha para cima da janela do programa. Trocar o dono depois
    de criada NAO reordena: o menu ficava ATRAS da janela principal, os cliques
    caiam nos botoes de baixo e "nada acontecia" (bug relatado por ele,
    10/out/2026; achado pela ordem Z, ver scripts/teste_menu_exemplo.py)."""
    try:
        top.lift()
        import ctypes
        u = ctypes.windll.user32
        u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        # HWND_TOP; SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
        u.SetWindowPos(int(top.wm_frame(), 16), 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    except Exception:
        log.debug("nao trouxe a janelinha para cima", exc_info=True)


def _arredondar(top: tk.Toplevel):
    """Curva do Windows 11 numa janelinha sem moldura (falha calada no 10)."""
    try:
        import ctypes
        top.update_idletasks()
        h = ctypes.windll.user32.GetParent(top.winfo_id())
        pref = ctypes.c_int(3)    # DWMWCP_ROUNDSMALL
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(h), 33, ctypes.byref(pref), 4)
    except Exception:
        pass
