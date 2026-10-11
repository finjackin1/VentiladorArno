"""Gera o .exe portatil (pasta) e o zip do release, e roda o autoteste do .exe.

Uso: python ferramentas\\empacotar.py
Sai em dist\\VentiladorArno\\ (VentiladorArno.exe + _internal\\) e
dist\\VentiladorArno-<versao>-windows.zip (o que vai no Release do GitHub).

(11/out/2026, pedido dele) ATUALIZA NO LUGAR: o PyInstaller gera numa pasta
temporaria e so o que MUDOU e copiado para dist\\<NOME>; o que sumiu do build
sai so de dentro de _internal\\. config.json, relatorios\\ e o que o programa
cria nunca sao movidos nem apagados (antes: mover config pro temp + apagar a
pasta -- com o .exe aberto parou no meio e o config dele ficou no temp).
(11/out/2026, permissao dele) FECHA E REABRE: .exe de dist\\ aberto recebe
relatorios\\.sair (janela.PEDIDO_SAIR: sai sem mexer no aparelho); se nao
atender em 8 s (versao antiga), taskkill. Reabre no fim se estava aberto.
Molde completo e testado: LightWireless\\ferramentas\\empacotar.py.
"""
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from ventilador import __version__  # noqa: E402

NOME = "VentiladorArno"
SEGREDOS = ("config.json", "config.json.bak", "config.json.tmp")
DO_USUARIO = ("relatorios", "ferramentas")     # criados pelo programa: ficam, nao vao no zip


def _pids(exe):
    cmd = (f"Get-Process -Name '{NOME}' -ErrorAction SilentlyContinue | "
           f"Where-Object {{ $_.Path -eq '{os.path.abspath(exe)}' }} | ForEach-Object {{ $_.Id }}")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                           encoding="oem", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(x) for x in r.stdout.split() if x.isdigit()]


def fechar(pasta):
    exe = os.path.join(pasta, NOME + ".exe")
    if not _pids(exe):
        return False
    rel = os.path.join(pasta, "relatorios")
    os.makedirs(rel, exist_ok=True)
    with open(os.path.join(rel, ".sair"), "w") as f:
        f.write("build")
    fim = time.monotonic() + 8
    while time.monotonic() < fim and _pids(exe):
        time.sleep(0.5)
    for pid in _pids(exe):
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        time.sleep(1.0)
    try:
        os.remove(os.path.join(rel, ".sair"))
    except OSError:
        pass
    return True


def sincronizar(novo, destino):
    copiados = removidos = 0
    for raiz, _dirs, arqs in os.walk(novo):
        rel_dir = os.path.relpath(raiz, novo)
        os.makedirs(os.path.join(destino, rel_dir), exist_ok=True)
        for a in arqs:
            o, d = os.path.join(raiz, a), os.path.join(destino, rel_dir, a)
            if not os.path.exists(d) or not filecmp.cmp(o, d, shallow=False):
                shutil.copy2(o, d)
                copiados += 1
    interno_d, interno_n = os.path.join(destino, "_internal"), os.path.join(novo, "_internal")
    for raiz, _dirs, arqs in os.walk(interno_d, topdown=False):
        rel_dir = os.path.relpath(raiz, interno_d)
        for a in arqs:
            if not os.path.exists(os.path.join(interno_n, rel_dir, a)):
                os.remove(os.path.join(raiz, a))
                removidos += 1
        if not os.listdir(raiz) and raiz != interno_d:
            os.rmdir(raiz)
    return copiados, removidos


def main():
    os.chdir(RAIZ)
    pasta_exe = os.path.join("dist", NOME)
    exe = os.path.join(pasta_exe, NOME + ".exe")
    temp = tempfile.mkdtemp(prefix="ventarno_build_")
    reabrir = False
    try:
        args = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--workpath", os.path.join(temp, "work"), "--specpath", temp,
            "--distpath", os.path.join(temp, "dist"),
            "--name", NOME, "--icon", os.path.abspath(os.path.join("ventilador", "marca.ico")),
            # bleak escolhe o backend do Windows em tempo de execucao; winrt e pystray idem
            "--collect-submodules", "bleak", "--collect-submodules", "winrt",
            "--hidden-import", "pystray._win32",
            "--exclude-module", "PyInstaller",
            # o Pillow puxa estes se estiverem instalados; o programa nao usa (-26 MB)
            "--exclude-module", "numpy", "--exclude-module", "charset_normalizer",
            "--exclude-module", "setuptools", "--exclude-module", "pkg_resources",
            os.path.abspath("VentiladorArno.pyw"),
        ]
        subprocess.run(args, check=True)       # o programa dele segue aberto enquanto compila
        novo = os.path.join(temp, "dist", NOME)
        for arq in ("README.md", "LICENSE"):
            shutil.copy(arq, novo)
        reabrir = fechar(pasta_exe)
        copiados, removidos = sincronizar(novo, pasta_exe)
        print(f"dist\\{NOME} atualizado no lugar: {copiados} trocado(s), {removidos} removido(s)")
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        for raiz, dirs, _arqs in os.walk(RAIZ):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(raiz, "__pycache__"), ignore_errors=True)
    subprocess.run([exe, "--autoteste"], timeout=60)
    zipado = os.path.join("dist", f"{NOME}-{__version__}-windows.zip")
    if os.path.exists(zipado):
        os.remove(zipado)
    with zipfile.ZipFile(zipado, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, _dirs, arqs in os.walk(pasta_exe):
            for a in arqs:
                caminho = os.path.join(raiz, a)
                rel = os.path.relpath(caminho, pasta_exe)
                if rel in SEGREDOS or rel.split(os.sep)[0] in DO_USUARIO:
                    continue                  # dados dele nao vao no release
                z.write(caminho, os.path.relpath(caminho, "dist"))
    print(f"pronto: {exe} e {zipado} ({os.path.getsize(zipado) // 1024} KB)")
    if reabrir:
        subprocess.Popen([os.path.abspath(exe)], cwd=os.path.abspath(pasta_exe))
        print("reaberto")


if __name__ == "__main__":
    main()
