"""Icones do sistema da casa: grade 24, traco >= 1,5 px, ponta redonda,
desenhados 8x maiores (PIL) e reduzidos por media (BOX), sem halo."""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

S = 8  # super-amostragem


def _rgba(cor: str, a: int = 255):
    cor = cor.lstrip("#")
    return (int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16), a)


class _Tela:
    """Desenha numa grade 24 (coordenadas 0..24) em `lado` px reais."""

    def __init__(self, lado: int, cor: str):
        self.lado = lado
        self.k = lado * S / 24.0
        self.img = Image.new("RGBA", (lado * S, lado * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.cor = _rgba(cor)
        # traco 2/24 do lado, nunca < 1,5 px
        self.t = max(2.0 * self.k, 1.5 * S)

    def p(self, x, y):
        return (x * self.k, y * self.k)

    def linha(self, *pts, larg=None):
        w = larg if larg is not None else self.t
        q = [self.p(*pt) for pt in pts]
        self.d.line(q, fill=self.cor, width=int(round(w)), joint="curve")
        r = w / 2
        for x, y in (q[0], q[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=self.cor)
        for x, y in q[1:-1]:
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=self.cor)

    def circulo(self, cx, cy, raio, cheio=False):
        x, y = self.p(cx, cy)
        r = raio * self.k
        if cheio:
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=self.cor)
        else:
            self.d.ellipse((x - r, y - r, x + r, y + r), outline=self.cor,
                           width=int(round(self.t)))

    def poligono(self, *pts):
        self.d.polygon([self.p(*pt) for pt in pts], fill=self.cor)

    def fim(self) -> Image.Image:
        return self.img.resize((self.lado, self.lado), Image.BOX)


@lru_cache(maxsize=256)
def desenhar(nome: str, lado: int, cor: str) -> Image.Image:
    t = _Tela(lado, cor)
    if nome == "fechar":
        t.linha((6, 6), (18, 18)); t.linha((18, 6), (6, 18))
    elif nome == "minimizar":
        t.linha((6, 12), (18, 12))
    elif nome == "opcoes":                     # tres trilhos com botoes deslizantes
        for y, x in ((6, 15), (12, 8), (18, 13)):
            t.linha((4, y), (20, y))
            t.circulo(x, y, 2.6, cheio=True)
    elif nome == "agenda":                     # relogio
        t.circulo(12, 12, 8.5)
        t.linha((12, 7.5), (12, 12), (15.5, 14))
    elif nome == "voltar":
        t.linha((19, 12), (5, 12)); t.linha((11, 6), (5, 12), (11, 18))
    elif nome == "mais":
        t.linha((12, 5), (12, 19)); t.linha((5, 12), (19, 12))
    elif nome == "menos":
        t.linha((5, 12), (19, 12))
    elif nome == "lixo":
        t.linha((4.5, 7), (19.5, 7)); t.linha((9.5, 7), (10, 4.5), (14, 4.5), (14.5, 7))
        t.linha((6.5, 7), (7.5, 19.5), (16.5, 19.5), (17.5, 7))
    elif nome == "editar":                     # lapis
        t.linha((5, 19), (6, 15), (16, 5), (19, 8), (9, 18), (5, 19))
    elif nome == "tocar":
        t.poligono((8, 5.5), (19, 12), (8, 18.5))
    elif nome == "parar":
        t.poligono((7, 7), (17, 7), (17, 17), (7, 17))
    elif nome == "bluetooth":
        t.linha((7, 7.5), (17, 16.5), (12, 21), (12, 3), (17, 7.5), (7, 16.5))
    elif nome == "timer":                      # ampulheta
        t.linha((7, 4), (17, 4)); t.linha((7, 20), (17, 20))
        t.linha((8, 4), (8, 7), (16, 17), (16, 20)); t.linha((16, 4), (16, 7), (8, 17), (8, 20))
    elif nome == "desligar":                   # simbolo de energia (IEC 5009)
        x0, y0 = t.p(4.5, 5.0)
        x1, y1 = t.p(19.5, 20.0)
        t.d.arc((x0, y0, x1, y1), start=-50, end=230, fill=t.cor, width=int(round(t.t)))
        import math as _m
        r = (x1 - x0) / 2
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for ang in (-50, 230):
            a = _m.radians(ang)
            # pontas redondas do arco (centro no meio do traco)
            rr = t.t / 2
            mx, my = cx + (r - rr) * _m.cos(a), cy + (r - rr) * _m.sin(a)
            t.d.ellipse((mx - rr, my - rr, mx + rr, my + rr), fill=t.cor)
        t.linha((12, 3.5), (12, 11))
    elif nome == "seta_baixo":
        t.linha((7, 10), (12, 15), (17, 10))
    else:
        raise ValueError(nome)
    return t.fim()


def marca(lado: int, cor: str | None = None) -> Image.Image:
    """O ventilador: cubo + 3 pas. `cor` None = cinza (desligado/sem conexao)."""
    return _marca(lado, cor or "#9A978F")


@lru_cache(maxsize=32)
def _marca(lado: int, cor: str) -> Image.Image:
    t = _Tela(lado, cor)
    c = _rgba(cor)
    for i in range(3):
        a = math.radians(-90 + i * 120)
        # pa = elipse girada: desenha numa camada e gira
        camada = Image.new("RGBA", t.img.size, (0, 0, 0, 0))
        dd = ImageDraw.Draw(camada)
        k = t.k
        dd.ellipse((12 * k - 3.6 * k, 1.6 * k, 12 * k + 3.6 * k, 11.2 * k), fill=c)
        camada = camada.rotate(-math.degrees(a + math.pi / 2) + 15, resample=Image.BICUBIC,
                               center=(12 * k, 12 * k))
        t.img.alpha_composite(camada)
    x, y = t.p(12, 12)
    r = 4.6 * t.k
    t.d.ellipse((x - r, y - r, x + r, y + r), fill=(0, 0, 0, 0))   # vao em volta do cubo
    t.circulo(12, 12, 2.9, cheio=True)
    return t.fim()
