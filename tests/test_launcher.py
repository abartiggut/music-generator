"""Real subprocess checks of the cross-platform launcher, on loopback ports only."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from test_api import FakeAceServer

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request_json(url, value=None, headers=None):
    request = urllib.request.Request(url, data=json.dumps(value).encode() if value is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="music-generator-launcher-")
        self.data = Path(self.temp.name)
        self.env = {**os.environ, "MUSIC_GENERATOR_DATA_DIR": str(self.data)}
        for key in ("MUSIC_GENERATOR_INSTANCE_ID", "MUSIC_GENERATOR_CONTROL_PORT", "MUSIC_GENERATOR_CONTROL_TOKEN",
                    "MUSIC_GENERATOR_MODE", "MUSIC_GENERATOR_ENGINE", "MUSIC_GENERATOR_SERVER_URL", "MUSIC_GENERATOR_LM_URL"):
            self.env.pop(key, None)
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.cli("stop", check=False)
        self.temp.cleanup()

    def cli(self, *args, check=True):
        process = subprocess.run([sys.executable, "-m", "app.launcher", *args], cwd=ROOT, env=self.env,
                                 capture_output=True, text=True, timeout=45)
        if check:
            self.assertEqual(process.returncode, 0, f"{process.stdout}\n{process.stderr}\n{self.logs()}")
        return process

    def logs(self):
        return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in self.data.glob("*.log"))

    def wait(self, predicate, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                value = predicate()
                if value:
                    return value
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        self.fail(f"Condition timed out\n{self.logs()}")

    def start(self, *args):
        return self.cli("start", "--port", str(self.port), "--no-browser", *args)

    def test_mock_start_status_authenticated_restart_shutdown(self):
        self.start("--mode", "mock")
        info = request_json(self.url + "/api/runtime")
        self.assertTrue(info["managed"])
        self.assertEqual(info["mode"], "mock")
        self.assertTrue(info["capabilities"]["restart"])
        self.assertTrue(info["connection_locked"])
        settings_change = urllib.request.Request(self.url + "/api/settings", method="PUT",
                                                 data=b'{"engine":"acestep_cpp"}',
                                                 headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as refusal:
            urllib.request.urlopen(settings_change, timeout=3)
        self.assertEqual(refusal.exception.code, 422)
        self.assertEqual(request_json(self.url + "/api/settings")["engine"], "mock")
        state = json.loads((self.data / "runtime.json").read_text())
        status = json.loads(self.cli("status").stdout)
        self.assertTrue(status["running"])
        self.assertNotIn("control_token", status)
        self.assertEqual(self.cli("start", "--mode", "mock", "--port", str(self.port), "--no-browser").returncode, 0)
        self.assertEqual(json.loads((self.data / "runtime.json").read_text())["pid"], state["pid"])

        control_url = f"http://127.0.0.1:{state['control_port']}"
        with self.assertRaises(urllib.error.HTTPError) as refusal:
            request_json(control_url + "/stop", {})
        self.assertEqual(refusal.exception.code, 403)
        self.assertTrue(request_json(self.url + "/api/health")["ok"])

        # Prove that a restart replaces the owned web process and preserves its DB.
        folder = request_json(self.url + "/api/folders", {"name": "Survives restart"})
        request_json(control_url + "/restart", {}, {"Authorization": "Bearer " + state["control_token"]})

        def restarted():
            log = (self.data / "server.log").read_text(encoding="utf-8", errors="replace")
            pids = re.findall(r"Started server process \[(\d+)\]", log)
            return len(set(pids)) >= 2 and request_json(self.url + "/api/runtime")["instance_id"] == info["instance_id"]

        self.wait(restarted)
        self.assertIn(folder["id"], [f["id"] for f in request_json(self.url + "/api/folders")["folders"]])
        self.assertEqual(request_json(self.url + "/api/shutdown", {}, {"x-lang": "de"}), {"ok": True})
        self.wait(lambda: not (self.data / "runtime.json").exists())
        self.assertFalse(json.loads(self.cli("status").stdout)["running"])

    def test_stale_state_never_terminates_unrelated_pid(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with FakeAceServer() as server:
                state = {"pid": unrelated.pid, "port": server.server.server_port,
                         "instance_id": "stale-identity", "control_port": server.server.server_port,
                         "control_token": "stale-token"}
                (self.data / "runtime.json").write_text(json.dumps(state))
                self.assertFalse(json.loads(self.cli("status").stdout)["running"])
                self.assertIn("no process", self.cli("stop").stdout.lower())
                self.assertIsNone(unrelated.poll())
                self.assertEqual(server.requests, [])
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)
            (self.data / "runtime.json").unlink(missing_ok=True)

    def test_occupied_web_port_preserves_existing_service(self):
        with FakeAceServer() as server:
            self.port = server.server.server_port
            result = self.cli(
                "start", "--mode", "mock", "--port", str(self.port), "--no-browser", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("occupied", result.stderr)
            self.assertEqual(request_json(server.url + "/health")["status"], "ready")
            self.assertFalse((self.data / "runtime.json").exists())

    def test_remote_direct_url_generates_through_http(self):
        with FakeAceServer() as server:
            # An explicit URL selects direct remote mode without an implicit SSH tunnel.
            self.start("--server-url", server.url)
            self.assertEqual(request_json(self.url + "/api/runtime")["mode"], "remote")
            settings = request_json(self.url + "/api/settings")
            self.assertEqual(settings["engine"], "acestep_cpp")
            self.assertEqual(settings["server_url"], server.url)
            # A new target on the same UI port must not silently reuse the old server.
            with FakeAceServer() as other_server:
                refused = self.cli("start", "--mode", "remote", "--ssh-host", "", "--server-url",
                                   other_server.url, "--port", str(self.port), "--no-browser", check=False)
                self.assertNotEqual(refused.returncode, 0)
                self.assertEqual(request_json(self.url + "/api/settings")["server_url"], server.url)
            sid = request_json(self.url + "/api/generate", {"prompt": "Remote test", "seed": 42})["ids"][0]
            def finished():
                song = request_json(self.url + f"/api/songs/{sid}")
                return song if song["status"] in {"done", "error"} else None

            song = self.wait(finished)
            self.assertEqual(song["status"], "done", song)
            self.cli("stop")
            # No remote stop request or process signal is issued; fixture remains reachable.
            self.assertEqual(request_json(server.url + "/health")["status"], "ready")

    def test_saved_config_and_invalid_config(self):
        (self.data / "launcher.json").write_text(json.dumps({"mode": "mock", "port": self.port,
                                                           "no_browser": True}))
        self.cli("start")
        self.assertEqual(request_json(self.url + "/api/runtime")["mode"], "mock")
        self.cli("stop")
        result = self.cli("start", "--mode", "remote", "--ssh-host", "-oops", check=False)
        self.assertNotEqual(result.returncode, 0)
        result = self.cli("start", "--port", "0", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.data / "runtime.json").exists())


if __name__ == "__main__":
    unittest.main()
