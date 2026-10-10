"""Mac web-only update restart for the original ON.command launcher."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.error("This helper is only used by the original macOS launcher.")
    # The original process may already have exited before this interpreter finishes importing.
    if args.parent_pid <= 1 or not 1024 <= args.port <= 65535:
        parser.error("Expected the owning web process and an unprivileged port.")
    deadline = time.monotonic() + 60
    # On macOS the helper is reparented when its original parent exits. No PID is signalled here.
    while os.getppid() == args.parent_pid or port_open(args.port):
        if time.monotonic() >= deadline:
            print("Web restart timed out waiting for the previous app/port. Start Music Generator ON again.", file=sys.stderr)
            return 1
        time.sleep(.25)
    subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.port)],
                     cwd=ROOT, stdin=subprocess.DEVNULL, start_new_session=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
