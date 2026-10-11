"""Iniciar com o Windows (porta enxuta do scrcpy-f, 10/out/2026).

- "Iniciar com o Windows" = chave Run do PROPRIO usuario (HKCU), sem admin.
- Sub-opcao "iniciar mais rapido" = tarefa no Agendador "ao fazer logon":
  abre na hora do logon, fora da fila Run (que espera a area de trabalho).
  Tenta sem elevacao; se o Windows recusar, pede o administrador UMA vez
  (.bat em ferramentas\\). Os dois caminhos nunca ficam juntos.
- Tudo so muda no clique dele; abrir o programa so LE.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import winreg

from .caminhos import pasta_do_programa

log = logging.getLogger(__name__)
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "VentiladorArno"
ARGUMENTO_INICIO = "--bandeja"      # quem sobe pelo Windows nasce na bandeja e, se ja houver um aberto, sai quieto


def comando() -> str:
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}" {ARGUMENTO_INICIO}'
    exe = os.path.abspath(sys.executable)
    pasta, nome = os.path.split(exe)
    if nome.lower().startswith("python") and not nome.lower().startswith("pythonw"):
        cand = os.path.join(pasta, nome.lower().replace("python", "pythonw", 1))
        if os.path.exists(cand):
            exe = cand
    return f'"{exe}" "{pasta_do_programa() / "VentiladorArno.pyw"}" {ARGUMENTO_INICIO}'


# -- fila Run ------------------------------------------------------------------
def _run_ler() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            return str(winreg.QueryValueEx(k, NOME)[0])
    except OSError:
        return None


def _run_ativo() -> bool:
    v = _run_ler()
    return v is not None and v.strip().lower() == comando().lower()


def _run_ativar() -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, comando())
    except OSError as e:
        log.warning("nao gravei o inicio (Run): %s", e)
        return False
    return _run_ativo()


def _run_desativar() -> bool:
    if _run_ler() is None:
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOME)
        return True
    except OSError as e:
        log.warning("nao tirei o inicio (Run): %s", e)
        return False


# -- Agendador -----------------------------------------------------------------
def _rodar(args: list[str]) -> tuple[bool, str]:
    """schtasks sem piscar console (o app roda em pythonw)."""
    try:
        # saida do schtasks vem na pagina OEM (cp850): em modo UTF-8 do Python o
        # text=True puro quebrava a thread de leitura (11/out/2026, LightWireless)
        r = subprocess.run(args, capture_output=True, text=True, encoding="oem", errors="replace", timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return r.returncode == 0, " ".join(((r.stdout or "") + (r.stderr or "")).split())


def tarefa_existe() -> bool:
    return _rodar(["schtasks", "/Query", "/TN", NOME])[0]


def _usuarios() -> list[str]:
    """schtasks quer o usuario QUALIFICADO (MAQUINA\\nome); o cru da erro (AmbiSync)."""
    u = os.environ.get("USERNAME") or ""
    if not u:
        return []
    nomes = []
    for pre in (os.environ.get("USERDOMAIN"), os.environ.get("COMPUTERNAME")):
        if pre and f"{pre}\\{u}" not in nomes:
            nomes.append(f"{pre}\\{u}")
    return nomes + [u]


def _variacoes() -> list[list[str]]:
    base = ["schtasks", "/Create", "/TN", NOME, "/TR", comando()]
    fim = ["/SC", "ONLOGON", "/F"]
    t = []
    for n in _usuarios():
        t += [base + ["/RU", n, "/IT"] + fim, base + ["/RU", n] + fim]
    return t + [base + ["/IT"] + fim, base + fim]


def _pasta_ferramentas() -> str:
    p = pasta_do_programa() / "ferramentas"
    p.mkdir(exist_ok=True)
    return str(p)


def _bat(nome: str, linha: str) -> str | None:
    destino = os.path.join(_pasta_ferramentas(), nome)
    linhas = ["@echo off", "REM Gerado pelo Ventilador Arno -- pode apagar depois de usar.",
              "REM A mao: botao direito -> Executar como administrador.", "", linha, "",
              "if %ERRORLEVEL%==0 (", "    echo Pronto.", ") else (",
              "    echo Falhou. Codigo: %ERRORLEVEL%",
              '    if not "%~1"=="auto" set /p "TECLA=Leia o resultado. Aperte ENTER para fechar: "',
              ")", ""]
    try:
        with open(destino, "w", encoding="cp1252", errors="replace") as f:
            f.write("\r\n".join(linhas))
        return destino
    except OSError as e:
        log.warning("nao escrevi %s: %s", nome, e)
        return None


def _elevado(caminho: str) -> bool:
    """Roda o .bat pedindo administrador (janela do Windows). True se rodou."""
    import ctypes
    from ctypes import wintypes

    class SEI(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                    ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        i = SEI()
        i.cbSize = ctypes.sizeof(i)
        i.fMask = 0x40
        i.lpVerb, i.lpFile = "runas", "cmd.exe"
        i.lpParameters = f'/c ""{caminho}" auto"'
        i.lpDirectory = os.path.dirname(caminho)
        i.nShow = 0
        shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SEI)]
        if not shell32.ShellExecuteExW(ctypes.byref(i)):
            log.info("elevacao recusada/falhou (erro %s)", ctypes.get_last_error())
            return False
        if i.hProcess:
            kernel32.WaitForSingleObject(i.hProcess, 60_000)
            kernel32.CloseHandle(i.hProcess)
        return True
    except Exception as e:
        log.warning("falha ao pedir elevacao: %s", e)
        return False


# -- o que a tela chama ----------------------------------------------------------
def ativo() -> bool:
    return _run_ativo() or tarefa_existe()


def rapido() -> bool:
    return tarefa_existe()


def definir(ligado: bool) -> bool:
    """Liga = fila Run (ou ja abre pela tarefa). Desliga = tira os dois."""
    if ligado:
        return True if tarefa_existe() else _run_ativar()
    _run_desativar()
    if tarefa_existe():
        ok, saida = _rodar(["schtasks", "/Delete", "/TN", NOME, "/F"])
        if not ok:
            log.info("remocao simples recusada: %s", saida)
            c = _bat("remover-tarefa-inicio.bat", f'schtasks /Delete /TN "{NOME}" /F')
            if c:
                _elevado(c)
    return not ativo()


def definir_rapido(ligado: bool) -> bool:
    if ligado:
        if not tarefa_existe():
            for args in _variacoes():
                ok, saida = _rodar(args)
                if ok:
                    log.info("tarefa de logon criada")
                    break
                log.info("tarefa recusada: %s", saida)
        if not tarefa_existe():
            usuario = (_usuarios() or [""])[0]
            alvo = comando().replace('"', '\\"')
            c = _bat("criar-tarefa-inicio.bat",
                     f'schtasks /Create /TN "{NOME}" /TR "{alvo}" /SC ONLOGON /RU "{usuario}" /IT /F')
            if c:
                _elevado(c)
        if tarefa_existe():
            _run_desativar()
            return True
        return False
    if tarefa_existe():
        ok, saida = _rodar(["schtasks", "/Delete", "/TN", NOME, "/F"])
        if not ok:
            log.info("remocao simples recusada: %s", saida)
            c = _bat("remover-tarefa-inicio.bat", f'schtasks /Delete /TN "{NOME}" /F')
            if c:
                _elevado(c)
    if tarefa_existe():
        return False
    return _run_ativar()
