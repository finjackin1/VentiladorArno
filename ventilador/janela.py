"""A janela do padrao "app simples": barra propria, UMA tela principal,
telas secundarias pela barra (agenda, opcoes) e editores; rodape com o
indicador de conexao. Nada aqui fala BLE direto: tudo pela `Conexao`.
"""
from __future__ import annotations

import datetime
import logging
import os
import tkinter as tk

from . import __version__, atalhos as AT, estilo as E, inicio_windows, moldura
from . import protocolo as P
from .agenda import Agenda, dias_texto
from .bandeja import Bandeja
from .caminhos import relatorios
from .config import Config, novo_id
from . import controles as C
from .controles import Botao, BotaoBarra, Chave, Menu, Painel, Passo, Rolagem
from .motor_atalhos import Motor

log = logging.getLogger(__name__)

# Janela de TAMANHO FIXO 5:4 (pedido dele, 10/out/2026: "toda janela tem que
# ter tamanho fixo"). Em 100%; px() escala. Nenhuma tela muda o tamanho: o que
# pode passar da altura rola (Rolagem).
LARGURA, ALTURA = 500, 400
MARGEM = 14
COL_ESQ = 222            # coluna dos controles / dica
COL_DIR_EDITOR = 170     # coluna do nome e botoes no editor de rotina
TIMER_PASSOS = [15, 30, 45, 60, 90, 120, 180, 240, 300, 360, 480, 600, 720]
PASSO_MIN = [5, 10, 15, 20, 30, 45, 60, 90, 120, 150, 180, 240, 300, 360, 420, 480, 540, 600, 720]
ESTADOS = {
    "procurando": "Procurando o ventilador…",
    "conectando": "Conectando…",
    "conectado": "Conectado",
    "solto": "Solto: o celular pode usar",
    "sem_bluetooth": "Bluetooth do PC desligado ou ausente",
}
PEDIDO_MOSTRAR = relatorios() / ".mostrar"


def fmt_min(m: int) -> str:
    h, mm = divmod(int(m), 60)
    if not h:
        return f"{mm} min"
    return f"{h} h" if not mm else f"{h} h {mm:02d}"


def resumo_passos(passos) -> str:
    if not passos:
        return "sem passos"
    vels = " → ".join("desl." if v == 0 else str(v) for v, _ in passos)
    return f"{vels} · {fmt_min(sum(m for _, m in passos))}"


