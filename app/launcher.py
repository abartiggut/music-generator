"""Native, shell-free launcher. The supervisor terminates only children it created."""
import argparse
import hmac
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("MUSIC_GENERATOR_DATA_DIR", ROOT / "data")).resolve()
STATE = DATA / "runtime.json"
DEFAULTS = {"mode": "remote", "server_url": "", "ssh_host": "gpu-server", "remote_port": 18085,
            "tunnel_port": 18085, "port": 8765, "no_browser": False}


def config_fingerprint(config: dict) -> str:
    """Compare the effective connection, excluding presentation options and credentials."""
    effective = {key: config.get(key, "") for key in
                 ("mode", "server_url", "ssh_host", "remote_port", "tunnel_port", "port", "lm_model", "cuda_bin")}
    if config["mode"] == "local":
        effective["local_engine"] = str(Path(config.get("local_engine", ROOT / "engine" / "build-cuda" / "Release" / "ace-server.exe")).resolve())
        effective["local_models"] = str(Path(config.get("local_models", ROOT / "engine" / "models")).resolve())
    return hashlib.sha256(json.dumps(effective, sort_keys=True).encode()).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def identity(port: int) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/runtime", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return {}


def current_state() -> dict:
    state = read_json(STATE)
    if state.get("instance_id") and identity(state.get("port", 8765)).get("instance_id") == state.get("instance_id"):
        return state
    return {}


def validate_config(config: dict) -> dict:
    if config["mode"] not in {"mock", "remote", "local"}:
        raise ValueError("mode must be mock, remote or local")
    for key in ("port", "remote_port", "tunnel_port"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 1024 <= value <= 65535:
            raise ValueError(f"{key} must be an integer between 1024 and 65535")
    if config["mode"] != "mock" and config["port"] == config["tunnel_port"]:
        raise ValueError("Web and model/tunnel ports must differ")
    host = config["ssh_host"]
    if not isinstance(host, str) or host.startswith("-") or any(c.isspace() for c in host):
        raise ValueError("ssh_host must be an SSH alias or user@hostname")
    url = config["server_url"]
    if url:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("server_url must be an HTTP(S) URL without embedded credentials")
        _ = parts.port
    for key in ("local_engine", "local_models", "lm_model"):
        if key in config and (not isinstance(config[key], str) or any(character in config[key] for character in "\r\n\0")):
            raise ValueError(f"{key} must be a filename or directory string")
    if config.get("cuda_bin"):
        cuda_bin = config["cuda_bin"]
        if not isinstance(cuda_bin, str) or any(character in cuda_bin for character in "\r\n\0") or not Path(cuda_bin).is_dir():
            raise ValueError("cuda_bin must point to an existing CUDA Toolkit bin directory")
    return config


def hidden_options(detached: bool = False) -> dict:
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
        if detached:
            flags |= subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        return {"creationflags": flags}
    return {"start_new_session": True} if detached else {}


def stop_child(child: subprocess.Popen | None) -> None:
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def control(state: dict, action: str) -> None:
    req = urllib.request.Request(f"http://127.0.0.1:{state['control_port']}/{action}", data=b"{}", method="POST",
                                 headers={"Authorization": "Bearer " + state["control_token"]})
    with urllib.request.urlopen(req, timeout=5) as response:
        json.load(response)


def run(config: dict) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    instance = uuid.uuid4().hex
    token = uuid.uuid4().hex + uuid.uuid4().hex
    actions = queue.Queue()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(403)
                return
            action = self.path.lstrip("/")
            if action not in {"stop", "restart"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            actions.put(action)

        def log_message(self, *args):
            pass

    control_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=control_server.serve_forever, daemon=True).start()
    state = {"instance_id": instance, "pid": os.getpid(), "port": config["port"], "mode": config["mode"],
             "control_port": control_server.server_port, "control_token": token,
             "config_fingerprint": config_fingerprint(config)}
    environment = {**os.environ, "MUSIC_GENERATOR_DATA_DIR": str(DATA), "MUSIC_GENERATOR_INSTANCE_ID": instance,
                   "MUSIC_GENERATOR_CONTROL_PORT": str(control_server.server_port), "MUSIC_GENERATOR_CONTROL_TOKEN": token,
                   "MUSIC_GENERATOR_MODE": config["mode"]}
    environment["MUSIC_GENERATOR_ENGINE"] = "mock" if config["mode"] == "mock" else "acestep_cpp"
    environment["MUSIC_GENERATOR_SERVER_URL"] = config["server_url"] or f"http://127.0.0.1:{config['tunnel_port']}"
    environment["MUSIC_GENERATOR_LM_URL"] = ""
    if config.get("lm_model"):
        environment["MUSIC_GENERATOR_LM_MODEL"] = config["lm_model"]
    children = []
    logs = []
    web = None

    def spawn(command: list[str], name: str, env: dict = environment) -> subprocess.Popen:
        log = open(DATA / name, "ab")
        logs.append(log)
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, **hidden_options())
        children.append(child)
        return child

    def spawn_web() -> subprocess.Popen:
        # Dependencies may have been refreshed by the updater; select the venv again on restart.
        venv = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = str(venv) if venv.exists() else sys.executable
        return spawn([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(config["port"])], "server.log")

    try:
        if port_open(config["port"]):
            raise RuntimeError(f"Web port {config['port']} is already occupied")
        if config["mode"] == "remote" and config["ssh_host"]:
            if port_open(config["tunnel_port"]):
                raise RuntimeError(f"Tunnel port {config['tunnel_port']} is already occupied; choose another port")
            tunnel = spawn(["ssh", "-N", "-T", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                            "-L", f"127.0.0.1:{config['tunnel_port']}:127.0.0.1:{config['remote_port']}",
                            config["ssh_host"]], "ssh-tunnel.log")
            deadline = time.monotonic() + 15
            while not port_open(config["tunnel_port"]):
                if tunnel.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("SSH tunnel failed; inspect data/ssh-tunnel.log")
                time.sleep(.2)
        elif config["mode"] == "local":
            if port_open(config["tunnel_port"]):
                raise RuntimeError(f"Model port {config['tunnel_port']} is occupied; choose another port")
            executable = Path(config.get("local_engine", ROOT / "engine" / "build-cuda" / "Release" / "ace-server.exe"))
            models = Path(config.get("local_models", ROOT / "engine" / "models"))
            if not executable.is_file() or not models.is_dir():
                raise RuntimeError("Local engine/models missing. Run the Windows installer in local mode first.")
            model_env = dict(environment)
            if config.get("cuda_bin"):
                model_env["PATH"] = config["cuda_bin"] + os.pathsep + model_env.get("PATH", "")
            model = spawn([str(executable), "--host", "127.0.0.1", "--port", str(config["tunnel_port"]),
                           "--models", str(models), "--max-batch", "1"], "ace-server.log", env=model_env)
            deadline = time.monotonic() + 90
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{config['tunnel_port']}/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if model.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Local CUDA model server failed to become ready; inspect data/ace-server.log")
                time.sleep(.3)
        write_json(STATE, state)
        web = spawn_web()
        signal.signal(signal.SIGTERM, lambda *_: actions.put("stop"))
        signal.signal(signal.SIGINT, lambda *_: actions.put("stop"))
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("An owned service exited; inspect data/*.log")
            try:
                action = actions.get(timeout=.3)
            except queue.Empty:
                continue
            if action == "stop":
                break
            # Retain the owned model process and SSH tunnel during a web-only update.
            stop_child(web)
            children.remove(web)
            web = spawn_web()
        return 0
    finally:
        for child in reversed(children):
            stop_child(child)
        control_server.shutdown()
        control_server.server_close()
        for log in logs:
            log.close()
        if read_json(STATE).get("instance_id") == instance:
            STATE.unlink(missing_ok=True)


