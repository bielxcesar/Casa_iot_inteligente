# Projeto ESP32 - Casa Inteligente

Este projeto é um firmware MicroPython para ESP32 que lê sensores e controla atuadores via MQTT/Node-RED.

## O que foi feito

- O arquivo principal é `main.py`.
- O Wokwi está configurado para expor a porta serial via RFC2217 em `wokwi.toml` na porta `4000`.
- O `mpremote` padrão falhava ao entrar no modo raw REPL via RFC2217, gerando o erro:
  - `could not enter raw repl`
- Para contornar isso, foi criado um script Python auxiliar `upload_manual.py` que:
  1. conecta-se ao dispositivo pela URI `rfc2217://localhost:4000`
  2. limpa o buffer inicial da serial
  3. entra manualmente no raw REPL
  4. grava `main.py` no ESP32
  5. reinicia o ESP32 para executar o novo firmware

## Por que isso foi necessário

O `mpremote` tenta usar uma sequência de comando automática para entrar no raw REPL e, no caso do Wokwi/RFC2217, isso não funcionava de forma confiável.

Então criamos um caminho mais direto e compatível com o Wokwi, evitando a falha no handshake serial.

## Como usar

1. Abra o simulador Wokwi e carregue o projeto.
2. Garanta que o `wokwi.toml` contenha:

```toml
[wokwi]
version = 1
firmware = "firmware.bin"
rfc2217ServerPort = 4000

[[net.forward]]
from = "localhost:8080"
to = "target:8080"
```

3. No terminal, entre na pasta `esp32`:

```powershell
cd "C:..\wokwi-vscode-micropython-main\wokwi-vscode-micropython-main\esp32"
```

4. Execute o upload manual:

```powershell
python upload_manual.py main.py main.py rfc2217://localhost:4000
```

5. Aguarde a mensagem de sucesso:

```text
connected to rfc2217://localhost:4000
raw REPL attempt 1/5
...
entered raw REPL
Uploaded main.py to main.py
```

6. Após o upload, o script reinicia o ESP32 automaticamente para rodar o novo `main.py`.

http://127.0.0.1:1880/ui/#!/0?socketid=eqlBI8CX3BSx3in6AAAD
http://localhost:1880/meu-site


## O que deve acontecer depois

- O ESP32 deve conectar na rede Wi-Fi `Wokwi-GUEST`.
- O firmware deve tentar se conectar ao broker MQTT `broker.hivemq.com`.
- O Node-RED deve receber e enviar comandos pelos tópicos configurados em `main.py`.

## Dicas adicionais

- Se `python` não for reconhecido no terminal, use o caminho completo do executável Python.
- Se o Wokwi não estiver com rede ativa, a conexão Wi-Fi não vai acontecer.
- Se quiser testar de novo, basta rodar o mesmo comando de upload.

## Arquivos importantes

- `main.py` — código do firmware
- `upload_manual.py` — script que faz o upload do firmware via RFC2217
- `wokwi.toml` — configuração do Wokwi e do servidor RFC2217
