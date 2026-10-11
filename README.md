# Ventilador Arno

Programa para Windows que controla o ventilador **Arno Ultra Silence Force Bluetooth (VDBT)** pelo
Bluetooth do PC, no lugar do aplicativo do celular.

> Projeto independente, sem ligação com a Arno ou o Groupe SEB. Use por sua conta.

## O que faz
- **Velocidade**: desligar, 1, 2 e 3. A tela mostra o estado real do ventilador, inclusive quando você
  usa o botão do próprio aparelho.
- **Timer**: liga/mantém na velocidade atual por um tempo e desliga. Fica gravado no ventilador.
- **Rotinas**: sequências de passos (velocidade + minutos) enviadas ao ventilador, que as cumpre sozinho.
  Vêm 4 prontas e dá para criar e editar.
- **Agenda**: horários e dias da semana para desligar, mudar a velocidade ou rodar uma rotina
  (o PC precisa estar ligado).
- **Conexão automática**: procura e conecta sozinho, reconecta se cair, e explica o que fazer quando não
  consegue (Bluetooth do PC desligado, ventilador fora da tomada, celular conectado nele…).
- **Bandeja**: um clique liga/desliga, dois cliques abrem a janela.
- **Atalhos de teclado globais** (você escolhe as teclas), **iniciar com o Windows** (com a opção
  "iniciar mais rápido"), **iniciar minimizado** e **soltar o ventilador** para usar o app do celular.

Oscilação e inclinação não são controladas por Bluetooth neste modelo (nem pelo app oficial).

## Requisitos
- Windows 10 ou 11 com Bluetooth 4.0 (BLE) ou mais novo.

## Como usar (versão pronta, sem instalar nada)
1. Baixe o `VentiladorArno-<versão>-windows.zip` em **Releases**.
2. Extraia numa pasta de caminho curto (ex.: `C:\Programas\VentiladorArno`) — caminhos muito longos
   esbarram no limite do Windows.
3. Ligue o ventilador e **feche o app no celular** (o ventilador aceita uma conexão por vez).
4. Abra o `VentiladorArno.exe`. Configurações e registros ficam na própria pasta (portátil).

O `.exe` não é assinado: o Windows SmartScreen pode avisar na primeira vez ("Mais informações" →
"Executar assim mesmo").

## Rodar pelo código (Python 3.11+)
1. `python -m pip install -r requirements.txt`
2. Dois cliques em `VentiladorArno.pyw`.
3. Gerar o `.exe`: `python -m pip install pyinstaller` e `python ferramentas\empacotar.py`
   (sai em `dist\`, com o zip do release).
4. Teste do protocolo sem interface: `python ferramentas\teste_ble.py` (relatório em `relatorios\`).

As configurações ficam em `config.json` e o registro em `relatorios\ventilador.log`, na pasta do programa.

## Como funciona (resumo)
O ventilador anuncia um nome com "FAN" e expõe um serviço BLE próprio com duas características: uma de
estado (leitura) e uma de comando (escrita). Velocidade é um comando de 2 bytes; timer e rotinas são uma
lista de passos (minutos + velocidade) que o próprio ventilador executa. Sem senha, sem pareamento e sem
nuvem. Detalhes em `ventilador/protocolo.py`.

## Estrutura
- `ventilador/` — o programa (`protocolo.py` monta e lê os pacotes, `ble.py` cuida da conexão,
  `janela.py` é a interface).
- `ferramentas/teste_ble.py` — teste do protocolo sem interface.
- `ferramentas/empacotar.py` — gera o `.exe` portátil e o zip do release.

## Como foi feito
O Ventilador Arno foi desenvolvido com apoio de inteligência artificial: o código, e também a análise do
aplicativo oficial que revelou o protocolo Bluetooth, foram feitos em conversa com o **Claude**, da
Anthropic (no Claude Code). As decisões de projeto, o desenho da interface, os testes com o ventilador de
verdade e o rumo de cada funcionalidade são de [finjackin](https://github.com/finjackin1).

## Licença
GPLv3 — veja `LICENSE`.
