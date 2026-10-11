"""Gera o .exe portatil (pasta) e o zip do release.

Uso: python ferramentas\\empacotar.py
Sai em dist\\VentiladorArno\\ (VentiladorArno.exe + _internal\\) e
dist\\VentiladorArno-<versao>-windows.zip (o que vai no Release do GitHub).
"""
import os
import shutil
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from ventilador import __version__  # noqa: E402

NOME = "VentiladorArno"


def main():
    import tempfile
    os.chdir(RAIZ)
    # build\ e .spec numa pasta temporaria apagada no fim: a pasta do projeto
    # fica so com o que e usado (pedido dele, 10/out/2026)
    temp = tempfile.mkdtemp(prefix="ventarno_build_")
    # ele testa pelo .exe em dist\: config e relatorios dele SOBREVIVEM ao rebuild
    pasta_exe = os.path.join("dist", NOME)
    guardados = []
    for nome in ("config.json", "relatorios"):
        origem = os.path.join(pasta_exe, nome)
        if os.path.exists(origem):
            destino = os.path.join(temp, "guardado_" + nome)
            shutil.move(origem, destino)
            guardados.append((destino, origem))
    shutil.rmtree(pasta_exe, ignore_errors=True)
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--workpath", temp, "--specpath", temp,
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
    try:
        subprocess.run(args, check=True)
    finally:
        os.makedirs(pasta_exe, exist_ok=True)
        for destino, origem in guardados:
            shutil.move(destino, origem)
        shutil.rmtree(temp, ignore_errors=True)
        for raiz, dirs, _arqs in os.walk(RAIZ):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(raiz, "__pycache__"), ignore_errors=True)
    pasta = os.path.join("dist", NOME)
    for arq in ("README.md", "LICENSE"):
        shutil.copy(arq, pasta)
    zipado = os.path.join("dist", f"{NOME}-{__version__}-windows.zip")
    if os.path.exists(zipado):
        os.remove(zipado)
    with zipfile.ZipFile(zipado, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, _dirs, arqs in os.walk(pasta):
            for a in arqs:
                caminho = os.path.join(raiz, a)
                rel = os.path.relpath(caminho, pasta)
                if rel == "config.json" or rel.startswith("relatorios"):
                    continue                  # dados de teste dele nao vao no release
                z.write(caminho, os.path.relpath(caminho, "dist"))
    print(f"pronto: {pasta}\\{NOME}.exe e {zipado} ({os.path.getsize(zipado) // 1024} KB)")


if __name__ == "__main__":
    main()
