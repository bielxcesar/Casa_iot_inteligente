import sys
import time
from pathlib import Path
from mpremote.main import State, do_connect

class Args:
    def __init__(self, device):
        self.device = [device]

def _flush_input(serial):
    serial.write(b"\r\n")
    time.sleep(0.2)
    while serial.inWaiting() > 0:
        dumped = serial.read(serial.inWaiting())

def _wait_for_prompt(serial, prompt, timeout=10):
    data = b""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if serial.inWaiting() > 0:
            data += serial.read(1)
            if data.endswith(prompt):
                return True, data
        else:
            time.sleep(0.01)
    return False, data

def enter_raw_repl(serial, max_attempts=5, timeout=10):
    prompt = b"raw REPL; CTRL-B to exit\r\n>"
    for attempt in range(1, max_attempts + 1):
        print(f'Tentando entrar no modo de gravacao ({attempt}/{max_attempts})...')
        _flush_input(serial)
        serial.write(b"\r\x03")
        time.sleep(0.05)
        while serial.inWaiting() > 0:
            serial.read(serial.inWaiting())
        serial.write(b"\r\x01")
        ok, data = _wait_for_prompt(serial, prompt, timeout=timeout)
        if ok:
            print('Modo de gravacao ativado com sucesso!')
            return True
        time.sleep(0.2)
    return False

def exec_raw_repl(serial, command, timeout=10):
    serial.write(command.encode('utf-8'))
    serial.write(b"\x04")

    # Read acknowledgment: some devices may emit prompt characters before
    # the 'OK' response (e.g. b">OK") so read bytes until we find 'OK'.
    ack = b""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if serial.inWaiting() > 0:
            ack += serial.read(1)
            if b"OK" in ack:
                break
        else:
            time.sleep(0.01)

    if b"OK" not in ack:
        raise RuntimeError(f"Falha no comando. Resposta da placa={ack!r}")

    # Now collect output until the raw REPL EOF (0x04) is received.
    out = b""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if serial.inWaiting() > 0:
            b = serial.read(1)
            if b == b"\x04":
                return out
            out += b
        else:
            time.sleep(0.01)
    raise RuntimeError('Tempo esgotado esperando a placa responder.')

def write_file_raw_repl(serial, dest, data, chunk_size=256):
    # O PULO DO GATO ESTÁ AQUI: Enviando em pacotes pequenos para não engasgar
    exec_raw_repl(serial, f"f = open({dest!r}, 'wb')\n")
    
    total_bytes = len(data)
    enviado = 0
    
    for i in range(0, total_bytes, chunk_size):
        chunk = data[i : i + chunk_size]
        exec_raw_repl(serial, f"f.write({chunk!r})\n")
        enviado += len(chunk)
        # Mostra o progresso no terminal pra gente não ficar no escuro
        print(f"  -> Gravando {dest}: {enviado}/{total_bytes} bytes...")
        
    exec_raw_repl(serial, "f.close()\n")

def upload_files(files_to_upload, device_uri="rfc2217://localhost:4000"):
    state = State()
    do_connect(state, Args(device_uri))
    transport = state.transport
    if not transport or not getattr(transport, 'serial', None):
        raise RuntimeError('Linha de comunicação indisponível.')

    try:
        serial = transport.serial
        print('Conectado na placa via', device_uri)

        if hasattr(transport, 'enter_raw_repl'):
            try:
                transport.enter_raw_repl()
                print('Modo de gravação ativado com sucesso!')
            except Exception as er:
                print('Falha no raw REPL nativo do mpremote:', er)
                print('Tentando fallback manual...')
                if not enter_raw_repl(serial):
                    raise RuntimeError('Nao foi possivel dominar a placa para gravacao.') from er
                transport.in_raw_repl = True
        else:
            if not enter_raw_repl(serial):
                raise RuntimeError('Nao foi possivel dominar a placa para gravacao.')
            transport.in_raw_repl = True

        for filename in files_to_upload:
            local_path = Path(filename)
            if not local_path.exists():
                print(f"Aviso: Arquivo {filename} nao encontrado. Pulando...")
                continue

            data = local_path.read_bytes()
            print(f'\nIniciando upload de {filename}...')
            write_file_raw_repl(serial, filename, data)
            print(f'Upload de {filename} concluido!')

        print('\nQuase la! Reiniciando o cérebro da placa...')
        exec_raw_repl(serial, 'import machine\nmachine.reset()')
    finally:
        if getattr(transport, 'in_raw_repl', False):
            try:
                transport.exit_raw_repl()
            except Exception:
                pass
        if getattr(transport, 'serial', None):
            try:
                transport.serial.close()
            except Exception:
                pass

def parse_cli_args():
    if len(sys.argv) > 1:
        maybe_uri = sys.argv[-1]
        if maybe_uri.startswith(('rfc2217://', 'serial://', 'COM', '/dev/')) or '://' in maybe_uri:
            arquivos = sys.argv[1:-1] or ['ssd1306.py', 'main.py']
            return arquivos, maybe_uri
        return sys.argv[1:], 'rfc2217://localhost:4000'
    return ['ssd1306.py', 'main.py'], 'rfc2217://localhost:4000'


if __name__ == '__main__':
    arquivos_para_enviar, uri = parse_cli_args()

    print("Ligando o trator de carga pesada...")
    upload_files(arquivos_para_enviar, uri)