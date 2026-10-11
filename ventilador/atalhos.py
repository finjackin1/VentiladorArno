"""
Os atalhos de teclado: quais acoes existem e como elas ficam guardadas.

QUEM SABE DAS ACOES E ESTE MODULO
----------------------------------
Mesma divisao do `regras.py`: o `config.py` so guarda e devolve um
dicionario; quem sabe quais acoes existem, como cada uma se chama na tela e
em que ordem elas aparecem e este arquivo -- o mesmo que as usa. Acao nova
entra mexendo em um lugar so.

A janela nao aparece aqui, e a captura de tecla tambem nao. Este modulo e
so a lista e o formato; quem desenha e o `widgets.py`, quem liga na acao de
verdade e o `interface.py`, e quem escuta o teclado com o programa em
segundo plano e o `motor_atalhos.py`.

O FORMATO E TEXTO, NAO CODIGO DE TECLA
---------------------------------------
Um atalho e guardado como "Ctrl+Alt+L": legivel por quem abrir o
config.json na mao, e independente de como o sistema registra a combinacao.
Se o motor mudar, o arquivo de quem ja configurou continua valendo.

Os atalhos moram na chave "atalhos" do config.json, fora das `opcoes` -- que
sao so os liga/desliga das automacoes.
"""

from __future__ import annotations

# As acoes que podem receber atalho, na ordem em que aparecem na lista.
#
# (VentiladorArno, portado do LightWireless 10/out/2026.) "Sair do programa"
# fica de fora de proposito: atalho global que fecha o app e facil de apertar
# sem querer, e fechar ja tem gesto proprio (segurar o X).
ACOES: dict[str, str] = {
    "alternar": "Ligar / desligar",
    "v1": "Velocidade 1",
    "v2": "Velocidade 2",
    "v3": "Velocidade 3",
    "mais": "Mais forte",
    "menos": "Mais fraco",
    "mostrar_janela": "Mostrar / esconder a janela",
    "soltar": "Desconectar / reconectar",     # pedido dele 10/out/2026
}


# -- as teclas -------------------------------------------------------------
#
# O Tk chama cada tecla por um nome proprio (`keysym`). Estas tabelas
# traduzem esses nomes para o que aparece na tela e fica no arquivo -- e sao
# a UNICA parte do programa que precisa saber como o Tk chama as coisas.

MODIFICADORES = {
    "Control_L": "Ctrl", "Control_R": "Ctrl",
    "Alt_L": "Alt", "Alt_R": "Alt",
    "Shift_L": "Shift", "Shift_R": "Shift",
    "Win_L": "Win", "Win_R": "Win",
    "Super_L": "Win", "Super_R": "Win",
    "Meta_L": "Win", "Meta_R": "Win",
}

# Sempre nesta ordem, venham apertados na ordem que vierem. Assim a mesma
# combinacao tem uma escrita so -- se cada gravacao saisse numa ordem, duas
# iguais nao se reconheceriam e a conferencia de conflito falharia.
ORDEM = ("Ctrl", "Alt", "Shift", "Win")

# Nome amigavel para as teclas cujo `keysym` e feio ou obscuro.
#
# AS DE PONTUACAO VIRAM O PROPRIO CARACTERE, e nao um nome. O Tk chama a
# barra invertida de "backslash", e um nome desses nao diz nada para quem
# le a lista e nao serve para o motor achar a tecla no Windows -- foi
# exatamente isso que fez `Ctrl+Alt+\` ser aceito e nao funcionar
# (06/set/2026). Virando "\", o nome fica curto na tela E o motor consegue
# perguntar ao Windows qual tecla e essa no teclado que a pessoa usa.
APELIDOS = {
    "Prior": "PgUp",
    "Next": "PgDn",
    "Return": "Enter",
    "KP_Enter": "Enter",
    "BackSpace": "Backspace",
    "Delete": "Del",
    "space": "Espaco",
    "Left": "Esquerda",
    "Right": "Direita",
    "Up": "Cima",
    "Down": "Baixo",

    # pontuacao e simbolos
    "backslash": "\\",
    "slash": "/",
    "comma": ",",
    "period": ".",
    "semicolon": ";",
    "colon": ":",
    "apostrophe": "'",
    "quoteright": "'",
    "quoteleft": "`",
    "grave": "`",
    "bracketleft": "[",
    "bracketright": "]",
    "braceleft": "{",
    "braceright": "}",
    "minus": "-",
    "plus": "+",
    "equal": "=",
    "asterisk": "*",
    "numbersign": "#",
    "dollar": "$",
    "percent": "%",
    "ampersand": "&",
    "at": "@",
    "exclam": "!",
    "question": "?",
    "less": "<",
    "greater": ">",
    "bar": "|",
    "underscore": "_",
    "asciitilde": "~",
    "asciicircum": "^",
    "acute": "´",
    "ccedilla": "Ç",
    "Ccedilla": "Ç",
    "cedilla": "Ç",
}

# As teclas de nome comprido que o motor sabe registrar. Tem que bater com a
# tabela `CODIGOS` do `motor_atalhos.py`: nome que estiver so aqui vira
# atalho que nao funciona, que e o pior dos mundos.
TECLAS_ESPECIAIS = {
    "Esquerda", "Direita", "Cima", "Baixo",
    "Espaco", "Enter", "Backspace", "Del", "Insert",
    "Home", "End", "PgUp", "PgDn",
}
TECLAS_ESPECIAIS.update("F%d" % n for n in range(1, 25))


def da_para_registrar(nome: str) -> bool:
    """
    O motor consegue transformar esta tecla num atalho do Windows?

    Uma tecla so passa se for UM caractere (letra, numero, pontuacao -- o
    motor pergunta ao Windows onde ela fica no teclado atual) ou uma das
    especiais conhecidas. Qualquer outro nome de tecla do Tk seria aceito
    aqui e recusado la, e o atalho ficaria gravado sem funcionar.
    """
    return len(nome) == 1 or nome in TECLAS_ESPECIAIS

