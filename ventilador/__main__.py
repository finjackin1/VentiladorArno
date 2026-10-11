"""Entrada: python -m ventilador [--bandeja]"""
from __future__ import annotations

import logging
import logging.handlers
import sys

from . import __version__, estilo
from .caminhos import relatorios


def _log():
    h = logging.handlers.RotatingFileHandler(relatorios() / "ventilador.log", maxBytes=1_000_000,
                                             backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(h)
    logging.getLogger("bleak").setLevel(logging.WARNING)


def _unico() -> bool:
    """Uma instancia so. A segunda pede a primeira para aparecer e sai."""
    try:
        import ctypes
        _unico.m = ctypes.windll.kernel32.CreateMutexW(None, False, "VentiladorArno_unico")
        if ctypes.windll.kernel32.GetLastError() == 183:
            if "--bandeja" not in sys.argv:          # quem sobe pelo Windows sai quieto
                (relatorios() / ".mostrar").write_text("1")
            return False
    except Exception:
        pass
    return True


def _autoteste():
    """--autoteste: confere o empacotado (.exe) sem janela nem Bluetooth de verdade:
    carrega o que o PyInstaller pode esquecer e grava relatorios\\autoteste.txt."""
    linhas = []
    for mod in ("bleak", "bleak.backends.winrt.scanner", "bleak.backends.winrt.client",
                "pystray", "pystray._win32", "PIL.ImageTk", "tkinter", "winreg"):
        try:
            __import__(mod)
            linhas.append(f"ok {mod}")
        except Exception as e:
            linhas.append(f"FALHA {mod}: {type(e).__name__}: {e}")
    try:
        import tkinter as tk
        from . import estilo as E, icones
        r = tk.Tk()
        r.withdraw()
        E.iniciar(r)
        E.icone("marca", 32, "#FF5A1F")
        icones.desenhar("bluetooth", 20, "#FFFFFF")
        r.destroy()
        linhas.append("ok tk + icones")
    except Exception as e:
        linhas.append(f"FALHA tk: {type(e).__name__}: {e}")
    (relatorios() / "autoteste.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    if sys.stdout is None:                       # pythonw
        import io
        sys.stdout = sys.stderr = io.StringIO()
    if "--autoteste" in sys.argv:
        _autoteste()
        return
    _log()
    if not _unico():
        return
    logging.info("inicio %s %s", __version__, " ".join(sys.argv[1:]))
    estilo.ciente_de_dpi()
    from .ble import Conexao
    from .config import Config
    from .janela import Janela

    cfg = Config.carregar()
    cx = Conexao(cfg["endereco"])
    cx.iniciar()
    escondida = "--bandeja" in sys.argv or bool(cfg.opcoes.get("comecar_na_bandeja"))
    j = Janela(cx, escondida=escondida)
    try:
        j.rodar()
    finally:
        cx.encerrar()
        logging.info("fim")


if __name__ == "__main__":
    main()