def start(config: dict) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    lock = DATA / "launcher.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("Another start is in progress. If it crashed, remove data/launcher.lock and retry.")
    os.close(descriptor)
    try:
        state = current_state()
        if state:
            if state.get("config_fingerprint") != config_fingerprint(config):
                raise RuntimeError("The app is already running with another connection configuration; stop it before changing its target, mode or ports")
            print(f"Already running: http://127.0.0.1:{state['port']}")
            if not config["no_browser"]:
                webbrowser.open(f"http://127.0.0.1:{state['port']}")
            return 0
        if port_open(config["port"]):
            raise RuntimeError(f"Port {config['port']} is occupied by another process; choose --port")
        log = open(DATA / "launcher.log", "ab")
        try:
            child = subprocess.Popen([sys.executable, "-m", "app.launcher", "run", "--config-json", json.dumps(config)],
                                     cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     **hidden_options(detached=True))
        finally:
            log.close()
        deadline = time.monotonic() + (120 if config["mode"] == "local" else 30)
        while time.monotonic() < deadline:
            state = current_state()
            if state:
                print(f"Running ({config['mode']}): http://127.0.0.1:{state['port']}")
                if not config["no_browser"]:
                    webbrowser.open(f"http://127.0.0.1:{state['port']}")
                return 0
            if child.poll() is not None:
                raise RuntimeError("Startup failed; inspect data/launcher.log and data/server.log")
            time.sleep(.2)
        # A supervisor with an unready web child still owns services. Ask it to clean up.
        pending = read_json(STATE)
        if pending.get("pid") == child.pid:
            try:
                control(pending, "stop")
                child.wait(timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                stop_child(child)
        else:
            stop_child(child)
        raise RuntimeError("Startup timed out; inspect data/launcher.log")
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--mode", choices=["mock", "remote", "local"])
    for key in ("server-url", "ssh-host"):
        start_parser.add_argument("--" + key)
    for key in ("port", "remote-port", "tunnel-port"):
        start_parser.add_argument("--" + key, type=int)
    start_parser.add_argument("--no-browser", action="store_true", default=None)
    commands.add_parser("stop")
    commands.add_parser("status")
    internal = commands.add_parser("run", help=argparse.SUPPRESS)
    internal.add_argument("--config-json", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return run(validate_config({**DEFAULTS, **json.loads(args.config_json)}))
        if args.command == "start":
            config = {**DEFAULTS, **read_json(DATA / "launcher.json")}
            config.update({k: v for k, v in vars(args).items() if k != "command" and v is not None})
            if args.server_url is not None:
                if args.mode in {"local", "mock"}:
                    raise ValueError("--server-url requires remote mode")
                config["mode"] = "remote"
                if args.ssh_host is None:
                    config["ssh_host"] = ""
            return start(validate_config(config))
        state = current_state()
        if args.command == "status":
            print(json.dumps({"running": bool(state), **{k: v for k, v in state.items() if k != "control_token"}}))
            return 0
        if not state:
            print("Not running; no process was terminated.")
            return 0
        # The web endpoint cancels any active remote job before signalling its owner.
        request = urllib.request.Request(f"http://127.0.0.1:{state['port']}/api/shutdown", data=b"{}", method="POST",
                                         headers={"X-Lang": "de", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 409:
                raise RuntimeError("The app is currently updating or shutting down. Wait before stopping it.") from error
            control(state, "stop")
        except (OSError, ValueError):
            control(state, "stop")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and STATE.exists():
            time.sleep(.2)
        if STATE.exists():
            raise RuntimeError("Shutdown is taking longer than expected; inspect data/launcher.log")
        print("Stopped.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