# Teclas que nao podem FECHAR uma combinacao. Esc cancela a gravacao, e as
# de trava mudam de estado sozinhas -- nenhuma serve de atalho.
NAO_SERVEM = {
    "Escape", "Caps_Lock", "Num_Lock", "Scroll_Lock",
    "Tab", "Menu",
}


def tecla_fisica(keysym: str, keycode: int) -> str:
    """O keysym da tecla FISICA (VentiladorArno, 10/out/2026).

    No teclado brasileiro Ctrl+Alt e o AltGr: Ctrl+Alt+2 chega como
    "twosuperior" (²), Ctrl+Alt+Q como "slash" -- e o atalho era recusado ou
    gravado errado. No Windows o `keycode` do Tk e o codigo virtual da tecla:
    letra, numero e F1..F24 saem dele; o resto segue pelo keysym."""
    if 0x30 <= keycode <= 0x39 or 0x41 <= keycode <= 0x5A:
        return chr(keycode).lower()
    if 0x70 <= keycode <= 0x87:
        return "F%d" % (keycode - 0x6F)
    if 0x60 <= keycode <= 0x69:              # teclado numerico
        return chr(keycode - 0x30)
    return keysym


def e_modificador(keysym: str) -> bool:
    return keysym in MODIFICADORES


def nome_de_tecla(keysym: str) -> str:
    """Como a tecla aparece na tela e no arquivo."""
    if keysym in MODIFICADORES:
        return MODIFICADORES[keysym]
    if keysym in APELIDOS:
        return APELIDOS[keysym]
    if len(keysym) == 1:
        return keysym.upper()
    return keysym


def escrever(modificadores, keysym: str = "") -> str:
    """
    A combinacao como texto, VALIDA OU NAO.

    Escreve o que esta apertado AGORA, mesmo que aquilo nao possa virar
    atalho: e ver a tecla proibida escrita em vermelho que explica a recusa.
    Quem diz se serve e o `porque_nao`, nao esta funcao.
    """
    presos = {MODIFICADORES[k] for k in modificadores if k in MODIFICADORES}
    partes = [m for m in ORDEM if m in presos]
    if keysym and not e_modificador(keysym):
        partes.append(nome_de_tecla(keysym))
    return "+".join(partes)


def porque_nao(modificadores, keysym: str = "") -> str:
    """
    Por que esta combinacao nao pode ser atalho? Texto vazio = pode.

    Uma frase curta e direta, porque ela vai aparecer embaixo da caixa
    enquanto a pessoa ainda esta com os dedos nas teclas.
    """
    if not keysym or e_modificador(keysym):
        return "Falta a tecla principal."
    if keysym in NAO_SERVEM:
        return "%s nao serve de atalho." % nome_de_tecla(keysym)
    if not da_para_registrar(nome_de_tecla(keysym)):
        return "O Windows nao aceita %s como atalho." % nome_de_tecla(keysym)
    if not tem_modificador(escrever(modificadores, keysym)):
        return "Falta Ctrl, Alt ou Win: sem eles o atalho roubaria a tecla do computador inteiro."
    return ""


def tem_modificador(teclas: str) -> bool:
    """
    A combinacao tem pelo menos um Ctrl / Alt / Shift / Win?

    Atalho GLOBAL sem modificador sequestraria a tecla no computador
    inteiro: gravar "L" faria a lampada piscar no meio de qualquer coisa que
    a pessoa estivesse escrevendo. Por isso o gravador recusa.
    """
    partes = {p.strip() for p in teclas.split("+")}
    return any(m in partes for m in ORDEM)


def rotulo(acao: str) -> str:
    """Como a acao aparece na tela. Acao desconhecida devolve o proprio nome."""
    return ACOES.get(acao, acao)


def guardados(config) -> dict[str, str]:
    """
    Os atalhos gravados, so os de acao conhecida.

    Filtrar na leitura, e nao na hora de desenhar: assim um config vindo de
    uma versao futura (ou editado na mao) nao faz aparecer linha de uma acao
    que este programa nao sabe executar.

    COMBINACAO VAZIA CONTINUA NA LISTA: e o atalho recem-adicionado, esperando
    as teclas. Quem nao aparece e a acao desconhecida ou o valor que nem texto
    e.
    """
    crus = (config.get("atalhos") if isinstance(config, dict) else getattr(config, "atalhos", None)) or {}
    return {
        acao: teclas
        for acao, teclas in crus.items()
        if acao in ACOES and isinstance(teclas, str)
    }


def em_ordem(config) -> list[tuple[str, str]]:
    """Os atalhos gravados na ordem de `ACOES`, e nao na ordem do arquivo."""
    salvos = guardados(config)
    return [(acao, salvos[acao]) for acao in ACOES if acao in salvos]


def livres(config) -> list[str]:
    """As acoes que ainda nao tem atalho -- as que o botao de adicionar oferece."""
    salvos = guardados(config)
    return [acao for acao in ACOES if acao not in salvos]


def quem_usa(config, teclas: str, menos: str = "") -> str | None:
    """
    Qual acao ja usa esta combinacao? `None` se estiver livre.

    `menos` e a acao que esta sendo regravada -- ela nao conflita consigo
    mesma. Quem chama isto e o gravador, no `widgets.py`; mora aqui porque a
    pergunta e sobre a lista, nao sobre a captura.
    """
    alvo = teclas.strip().lower()
    if not alvo:
        return None
    for acao, valor in guardados(config).items():
        if acao != menos and valor.strip().lower() == alvo:
            return acao
    return None
