"""Tokens e medidas do padrao "app simples" (perfil enxuto da interface-polida).

Cores = as da interface-polida (nada de cor escrita a mao fora daqui).
Chamar `iniciar(raiz)` logo depois de criar o Tk.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from functools import lru_cache

from PIL import Image, ImageDraw, ImageTk

FUNDO = "#16161A"
FUNDO_FUNDO = "#101013"
CAMADA_1 = "#1D1D22"
BORDA_1 = "#2F2F37"
BORDA_MOUSE = "#4A4A54"
CAMADA_2 = "#25252C"
SUPERFICIE = "#2C2C34"
SUPERFICIE_BORDA = "#4C4C57"
LINHA = "#2C2C33"
TEXTO = "#E9E6DF"
TEXTO_2 = "#9A978F"
APAGADO = "#6F6D68"
ACENTO = "#FF5A1F"
VERDE = "#57C27A"
AZUL = "#5AA9FF"
ERRO = "#FF5A5A"
ALERTA = "#E8C15A"
FOCO = "#8E8B93"
FECHAR_SEGURAR = "#C42B1C"

ESCALA = 1.3
DPI = 1.0
_familia = "Segoe UI"
_semi = None


def ciente_de_dpi():
    """Antes de criar o Tk: medidas em pixel real (modo sistema)."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def iniciar(raiz: tk.Tk):
    global DPI, _familia, _semi
    try:
        import ctypes
        DPI = max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96.0)
    except Exception:
        DPI = 1.0
    fams = set(tkfont.families(raiz))
    _familia = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in fams), "TkDefaultFont")
    semi = {"Segoe UI Variable Text": "Segoe UI Variable Text Semibold",
            "Segoe UI": "Segoe UI Semibold"}.get(_familia)
    _semi = semi if semi in fams else None


def px(n: float) -> int:
    v = n * ESCALA * DPI
    return int(v + 0.5) if v > 0 else int(v - 0.5)


_FONTES: dict = {}


def fonte(tam: int, peso: str = "normal") -> str:
    """peso: normal | semibold. Sem caixa alta em lugar nenhum."""
    chave = (tam, peso)
    f = _FONTES.get(chave)
    if f is None:
        fam, w = _familia, "normal"
        if peso == "semibold":
            fam, w = (_semi, "normal") if _semi else (_familia, "bold")
        f = tkfont.Font(family=fam, size=round(tam * ESCALA), weight=w)
        _FONTES[chave] = f
    return f.name


def misturar(frente: str, fundo: str, alfa: float) -> str:
    a = max(0.0, min(1.0, alfa))
    f = [int(frente[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(fundo[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x * a + y * (1 - a)) for x, y in zip(f, b))


@lru_cache(maxsize=512)
def _ret(w: int, h: int, r: int, cheio: str, borda: str | None, fundo: str, esp: int) -> Image.Image:
    s = 4
    img = Image.new("RGB", (w * s, h * s), fundo)
    d = ImageDraw.Draw(img)
    if borda:
        d.rounded_rectangle((0, 0, w * s - 1, h * s - 1), r * s, fill=borda)
        e = esp * s
        d.rounded_rectangle((e, e, w * s - 1 - e, h * s - 1 - e), max(0, r * s - e), fill=cheio)
    else:
        d.rounded_rectangle((0, 0, w * s - 1, h * s - 1), r * s, fill=cheio)
    return img.resize((w, h), Image.BOX)


_FOTOS: dict = {}


def ret(w: int, h: int, r: int, cheio: str, fundo: str, borda: str | None = None, esp: int = 1):
    """Retangulo arredondado com antisserrilhado, como PhotoImage (cache)."""
    chave = (w, h, r, cheio, borda, fundo, esp)
    foto = _FOTOS.get(chave)
    if foto is None:
        foto = ImageTk.PhotoImage(_ret(w, h, r, cheio, borda, fundo, esp))
        if len(_FOTOS) > 600:
            _FOTOS.clear()
        _FOTOS[chave] = foto
    return foto


_ICONES: dict = {}


def icone(nome: str, lado: int, cor: str):
    from . import icones
    chave = (nome, lado, cor)
    foto = _ICONES.get(chave)
    if foto is None:
        img = icones.marca(lado, cor) if nome == "marca" else icones.desenhar(nome, lado, cor)
        foto = ImageTk.PhotoImage(img)
        _ICONES[chave] = foto
    return foto
