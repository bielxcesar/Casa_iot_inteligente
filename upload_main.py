import sys
import time
from pathlib import Path
from mpremote.main import State, do_connect

class Args:
    def __init__(self, device):
        self.device = [device]


def _flush_initial_serial(serial):
    serial.write(b"\r\n")
    time.sleep(0.2)
    while serial.inWaiting() > 0:
        serial.read(serial.inWaiting())


def _wait_for_raw_repl(serial, timeout=10):
    end = b"raw REPL; CTRL-B to exit\r\n>"
    data = b""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if serial.inWaiting() > 0:
            data += serial.read(1)
            if data.endswith(end):
                return True
        else:
            time.sleep(0.01)
    print("raw REPL response:", data)
    return False


def _enter_raw_repl_manual(transport, timeout=10):
    serial = transport.serial
    for attempt in range(3):
        _flush_initial_serial(serial)
        serial.write(b"\r\x03")
        time.sleep(0.1)
        while serial.inWaiting() > 0:
            serial.read(serial.inWaiting())
        serial.write(b"\r\x01")
        if _wait_for_raw_repl(serial, timeout=timeout):
            transport.in_raw_repl = True
            return True
        time.sleep(0.2)
    return False


def upload(local_path, remote_path, device_uri="rfc2217://localhost:4000"):
    state = State()
    do_connect(state, Args(device_uri))
    try:
        transport = state.transport
        if hasattr(transport, "serial") and transport.serial:
            if not _enter_raw_repl_manual(transport):
                raise RuntimeError("could not enter raw repl")
        else:
            raise RuntimeError("serial transport not available")

        data = Path(local_path).read_bytes()
        transport.fs_writefile(remote_path, data)
        print(f"Uploaded {local_path} -> {remote_path}")
    finally:
        if state.transport and getattr(state.transport, "in_raw_repl", False):
            try:
                state.transport.exit_raw_repl()
            except Exception:
                pass
        if state.transport and getattr(state.transport, "serial", None):
            try:
                state.transport.serial.close()
            except Exception:
                pass


if __name__ == "__main__":
    local = sys.argv[1] if len(sys.argv) > 1 else "main.py"
    remote = sys.argv[2] if len(sys.argv) > 2 else "main.py"
    uri = sys.argv[3] if len(sys.argv) > 3 else "rfc2217://localhost:4000"
    upload(local, remote, uri)
