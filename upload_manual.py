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
        print('flushed:', dumped)


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
        print(f'raw REPL attempt {attempt}/{max_attempts}')
        _flush_input(serial)
        serial.write(b"\r\x03")
        time.sleep(0.05)
        while serial.inWaiting() > 0:
            serial.read(serial.inWaiting())
        serial.write(b"\r\x01")
        ok, data = _wait_for_prompt(serial, prompt, timeout=timeout)
        print('raw REPL data:', data)
        if ok:
            print('entered raw REPL')
            return True
        time.sleep(0.2)
    return False


def exec_raw_repl(serial, command, timeout=10):
    serial.write(command.encode('utf-8'))
    serial.write(b"\x04")
    ack = serial.read(2)
    if ack != b"OK":
        raise RuntimeError(f"raw REPL command failed, response={ack!r}")

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
    raise RuntimeError('timeout waiting for raw REPL end marker')


def write_file_raw_repl(serial, dest, data, chunk_size=256):
    cmd = f"f = open({dest!r}, 'wb')\n"
    for i in range(0, len(data), chunk_size):
        chunk = data[i : i + chunk_size]
        cmd += f"f.write({chunk!r})\n"
    cmd += "f.close()\n"
    exec_raw_repl(serial, cmd)


def upload(local_path, remote_path, device_uri="rfc2217://localhost:4000"):
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(local_path)

    state = State()
    do_connect(state, Args(device_uri))
    transport = state.transport
    if not transport or not getattr(transport, 'serial', None):
        raise RuntimeError('serial transport unavailable')

    try:
        serial = transport.serial
        print('connected to', device_uri)
        if not enter_raw_repl(serial):
            raise RuntimeError('could not enter raw REPL')
        transport.in_raw_repl = True
        data = local_path.read_bytes()
        write_file_raw_repl(serial, remote_path, data)
        print(f'Uploaded {local_path} to {remote_path}')
        print('Resetting device to run the new main.py...')
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


if __name__ == '__main__':
    local = sys.argv[1] if len(sys.argv) > 1 else 'main.py'
    remote = sys.argv[2] if len(sys.argv) > 2 else 'main.py'
    uri = sys.argv[3] if len(sys.argv) > 3 else 'rfc2217://localhost:4000'
    upload(local, remote, uri)