class Janela:
    def __init__(self, conexao, escondida: bool = False):
        self.cfg = Config.carregar()
        self.cx = conexao
        self.raiz = r = tk.Tk()
        # erro dentro de um clique/after vai pro log e a janela segue viva
        r.report_callback_exception = lambda *e: log.error("erro na interface", exc_info=e)
        self._job_gravar = None
        E.iniciar(r)
        r.title("Ventilador Arno")
        r.configure(bg=E.SUPERFICIE_BORDA)
        moldura.preparar(r, visivel=not escondida)
        self._ja_mostrou = not escondida
        self.vel = 0                  # velocidade real (status)
        self.estado = "procurando"
        self._ignorar_status_ate = 0.0
        self._ao_abrir_feito = False
        self.timer_fim: datetime.datetime | None = None
        self.rotina_rodando: tuple[str, datetime.datetime] | None = None
        self.agenda = Agenda()
        self._tela = None
        self._capturando = None

        r.geometry(f"{E.px(LARGURA)}x{E.px(ALTURA)}")
        self.casca = tk.Frame(r, bg=E.FUNDO)
        self.casca.pack(fill="both", expand=True, padx=1, pady=1)
        self._barra()
        self.corpo = tk.Frame(self.casca, bg=E.FUNDO)
        self.corpo.pack(fill="both", expand=True)
        self._rodape()

        self.telas: dict[str, tk.Frame] = {}
        self.ir("inicio")
        self._posicionar()

        self.bandeja = Bandeja()
        self.bandeja.iniciar()
        self.motor = Motor()
        self.motor.iniciar()
        self.motor.aplicar(AT.guardados(self.cfg))

        r.bind("<Key>", self._tecla_janela)
        r.protocol("WM_DELETE_WINDOW", self.esconder)
        if escondida and self.bandeja.disponivel:     # sem bandeja nao ha como achar a janela
            r.withdraw()
        elif escondida:
            self._ja_mostrou = True
            moldura.fixar_barra_de_tarefas(r)
        self._agenda_t = 0
        r.after(50, self._ciclo)

    # == barra, rodape ===================================================
    def _barra(self):
        b = tk.Frame(self.casca, bg=E.FUNDO_FUNDO, height=E.px(34))
        b.pack(fill="x")
        b.pack_propagate(False)
        self._logo = tk.Label(b, image=E.icone("marca", E.px(16), E.ACENTO), bg=E.FUNDO_FUNDO)
        self._logo.pack(side="left", padx=(E.px(10), E.px(6)))
        tit = tk.Label(b, text="Ventilador", bg=E.FUNDO_FUNDO, fg=E.TEXTO_2, font=E.fonte(10, "semibold"))
        tit.pack(side="left")
        self.b_fechar = BotaoBarra(b, "fechar", self.esconder, largura=40, ao_segurar=self.sair,
                                   dica="Fechar\nclique: esconde na bandeja\nsegurar: sai")
        self.b_fechar.pack(side="right")
        BotaoBarra(b, "minimizar", lambda: moldura.minimizar(self.raiz), dica="Minimizar").pack(side="right")
        self.b_opcoes = BotaoBarra(b, "opcoes", lambda: self._alternar_tela("opcoes"), dica="Opções")
        self.b_opcoes.pack(side="right")
        self.b_agenda = BotaoBarra(b, "agenda", lambda: self._alternar_tela("agenda"), dica="Agenda")
        self.b_agenda.pack(side="right")
        arr = moldura.Arrasto(self.raiz)
        for w in (b, tit, self._logo):
            arr.ligar(w)
            w.bind("<ButtonRelease-1>", lambda _e=None: self._guardar_posicao(), add="+")

    def _rodape(self):
        f = tk.Frame(self.casca, bg=E.FUNDO)
        f.pack(fill="x", side="bottom", pady=(0, E.px(8)))
        self._ind = tk.Label(f, bg=E.FUNDO)
        self._ind.pack(side="left", padx=(E.px(MARGEM), E.px(4)))
        self._ind_txt = tk.Label(f, bg=E.FUNDO, fg=E.TEXTO_2, font=E.fonte(9))
        self._ind_txt.pack(side="left")
        self._pintar_indicador()

    def _pintar_indicador(self):
        cor = {"conectado": E.VERDE, "sem_bluetooth": E.ERRO}.get(self.estado, E.APAGADO)
        self._ind.config(image=E.icone("bluetooth", E.px(14), cor))
        self._ind_txt.config(text=ESTADOS.get(self.estado, self.estado))

    # == telas =============================================================
    def _alternar_tela(self, nome):
        self.ir("inicio" if self._tela == nome else nome)

    def ir(self, nome: str, **kw):
        """Troca de tela. Principal e montada uma vez; as outras a cada visita
        (sao listas/editores que mudam)."""
        self._capturando = None
        congelar(self.raiz, True)
        try:
            if self._tela and self._tela in self.telas:
                t = self.telas[self._tela]
                t.pack_forget()
                if self._tela != "inicio":
                    t.destroy()
                    del self.telas[self._tela]
            if nome not in self.telas:
                t = tk.Frame(self.corpo, bg=E.FUNDO)
                getattr(self, "_tela_" + nome)(t, **kw)
                self.telas[nome] = t
            self.telas[nome].pack(fill="both", expand=True, padx=E.px(MARGEM), pady=(E.px(10), E.px(6)))
            self._tela = nome
            self.b_agenda.acender(nome.startswith("agenda"))
            self.b_opcoes.acender(nome == "opcoes")
            self._medir()
        finally:
            congelar(self.raiz, False)

    def _medir(self):
        """Paineis que seguem o conteudo ficam na altura certa (o <Configure>
        do conteudo nao chega quando a tela e montada escondida). A JANELA
        nao muda de tamanho."""
        self.raiz.update_idletasks()
        Painel.medir_todos(self.corpo)

    def _titulo_tela(self, pai, texto, voltar_para="inicio"):
        f = tk.Frame(pai, bg=E.FUNDO)
        f.pack(fill="x", pady=(0, E.px(8)))
        Botao(f, icone="voltar", ao_clicar=lambda: self.ir(voltar_para), largura=32, altura=32,
              raio=8, fundo=E.FUNDO, cor=E.FUNDO, lado_icone=16, dica="Voltar (Esc)").pack(side="left")
        tk.Label(f, text=texto, bg=E.FUNDO, fg=E.TEXTO, font=E.fonte(12, "semibold")).pack(
            side="left", padx=E.px(6))
        self._voltar_para = voltar_para
        return f

    def _cabeca_painel(self, painel, texto, legenda=None):
        f = tk.Frame(painel.dentro, bg=E.CAMADA_1)
        f.pack(fill="x")
        tk.Label(f, text=texto, bg=E.CAMADA_1, fg=E.TEXTO, font=E.fonte(10.5, "semibold")).pack(side="left")
        if legenda:
            tk.Label(f, text=legenda, bg=E.CAMADA_1, fg=E.TEXTO_2, font=E.fonte(9)).pack(
                side="left", padx=E.px(6))
        return f

    # -- principal --------------------------------------------------------------
    # Janela FIXA 5:4 (pedido dele, 10/out/2026): duas colunas. Esquerda =
    # controle (velocidade + timer) ou, sem conexao, a dica do que fazer;
    # direita = rotinas (lista que rola).
    def _duas_colunas(self, t, esq=COL_ESQ):
        t.grid_columnconfigure(0, minsize=E.px(esq), weight=0)
        t.grid_columnconfigure(1, weight=1)
        t.grid_rowconfigure(0, weight=1)
        a = tk.Frame(t, bg=E.FUNDO, width=E.px(esq))
        a.grid(row=0, column=0, sticky="nsew")
        a.pack_propagate(False)
        a.grid_propagate(False)
        b = tk.Frame(t, bg=E.FUNDO)
        b.grid(row=0, column=1, sticky="nsew", padx=(E.px(10), 0))
        return a, b

    def _tela_inicio(self, t):
        esq, dir_ = self._duas_colunas(t)
        # controles
        self.f_controles = tk.Frame(esq, bg=E.FUNDO)
        self.f_controles.pack(fill="both", expand=True)
        self._p_vel = p = Painel(self.f_controles)
        p.pack(fill="x")
        self._cabeca_painel(p, "Velocidade")
        linha = tk.Frame(p.dentro, bg=E.CAMADA_1)
        linha.pack(fill="x", pady=(E.px(10), 0))
        self.b_vel = [None] * 4
        for v in (1, 2, 3):
            b = Botao(linha, texto=str(v), ao_clicar=lambda v=v: self.pedir_velocidade(v), largura=60,
                      altura=70, raio=12, fundo=E.CAMADA_1, tam=17, dica=f"Velocidade {v} ({v})")
            b.pack(side="left", expand=True, fill="x", padx=(0 if v == 1 else E.px(6), 0))
            self.b_vel[v] = b
        b = Botao(p.dentro, texto="Desligar", icone="desligar", ao_clicar=lambda: self.pedir_velocidade(0),
                  largura=190, altura=46, raio=10, fundo=E.CAMADA_1, tam=10.5, lado_icone=16,
                  dica="Desligar (0)")
        b.pack(fill="x", pady=(E.px(6), 0))
        self.b_vel[0] = b

        p = Painel(self.f_controles)
        p.pack(fill="x", pady=(E.px(10), 0))
        cab = self._cabeca_painel(p, "Timer")
        self.l_timer = tk.Label(cab, text="", bg=E.CAMADA_1, fg=E.TEXTO_2, font=E.fonte(9))
        self.l_timer.pack(side="left", padx=E.px(6))
        linha = tk.Frame(p.dentro, bg=E.CAMADA_1)
        linha.pack(fill="x", pady=(E.px(10), 0))
        self.p_timer = Passo(linha, self.cfg["timer_minutos"], 15, 720, 15, fmt_min,
                             self._mudou_timer, passos=TIMER_PASSOS, largura_texto=48)
        self.p_timer.pack(side="left")
        self.b_timer = Botao(linha, texto="Iniciar", ao_clicar=self._timer_botao, largura=80, altura=32,
                             raio=8, fundo=E.CAMADA_1, tam=10)
        self.b_timer.pack(side="right")

        # dica de conexao: ocupa a coluna dos controles quando nao ha conexao
        self.p_dica = Painel(esq, borda=E.misturar(E.ALERTA, E.CAMADA_1, 0.45), encher=True)
        self.l_dica_tit = tk.Label(self.p_dica.dentro, bg=E.CAMADA_1, fg=E.ALERTA, anchor="w", justify="left",
                                   font=E.fonte(10.5, "semibold"), wraplength=E.px(COL_ESQ - 30))
        self.l_dica_tit.pack(fill="x")
        self.l_dica_txt = tk.Label(self.p_dica.dentro, bg=E.CAMADA_1, fg=E.TEXTO_2, anchor="w",
                                   justify="left", font=E.fonte(9.5), wraplength=E.px(COL_ESQ - 30))
        self.l_dica_txt.pack(fill="x", pady=(E.px(6), 0))
        self.b_dica = Botao(self.p_dica.dentro, texto="Procurar agora", ao_clicar=self._dica_botao,
                            largura=190, altura=34, raio=8, fundo=E.CAMADA_1, tam=10)
        self.b_dica.pack(side="bottom", fill="x")
        self._dica = None
        self._dica_visivel = False

        # rotinas
        p = Painel(dir_, encher=True)
        p.pack(fill="both", expand=True)
        cab = self._cabeca_painel(p, "Rotinas")
        Botao(cab, icone="mais", ao_clicar=lambda: self.ir("rotina", rid=None), largura=28, altura=28,
              raio=8, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=14, dica="Nova rotina").pack(side="right")
        self.rol_rotinas = Rolagem(p.dentro)
        self.rol_rotinas.pack(fill="both", expand=True, pady=(E.px(4), 0))
        self.f_rotinas = self.rol_rotinas.dentro
        self._linhas_rot = {}
        self._montar_rotinas()
        self._pintar_velocidade(0)
        self._pintar_timer()

    def _montar_rotinas(self):
        for w in self.f_rotinas.winfo_children():
            w.destroy()
        self.b_rot = {}
        self.l_rot = {}
        if not self.cfg["rotinas"]:
            tk.Label(self.f_rotinas, text="Nenhuma rotina. Use o + para criar.", bg=E.CAMADA_1,
                     fg=E.TEXTO_2, font=E.fonte(9.5), anchor="w").pack(fill="x", pady=(E.px(8), 0))
        self._linhas_rot = {}
        for rot in self.cfg["rotinas"]:
            f = tk.Frame(self.f_rotinas, bg=E.CAMADA_1)
            f.pack(fill="x", pady=(E.px(6), 0))
            self._linhas_rot[rot["id"]] = f
            b = Botao(f, icone="tocar", ao_clicar=lambda i=rot["id"]: self._rotina_botao(i), largura=36,
                      altura=36, raio=10, fundo=E.CAMADA_1, lado_icone=14, dica="Rodar no ventilador")
            b.pack(side="right")
            Botao(f, icone="editar", ao_clicar=lambda i=rot["id"]: self.ir("rotina", rid=i), largura=32,
                  altura=36, raio=10, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=14,
                  dica="Editar").pack(side="right", padx=(0, E.px(2)))
            txt = tk.Frame(f, bg=E.CAMADA_1)
            txt.pack(side="left", fill="x", expand=True)
            nome = tk.Label(txt, text=rot["nome"], bg=E.CAMADA_1, fg=E.TEXTO, font=E.fonte(10.5),
                            anchor="w", justify="left")
            nome.pack(fill="x")
            leg = tk.Label(txt, text=resumo_passos(rot["passos"]), bg=E.CAMADA_1, fg=E.TEXTO_2,
                           font=E.fonte(9), anchor="w", justify="left")
            leg.pack(fill="x")
            quebrar(txt, nome, leg)
            self.l_rot[rot["id"]] = leg
            self.b_rot[rot["id"]] = b
        self.rol_rotinas.atualizar()
        self._pintar_rotinas()

    # -- editor de rotina ---------------------------------------------------------
    def _tela_rotina(self, t, rid=None):
        rot = self.cfg.rotina(rid) if rid else None
        self._ed = {"id": rid, "nome": rot["nome"] if rot else "Nova rotina",
                    "passos": [list(p) for p in (rot["passos"] if rot else [[2, 60]])]}
        self._titulo_tela(t, "Rotina")
        corpo = tk.Frame(t, bg=E.FUNDO)
        corpo.pack(fill="both", expand=True)
        dir_, esq = self._duas_colunas(corpo, esq=COL_DIR_EDITOR)   # nome a direita, passos a esquerda (mais largo)
        dir_.grid_configure(column=1, padx=(E.px(10), 0))
        esq.grid_configure(column=0, padx=0)
        corpo.grid_columnconfigure(0, weight=1, minsize=0)
        corpo.grid_columnconfigure(1, weight=0, minsize=E.px(COL_DIR_EDITOR))
        p = Painel(esq, encher=True)
        p.pack(fill="both", expand=True)
        cab = self._cabeca_painel(p, "Passos", "rodam em ordem")
        Botao(cab, icone="mais", ao_clicar=self._passo_novo, largura=28, altura=28, raio=8,
              fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=14, dica="Novo passo").pack(side="right")
        self.rol_passos = Rolagem(p.dentro)
        self.rol_passos.pack(fill="both", expand=True)
        self.f_passos = self.rol_passos.dentro
        self._montar_passos()
        p = Painel(dir_)
        p.pack(fill="x")
        self._cabeca_painel(p, "Nome")
        self.e_nome = tk.Entry(p.dentro, bg=E.CAMADA_2, fg=E.TEXTO, insertbackground=E.TEXTO,
                               relief="flat", font=E.fonte(11), highlightthickness=1,
                               highlightbackground=E.BORDA_1, highlightcolor=E.FOCO)
        self.e_nome.insert(0, self._ed["nome"])
        self.e_nome.pack(fill="x", pady=(E.px(8), 0), ipady=E.px(5))
        Botao(dir_, texto="Salvar", ao_clicar=self._rotina_salvar, largura=150, altura=38,
              fundo=E.FUNDO, tam=10.5).pack(side="bottom", fill="x")
        if rid:
            Botao(dir_, texto="Excluir", icone="lixo", ao_clicar=self._rotina_excluir, largura=150,
                  altura=38, fundo=E.FUNDO, cor=E.FUNDO, cor_texto=E.ERRO, tam=10.5,
                  lado_icone=14).pack(side="bottom", fill="x", pady=(0, E.px(6)))

    def _montar_passos(self):
        for w in self.f_passos.winfo_children():
            w.destroy()
        for n, passo in enumerate(self._ed["passos"]):
            f = tk.Frame(self.f_passos, bg=E.CAMADA_1)
            f.pack(fill="x", pady=(E.px(8), 0))
            sel = []
            for v in range(4):
                b = Botao(f, texto="" if v == 0 else str(v), icone="desligar" if v == 0 else None,
                          largura=28, altura=30, raio=8, fundo=E.CAMADA_1, tam=10, lado_icone=13)
                b.ao_clicar = (lambda n=n, v=v, sel=sel: self._passo_vel(n, v, sel))
                b.definir(selecionado=(passo[0] == v), ms=0)
                b.pack(side="left", padx=(0, E.px(3)))
                sel.append(b)
            Botao(f, icone="lixo", ao_clicar=lambda n=n: self._passo_tirar(n), largura=28, altura=30,
                  raio=8, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=13,
                  dica="Tirar este passo").pack(side="right")
            Passo(f, passo[1], 5, 720, 5, fmt_min, lambda v, n=n: self._passo_min(n, v),
                  passos=PASSO_MIN, largura_texto=50).pack(side="right", padx=(0, E.px(2)))
        self.rol_passos.atualizar()

    def _passo_vel(self, n, v, sel):
        self._ed["passos"][n][0] = v
        for i, b in enumerate(sel):
            b.definir(selecionado=(i == v))

    def _passo_min(self, n, v):
        self._ed["passos"][n][1] = v

    def _passo_novo(self):
        if len(self._ed["passos"]) >= 20:
            return
        ult = self._ed["passos"][-1] if self._ed["passos"] else [2, 60]
        self._ed["passos"].append(list(ult))
        self._montar_passos()
        linhas = self.f_passos.winfo_children()
        if linhas:
            self.rol_passos.mostrar(linhas[-1])       # o passo novo fica a vista

    def _passo_tirar(self, n):
        if len(self._ed["passos"]) <= 1:
            return
        del self._ed["passos"][n]
        self._montar_passos()

    def _rotina_salvar(self):
        nome = self.e_nome.get().strip() or "Rotina"
        rid = self._ed["id"]
        if rid:
            rot = self.cfg.rotina(rid)
            rot["nome"], rot["passos"] = nome, self._ed["passos"]
        else:
            rid = novo_id()
            self.cfg["rotinas"].append({"id": rid, "nome": nome, "passos": self._ed["passos"]})
        self.cfg.gravar()
        self._montar_rotinas()
        self.ir("inicio")
        if rid in self._linhas_rot:                  # a rotina salva fica a vista
            self.rol_rotinas.mostrar(self._linhas_rot[rid])

    def _rotina_excluir(self):
        self.cfg["rotinas"] = [r for r in self.cfg["rotinas"] if r["id"] != self._ed["id"]]
        self.cfg.gravar()
        self._montar_rotinas()
        self.ir("inicio")

    # -- agenda ---------------------------------------------------------------------
    def _rotulo_acao(self, acao: str) -> str:
        if acao == "v0":
            return "Desligar"
        if acao in ("v1", "v2", "v3"):
            return f"Velocidade {acao[1]}"
        if acao.startswith("rotina:"):
            rot = self.cfg.rotina(acao[7:])
            return rot["nome"] if rot else "(rotina apagada)"
        return acao

    def _tela_agenda(self, t):
        self._titulo_tela(t, "Agenda")
        p = Painel(t, encher=True)
        p.pack(fill="both", expand=True)
        cab = self._cabeca_painel(p, "Horários", "o PC precisa estar ligado")
        Botao(cab, icone="mais", ao_clicar=lambda: self.ir("agenda_item", aid=None), largura=28, altura=28,
              raio=8, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=14, dica="Novo horário").pack(side="right")
        rol = self.rol_agenda = Rolagem(p.dentro)
        rol.pack(fill="both", expand=True)
        self._linhas_ag = {}
        itens = sorted(self.cfg["agenda"], key=lambda i: i["hora"])
        if not itens:
            tk.Label(rol.dentro, text="Nenhum horário ainda. Use o + para criar.", bg=E.CAMADA_1,
                     fg=E.TEXTO_2, font=E.fonte(9.5), anchor="w").pack(fill="x", pady=(E.px(8), 0))
        for it in itens:
            f = tk.Frame(rol.dentro, bg=E.CAMADA_1)
            f.pack(fill="x", pady=(E.px(8), 0))
            self._linhas_ag[it["id"]] = f
            tk.Label(f, text=it["hora"], bg=E.CAMADA_1, fg=E.TEXTO, font=E.fonte(14, "semibold")).pack(side="left")
            Chave(f, it.get("ligado", True), lambda v, it=it: self._agenda_ligar(it, v)).pack(side="right")
            Botao(f, icone="editar", ao_clicar=lambda i=it["id"]: self.ir("agenda_item", aid=i), largura=32,
                  altura=32, raio=8, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=14,
                  dica="Editar").pack(side="right", padx=(0, E.px(6)))
            tx = tk.Frame(f, bg=E.CAMADA_1)
            tx.pack(side="left", padx=E.px(12), fill="x", expand=True)
            a = tk.Label(tx, text=self._rotulo_acao(it["acao"]), bg=E.CAMADA_1, fg=E.TEXTO, font=E.fonte(10),
                         anchor="w", justify="left")
            a.pack(fill="x")
            d = tk.Label(tx, text=dias_texto(it["dias"]), bg=E.CAMADA_1, fg=E.TEXTO_2, font=E.fonte(9),
                         anchor="w", justify="left")
            d.pack(fill="x")
            quebrar(tx, a, d)

    def _agenda_ligar(self, it, v):
        it["ligado"] = v
        return self.cfg.gravar()

    def _tela_agenda_item(self, t, aid=None):
        it = next((i for i in self.cfg["agenda"] if i["id"] == aid), None)
        self._ai = dict(it) if it else {"id": None, "hora": "22:00", "dias": list(range(7)),
                                        "acao": "v0", "ligado": True}
        self._ai["dias"] = list(self._ai["dias"])
        self._titulo_tela(t, "Horário", voltar_para="agenda")
        corpo = tk.Frame(t, bg=E.FUNDO)
        corpo.pack(fill="both", expand=True)
        esq, dir_ = self._duas_colunas(corpo)
        p = Painel(esq)
        p.pack(fill="x")
        self._cabeca_painel(p, "Hora")
        h, m = (int(x) for x in self._ai["hora"].split(":"))
        self.p_h = Passo(p.dentro, h, 0, 23, 1, lambda v: f"{v:02d} h", lambda v: self._ai_hora(h=v),
                         largura_texto=60)
        self.p_h.pack(anchor="w", pady=(E.px(8), 0))
        self.p_m = Passo(p.dentro, m, 0, 55, 5, lambda v: f"{v:02d} min", lambda v: self._ai_hora(m=v),
                         largura_texto=60)
        self.p_m.pack(anchor="w", pady=(E.px(6), 0))
        p = Painel(esq)
        p.pack(fill="x", pady=(E.px(10), 0))
        self._cabeca_painel(p, "Fazer")
        self.b_acao = Botao(p.dentro, texto=self._rotulo_acao(self._ai["acao"]), icone="seta_baixo",
                            ao_clicar=self._ai_menu_acao, largura=190, altura=34, raio=8,
                            fundo=E.CAMADA_1, tam=10, peso="normal", lado_icone=14)
        self.b_acao.pack(fill="x", pady=(E.px(8), 0))
        p = Painel(dir_)
        p.pack(fill="x")
        self._cabeca_painel(p, "Dias")
        from .agenda import DIAS
        grade = tk.Frame(p.dentro, bg=E.CAMADA_1)
        grade.pack(fill="x", pady=(E.px(8), 0))
        for d, nome in enumerate(DIAS):
            b = Botao(grade, texto=nome, largura=48, altura=32, raio=8, fundo=E.CAMADA_1, tam=9.5, peso="normal")
            b.ao_clicar = (lambda d=d, b=b: self._ai_dia(d, b))
            b.definir(selecionado=d in self._ai["dias"], ms=0)
            b.grid(row=d // 4, column=d % 4, sticky="ew", padx=(0, E.px(4)), pady=(0, E.px(4)))
        for c in range(4):
            grade.grid_columnconfigure(c, weight=1)
        Botao(dir_, texto="Salvar", ao_clicar=self._ai_salvar, largura=150, altura=38, fundo=E.FUNDO,
              tam=10.5).pack(side="bottom", fill="x")
        if aid:
            Botao(dir_, texto="Excluir", icone="lixo", ao_clicar=self._ai_excluir, largura=150, altura=38,
                  fundo=E.FUNDO, cor=E.FUNDO, cor_texto=E.ERRO, tam=10.5,
                  lado_icone=14).pack(side="bottom", fill="x", pady=(0, E.px(6)))

    def _ai_hora(self, h=None, m=None):
        hh, mm = (int(x) for x in self._ai["hora"].split(":"))
        self._ai["hora"] = f"{hh if h is None else h:02d}:{mm if m is None else m:02d}"

    def _ai_dia(self, d, b):
        dias = self._ai["dias"]
        if d in dias:
            if len(dias) == 1:
                return
            dias.remove(d)
        else:
            dias.append(d)
        b.definir(selecionado=d in dias)

    def _opcoes_acao(self, incluir_nada=False):
        ops = [("Não fazer nada", "nada")] if incluir_nada else []
        ops += [("Desligar", "v0"), ("Velocidade 1", "v1"), ("Velocidade 2", "v2"), ("Velocidade 3", "v3")]
        ops += [(r["nome"], "rotina:" + r["id"]) for r in self.cfg["rotinas"]]
        return ops

    def _ai_menu_acao(self):
        def escolher(a):
            self._ai["acao"] = a
            self.b_acao.definir(texto=self._rotulo_acao(a))
        Menu(self.b_acao, [(n, (lambda a=a: escolher(a))) for n, a in self._opcoes_acao()],
             marcado=self._rotulo_acao(self._ai["acao"]), alinhar="direita")

    def _ai_salvar(self):
        if self._ai["id"]:
            for i, it in enumerate(self.cfg["agenda"]):
                if it["id"] == self._ai["id"]:
                    self.cfg["agenda"][i] = self._ai
        else:
            self._ai["id"] = novo_id()
            self.cfg["agenda"].append(self._ai)
        self.cfg.gravar()
        aid = self._ai["id"]
        self.ir("agenda")
        if aid in self._linhas_ag:                   # o horario salvo fica a vista
            self.rol_agenda.mostrar(self._linhas_ag[aid])

    def _ai_excluir(self):
        self.cfg["agenda"] = [i for i in self.cfg["agenda"] if i["id"] != self._ai["id"]]
        self.cfg.gravar()
        self.ir("agenda")

    # -- opcoes ------------------------------------------------------------------------
    def _linha(self, pai, nome, legenda):
        f = tk.Frame(pai, bg=E.CAMADA_1)
        f.pack(fill="x", pady=(E.px(10), 0))
        tx = tk.Frame(f, bg=E.CAMADA_1)
        tx.pack(side="left", fill="x", expand=True)
        tk.Label(tx, text=nome, bg=E.CAMADA_1, fg=E.TEXTO, font=E.fonte(10.5), anchor="w").pack(fill="x")
        if legenda:
            tk.Label(tx, text=legenda, bg=E.CAMADA_1, fg=E.TEXTO_2, font=E.fonte(9), anchor="w",
                     justify="left", wraplength=E.px(250)).pack(fill="x")
        return f

    def _tela_opcoes(self, t):
        """Uma coluna larga que rola: Programa, depois Atalhos."""
        self._titulo_tela(t, "Opções")
        rol = self.rol_opcoes = Rolagem(t, fundo=E.FUNDO)
        rol.pack(fill="both", expand=True)
        area = rol.dentro
        p = Painel(area)
        p.pack(fill="x")
        self._cabeca_painel(p, "Programa")
        f = self._f_win = self._linha(p.dentro, "Iniciar com o Windows", "abre escondido na bandeja")
        win = inicio_windows.ativo()
        Chave(f, win, self._opc_windows).pack(side="right")
        # sub-opcao: so aparece com a de origem ligada (padrao scrcpy-f)
        self.f_rapido = tk.Frame(p.dentro, bg=E.CAMADA_1)
        f = self._linha(self.f_rapido, "Iniciar mais rápido", "junto com o login; pede o administrador uma vez")
        f.pack_configure(padx=(E.px(16), 0))
        self.ch_rapido = Chave(f, win and inicio_windows.rapido(), self._opc_rapido)
        self.ch_rapido.pack(side="right")
        if win:
            self.f_rapido.pack(fill="x")
        f = self._linha(p.dentro, "Iniciar minimizado", "abre direto na bandeja")
        Chave(f, bool(self.cfg.opcoes.get("comecar_na_bandeja")), self._opc_minimizado).pack(side="right")
        f = self._linha(p.dentro, "Ao conectar", "o que fazer assim que o programa abre")
        self.b_ao_abrir = Botao(f, texto=self._rotulo_ao_abrir(), icone="seta_baixo",
                                ao_clicar=self._opc_menu_ao_abrir, largura=150, altura=32, raio=8,
                                fundo=E.CAMADA_1, tam=9.5, peso="normal", lado_icone=12)
        self.b_ao_abrir.pack(side="right")
        f = self._linha(p.dentro, "Ventilador", "libera para o app do celular")
        solto = self.estado == "solto"
        self.b_soltar = Botao(f, texto="Reconectar" if solto else "Soltar", ao_clicar=self._opc_soltar,
                              largura=150, altura=32, raio=8, fundo=E.CAMADA_1, tam=10)
        self.b_soltar.pack(side="right")

        p = Painel(area)
        p.pack(fill="x", pady=(E.px(10), 0))
        cab = self._cabeca_painel(p, "Atalhos", "Ctrl, Alt ou Win + uma tecla")
        self.b_novo_atalho = Botao(cab, icone="mais", ao_clicar=self._atalho_menu, largura=28, altura=28,
                                   raio=8, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=14, dica="Novo atalho")
        self.b_novo_atalho.pack(side="right")
        self.f_atalhos = tk.Frame(p.dentro, bg=E.CAMADA_1)
        self.f_atalhos.pack(fill="x")
        self._montar_atalhos()
        tk.Label(area, text=f"Ventilador Arno {__version__} · relatórios em relatorios\\", bg=E.FUNDO,
                 fg=E.APAGADO, font=E.fonte(8.5)).pack(anchor="w", pady=(E.px(8), 0))

    def _rotulo_ao_abrir(self):
        a = self.cfg.opcoes.get("ao_abrir", "nada")
        return "Não fazer nada" if a == "nada" else self._rotulo_acao(a)

    def _opc_menu_ao_abrir(self):
        def escolher(a):
            self.cfg.opcoes["ao_abrir"] = a
            self.cfg.gravar()
            self.b_ao_abrir.definir(texto=self._rotulo_ao_abrir())
        Menu(self.b_ao_abrir, [(n, (lambda a=a: escolher(a))) for n, a in self._opcoes_acao(True)],
             marcado=self._rotulo_ao_abrir(), alinhar="direita")

    def _opc_windows(self, v):
        ok = inicio_windows.definir(v)
        if ok:
            self.cfg.opcoes["iniciar_com_windows"] = v
            self.cfg.gravar()
            if v:
                self.f_rapido.pack(fill="x", after=self._f_win)
                self.ch_rapido.definir(inicio_windows.rapido())
            else:
                self.f_rapido.pack_forget()
                self.ch_rapido.definir(False)
            self._medir()
        return ok

    def _opc_minimizado(self, v):
        self.cfg.opcoes["comecar_na_bandeja"] = v
        return self.cfg.gravar()

    def _opc_rapido(self, v):
        ok = inicio_windows.definir_rapido(v)
        log.info("iniciar mais rapido %s: %s", v, "ok" if ok else "falhou")
        return ok

    def _opc_soltar(self):
        if self.estado == "solto":
            self.cx.retomar()
            self.b_soltar.definir(texto="Soltar")
        else:
            self.cx.soltar()
            self.b_soltar.definir(texto="Reconectar")

    def _montar_atalhos(self):
        for w in self.f_atalhos.winfo_children():
            w.destroy()
        falhas = self.motor.falhas() if hasattr(self, "motor") else set()
        lista = AT.em_ordem(self.cfg)
        self._linhas_atalho = {}
        if not lista:
            tk.Label(self.f_atalhos, text="Nenhum atalho. Use o + para criar.", bg=E.CAMADA_1,
                     fg=E.TEXTO_2, font=E.fonte(9.5), anchor="w").pack(fill="x", pady=(E.px(8), 0))
        for acao, teclas in lista:
            f = tk.Frame(self.f_atalhos, bg=E.CAMADA_1)
            f.pack(fill="x", pady=(E.px(8), 0))
            tk.Label(f, text=AT.rotulo(acao), bg=E.CAMADA_1, fg=E.TEXTO, font=E.fonte(10),
                     anchor="w").pack(side="left")
            Botao(f, icone="lixo", ao_clicar=lambda a=acao: self._atalho_tirar(a), largura=28, altura=30,
                  raio=8, fundo=E.CAMADA_1, cor=E.CAMADA_1, lado_icone=13, dica="Tirar").pack(side="right")
            b = Botao(f, texto=teclas or "definir", largura=170, altura=30, raio=8, fundo=E.CAMADA_1,
                      tam=9.5, peso="normal",
                      cor_texto=E.ERRO if acao in falhas else (E.TEXTO if teclas else E.TEXTO_2),
                      dica="Clique e aperte as teclas" if acao not in falhas else
                      "O Windows recusou: outro programa já usa")
            b.ao_clicar = (lambda a=acao, b=b: self._atalho_capturar(a, b))
            b.pack(side="right", padx=(0, E.px(4)))
            self._linhas_atalho[acao] = (f, b)
        if self._tela == "opcoes":
            self._medir()

    def _atalho_menu(self):
        livres = AT.livres(self.cfg)
        if not livres:
            return

        def novo(a):
            # (10/out, bug relatado por ele: "clico no + e nada acontece") a linha
            # nova nascia abaixo da dobra e esperando outro clique. Agora ela fica
            # a vista e ja pede as teclas.
            self.cfg.atalhos[a] = ""
            self._montar_atalhos()
            f, b = self._linhas_atalho[a]
            self.rol_opcoes.mostrar(f)
            self.raiz.after(60, lambda: self._atalho_capturar(a, b))
        Menu(self.b_novo_atalho, [(AT.rotulo(a), (lambda a=a: novo(a))) for a in livres], alinhar="direita")

    def _atalho_tirar(self, a):
        self.cfg.atalhos.pop(a, None)
        self.cfg.gravar()
        self.motor.aplicar(AT.guardados(self.cfg))
        self._montar_atalhos()

    def _atalho_capturar(self, acao, b):
        if self._capturando and self._capturando[1] is b:
            return
        self._capturando = (acao, b, set())
        b.definir(texto="aperte as teclas…")
        log.info("capturando teclas para %s", acao)
        # (10/out, bug dele: "nao consigo definir as teclas") o teclado precisa
        # voltar de verdade para a janela; Espaco/Enter do botao viram tecla do
        # atalho; o "perdeu o foco" so cancela depois que a janela assentou
        C.ativar(self.raiz, b)
        b.bind("<KeyPress>", self._cap_tecla)
        b.bind("<KeyRelease>", self._cap_solta)
        b.bind("<space>", self._cap_tecla)
        b.bind("<Return>", self._cap_tecla)
        self.raiz.after(300, lambda: self._capturando and self._capturando[1] is b and
                        b.bind("<FocusOut>", lambda _e=None: self._cap_fim(None), add="+"))

    def _cap_tecla(self, e):
        if not self._capturando:
            return
        acao, b, presos = self._capturando
        if e.keysym == "Escape":
            self._cap_fim(None)
            return "break"
        if AT.e_modificador(e.keysym):
            presos.add(e.keysym)
            b.definir(texto=AT.escrever(presos) + "+…")
            return "break"
        tecla = AT.tecla_fisica(e.keysym, getattr(e, "keycode", 0) or 0)
        teclas = AT.escrever(presos, tecla)
        motivo = AT.porque_nao(presos, tecla)
        dono = AT.quem_usa(self.cfg, teclas, menos=acao)
        if motivo or dono:
            # o MOTIVO aparece no proprio botao (antes: recusa muda, so texto vermelho)
            curto = ("use Ctrl/Alt/Win + tecla" if "Falta Ctrl" in motivo or "Falta a tecla" in motivo
                     else f"já usado: {AT.rotulo(dono)}" if dono else "tecla não aceita")
            b.cor_texto = E.ERRO
            b.definir(texto=curto)
            log.info("atalho recusado: %s (%s)", teclas, motivo or "ja usado")

            def voltar():
                if self._capturando and self._capturando[1] is b:
                    b.cor_texto = E.TEXTO
                    b.definir(texto="aperte as teclas…")
            self.raiz.after(1600, voltar)
            return "break"
        self._cap_fim(teclas)
        return "break"

    def _cap_solta(self, e):
        if self._capturando and AT.e_modificador(e.keysym):
            self._capturando[2].discard(e.keysym)
        return "break"

    def _cap_fim(self, teclas):
        if not self._capturando:
            return
        acao, b, _ = self._capturando
        self._capturando = None
        log.info("captura de %s: %s", acao, teclas or "cancelada")
        for seq in ("<KeyPress>", "<KeyRelease>", "<space>", "<Return>"):
            b.unbind(seq)
        if teclas:
            self.cfg.atalhos[acao] = teclas
            self.cfg.gravar()
            self.motor.aplicar(AT.guardados(self.cfg))
            self.raiz.after(300, self._montar_atalhos)
        else:
            self.raiz.after(10, self._montar_atalhos)

    # == acoes no ventilador ==================================================
    def pedir_velocidade(self, v: int, origem="tela") -> bool:
        antes = self.vel
        self._pintar_velocidade(v)
        if not self.cx.enviar(P.pacote_velocidade(v)):
            self._pintar_velocidade(antes)
            return False
        log.info("velocidade %s (%s)", v, origem)
        self.vel = v
        if v:
            self.cfg["ultima_velocidade"] = v
            self.gravar_depois()
        self._ignorar_status_ate = _agora_s() + 1.5
        self.timer_fim = None
        self.rotina_rodando = None
        self._pintar_timer()
        self._pintar_rotinas()
        self._pintar_bandeja()
        return True

    def _mudou_timer(self, v):
        self.cfg["timer_minutos"] = v
        self.gravar_depois()

    def gravar_depois(self):
        """Cliques seguidos gravam o config uma vez so (0,8 s depois do ultimo)."""
        if self._job_gravar:
            self.raiz.after_cancel(self._job_gravar)
        self._job_gravar = self.raiz.after(800, self._gravar_agora)

    def _gravar_agora(self):
        self._job_gravar = None
        self.cfg.gravar()

    def _timer_botao(self):
        if self.timer_fim:
            self.pedir_velocidade(self.vel or 0)
            return
        vel = self.vel or self.cfg["ultima_velocidade"]
        m = self.p_timer.valor
        if not self.cx.enviar(P.pacote_programa([(vel, m)])):
            return
        log.info("timer %s min na velocidade %s", m, vel)
        self.rotina_rodando = None
        self.timer_fim = datetime.datetime.now() + datetime.timedelta(minutes=m)
        self.vel = vel
        self._pintar_velocidade(vel)
        self._ignorar_status_ate = _agora_s() + 1.5
        self._pintar_timer()
        self._pintar_rotinas()

    def _rotina_botao(self, rid):
        if self.rotina_rodando and self.rotina_rodando[0] == rid:
            self.pedir_velocidade(0)
            return
        self.rodar_rotina(rid)

    def rodar_rotina(self, rid) -> bool:
        rot = self.cfg.rotina(rid)
        if not rot or not rot["passos"]:
            return False
        if not self.cx.enviar(P.pacote_programa([tuple(p) for p in rot["passos"]])):
            return False
        log.info("rotina %s", rot["nome"])
        fim = datetime.datetime.now() + datetime.timedelta(minutes=sum(m for _, m in rot["passos"]))
        self.rotina_rodando = (rid, fim)
        self.timer_fim = None
        v = rot["passos"][0][0]
        self.vel = v
        self._pintar_velocidade(v)
        self._ignorar_status_ate = _agora_s() + 1.5
        self._pintar_timer()
        self._pintar_rotinas()
        return True

    def executar(self, acao: str, origem: str):
        if acao in ("v0", "v1", "v2", "v3"):
            self.pedir_velocidade(int(acao[1]), origem)
        elif acao.startswith("rotina:"):
            self.rodar_rotina(acao[7:])

    # == dica de conexao ========================================================
    DICAS = {
        "bt_desligado": ("O Bluetooth do PC está desligado",
                         "Ligue em Configurações › Bluetooth e dispositivos. O programa conecta sozinho "
                         "assim que ligar.", "Abrir configurações"),
        "bt_ausente": ("Não achei o Bluetooth do PC",
                       "O PC precisa de Bluetooth 4.0 ou mais novo (um adaptador USB serve). Se ele tem, "
                       "confira se está ligado em Configurações › Bluetooth.", "Abrir configurações"),
        "bt_negado": ("O Windows bloqueou o Bluetooth",
                      "Libere em Configurações › Privacidade › Rádios.", "Abrir configurações"),
        "nao_achado": ("Não encontrei o ventilador",
                       "• Está na tomada e ligado?\n• Está perto do PC (mesmo cômodo)?\n"
                       "• O celular está conectado nele? Conectado, ele some para o PC: feche o app ou "
                       "desligue o Bluetooth do celular.", "Procurar agora"),
        "recusou": ("O ventilador não aceitou a conexão",
                    "Quase sempre é o celular conectado nele. Feche o app ou desligue o Bluetooth do "
                    "celular; o programa tenta de novo sozinho.", "Tentar agora"),
        "caiu": ("A conexão caiu",
                 "Reconectando sozinho. Se demorar: o ventilador foi desligado da tomada ou o celular "
                 "pegou a conexão.", "Tentar agora"),
        "aparelho_errado": ("Achei um aparelho que não é este ventilador",
                            "Ele tem \"FAN\" no nome mas não fala o protocolo da Arno. Deixe só o "
                            "ventilador ligado perto do PC.", "Procurar agora"),
    }

    def _pintar_dica(self):
        if not hasattr(self, "p_dica"):
            return
        d = self._dica if self.estado not in ("conectado", "solto") else None
        if d and self.l_dica_tit.cget("text") != self.DICAS.get(d, (d,))[0]:
            tit, txt, botao = self.DICAS.get(d, (d, "", "Procurar agora"))
            self.l_dica_tit.config(text=tit)
            self.l_dica_txt.config(text=txt)
            self.b_dica.definir(texto=botao, ms=0)
        if bool(d) != self._dica_visivel:
            # a dica ocupa o lugar dos controles (que sem conexao nao servem);
            # a janela nao muda de tamanho
            self._dica_visivel = bool(d)
            if d:
                self.f_controles.pack_forget()
                self.p_dica.pack(fill="both", expand=True)
            else:
                self.p_dica.pack_forget()
                self.f_controles.pack(fill="both", expand=True)
                self.l_dica_tit.config(text="")

    def _dica_botao(self):
        if self._dica and self._dica.startswith("bt_"):
            alvo = "ms-settings:privacy-radios" if self._dica == "bt_negado" else "ms-settings:bluetooth"
            try:
                os.startfile(alvo)
            except OSError as e:
                log.warning("nao abri %s: %s", alvo, e)
        self.cx.procurar_agora()

    # == pintura do estado =====================================================
    def _pintar_velocidade(self, v):
        ok = self.estado == "conectado"        # sem conexao nao ha estado real para mostrar
        for i, b in enumerate(getattr(self, "b_vel", [])):
            b.definir(selecionado=ok and i == v, habilitado=ok)

    def _pintar_timer(self):
        if not hasattr(self, "b_timer"):
            return
        if self.timer_fim:
            self.l_timer.config(text="desliga às " + self.timer_fim.strftime("%H:%M"))
            self.b_timer.definir(texto="Cancelar", selecionado=True, icone="")
        else:
            self.l_timer.config(text="")
            self.b_timer.definir(texto="Iniciar", selecionado=False, icone="")
        self.b_timer.definir(habilitado=self.estado == "conectado")

    def _pintar_rotinas(self):
        for rid, b in getattr(self, "b_rot", {}).items():
            rodando = bool(self.rotina_rodando and self.rotina_rodando[0] == rid)
            b.definir(selecionado=rodando, icone="parar" if rodando else "tocar",
                      habilitado=self.estado == "conectado")
            rot = self.cfg.rotina(rid)
            if rot:
                txt = (f"rodando · até {self.rotina_rodando[1]:%H:%M}" if rodando
                       else resumo_passos(rot["passos"]))
                self.l_rot[rid].config(text=txt, fg=E.ACENTO if rodando else E.TEXTO_2)

    def _pintar_bandeja(self):
        ligado = self.estado == "conectado" and self.vel > 0
        self.bandeja.definir_cor(E.ACENTO if ligado else None)
        if self.estado != "conectado":
            txt = ESTADOS.get(self.estado, "")
        else:
            txt = f"velocidade {self.vel}" if self.vel else "desligado"
        self.bandeja.definir_titulo(f"Ventilador: {txt}")

    # == laco ===================================================================
    def _ciclo(self):
        try:
            self._ciclo_dentro()
        except Exception:
            log.exception("erro no laco da janela")
        self.raiz.after(50, self._ciclo)

    def _ciclo_dentro(self):
        for ev in self.cx.eventos():
            if ev[0] == "estado":
                self.estado = ev[1]
                self._pintar_indicador()
                self._pintar_velocidade(self.vel)
                self._pintar_timer()
                self._pintar_rotinas()
                self._pintar_bandeja()
                if hasattr(self, "b_soltar") and self._tela == "opcoes":
                    self.b_soltar.definir(texto="Reconectar" if self.estado == "solto" else "Soltar")
                self._pintar_dica()
            elif ev[0] == "dica":
                self._dica = ev[1]
                self._pintar_dica()
            elif ev[0] == "aparelho":
                if self.cfg["endereco"] != ev[1]:
                    self.cfg["endereco"] = ev[1]
                    self.cfg.gravar()
                if not self._ao_abrir_feito:
                    self._ao_abrir_feito = True
                    a = self.cfg.opcoes.get("ao_abrir", "nada")
                    if a != "nada":
                        self.raiz.after(1200, lambda a=a: self.executar(a, "ao abrir"))
            elif ev[0] == "status":
                if _agora_s() >= self._ignorar_status_ate and ev[1]["velocidade"] != self.vel:
                    self.vel = ev[1]["velocidade"]
                    self._pintar_velocidade(self.vel)
                    self._pintar_bandeja()
        agora = datetime.datetime.now()
        if self.timer_fim and agora >= self.timer_fim:
            self.timer_fim = None
            self._pintar_timer()
        if self.rotina_rodando and agora >= self.rotina_rodando[1]:
            self.rotina_rodando = None
            self._pintar_rotinas()
        for p in self.bandeja.pedidos():
            if p == "mostrar":
                self.mostrar()
            elif p == "alternar":
                self.pedir_velocidade(0 if self.vel else self.cfg["ultima_velocidade"], "bandeja")
        for a in self.motor.pedidos():
            self._atalho(a)
        self._agenda_t += 1
        if self._agenda_t >= 100:            # ~5 s
            self._agenda_t = 0
            for it in self.agenda.vencidos(self.cfg["agenda"]):
                log.info("agenda %s: %s", it["hora"], it["acao"])
                self.executar(it["acao"], "agenda")
        if self._agenda_t % 10 == 0 and PEDIDO_MOSTRAR.exists():
            try:
                os.remove(PEDIDO_MOSTRAR)
            except OSError:
                pass
            self.mostrar()

    def _atalho(self, a):
        if a == "alternar":
            self.pedir_velocidade(0 if self.vel else self.cfg["ultima_velocidade"], "atalho")
        elif a in ("v1", "v2", "v3"):
            self.pedir_velocidade(int(a[1]), "atalho")
        elif a == "mais":
            self.pedir_velocidade(min(3, self.vel + 1), "atalho")
        elif a == "menos":
            self.pedir_velocidade(max(0, self.vel - 1), "atalho")
        elif a == "soltar":
            if self.estado == "solto":
                self.cx.retomar()
            else:
                self.cx.soltar()
        elif a == "mostrar_janela":
            if self.raiz.state() == "withdrawn":
                self.mostrar()
            else:
                self.esconder()

    def _tecla_janela(self, e):
        if self._capturando or isinstance(e.widget, tk.Entry):
            return
        if e.keysym == "Escape" and self._tela != "inicio":
            self.ir(getattr(self, "_voltar_para", "inicio") if self._tela != "agenda" and
                    self._tela != "opcoes" else "inicio")
        elif e.char in "0123" and e.char and self._tela == "inicio":
            self.pedir_velocidade(int(e.char), "teclado")

    # == janela ===================================================================
    def _posicionar(self):
        j = self.cfg["janela"]
        w, h = E.px(LARGURA), E.px(ALTURA)
        if j.get("x") is not None:
            # area de TODOS os monitores: monitor desligado/trocado nao deixa a janela perdida fora
            try:
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                vx, vy, vw, vh = gm(76), gm(77), gm(78), gm(79)
            except Exception:
                vx, vy, vw, vh = 0, 0, self.raiz.winfo_screenwidth(), self.raiz.winfo_screenheight()
            x = max(vx, min(j["x"], vx + vw - w))
            y = max(vy, min(j["y"], vy + vh - h))
            self.raiz.geometry(f"{w}x{h}+{x}+{y}")
        else:
            moldura.centralizar(self.raiz, w, h)

    def _guardar_posicao(self):
        self.cfg["janela"] = {"x": self.raiz.winfo_x(), "y": self.raiz.winfo_y()}
        self.cfg.gravar()

    def mostrar(self):
        r = self.raiz
        r.deiconify()
        if not self._ja_mostrou:
            self._ja_mostrou = True
            moldura.fixar_barra_de_tarefas(r)
        r.lift()
        r.focus_force()

    def esconder(self):
        if self.bandeja.disponivel:
            self.raiz.withdraw()
        else:
            moldura.minimizar(self.raiz)

    def sair(self):
        log.info("saindo")
        if self._job_gravar:                     # nada de config pendente perdido
            self.raiz.after_cancel(self._job_gravar)
            self._gravar_agora()
        try:
            self.motor.encerrar()
            self.bandeja.encerrar()
        finally:
            self.raiz.after(50, self.raiz.destroy)

    def rodar(self):
        self.raiz.mainloop()


def quebrar(caixa: tk.Widget, *rotulos: tk.Label):
    """Texto de largura livre (nome que ele digita) QUEBRA linha na largura da
    caixa em vez de ser cortado (gosto dele: nada de texto cortado)."""
    def ajustar(e):
        for r in rotulos:
            if int(r.cget("wraplength") or 0) != e.width:
                r.configure(wraplength=max(20, e.width))
    caixa.bind("<Configure>", ajustar, add="+")


def _agora_s() -> float:
    import time
    return time.monotonic()


def congelar(janela: tk.Tk, sim: bool):
    """WM_SETREDRAW na janela de cima: monta tudo e pinta de uma vez.

    So com a janela JA mapeada: WM_SETREDRAW mexe no WS_VISIBLE, e antes do
    1o mapeamento isso deixava o Tk achando que a janela estava escondida --
    o programa abria sempre "minimizado" (bug relatado por ele, 10/out/2026)."""
    if not janela.winfo_ismapped():
        return
    try:
        import ctypes
        h = ctypes.windll.user32.GetParent(janela.winfo_id())
        ctypes.windll.user32.SendMessageW(h, 0x000B, 0 if sim else 1, 0)
        if not sim:
            ctypes.windll.user32.RedrawWindow(h, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)
    except Exception:
        pass
