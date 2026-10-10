"""Exercise queue and downloads with isolated data, never the user's library."""
import asyncio
import atexit
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# db connects at import time. This MUST precede importing any app module.
_import_data = tempfile.TemporaryDirectory(prefix="music-generator-tests-")
os.environ["MUSIC_GENERATOR_DATA_DIR"] = _import_data.name

from fastapi.testclient import TestClient
from app import db, main, updater


def _cleanup():
    db._con.close()
    _import_data.cleanup()


atexit.register(_cleanup)


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22050)
        output.writeframes(b"\0\0" * 2205)
    return stream.getvalue()


class FakeAceServer:
    """Small real HTTP fixture for the ace-server protocol, no GPU or network."""
    def __init__(self):
        self.requests = []
        self.missing_codes = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def send(self, value, content_type="application/json"):
                body = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, payload))
                self.send({"id": "lm" if self.path == "/lm" else "synth"})

            def do_GET(self):
                if self.path.startswith("/job"):
                    if "result=1" not in self.path:
                        self.send({"status": "done"})
                    elif "id=lm" in self.path:
                        self.send([{"audio_codes": [] if owner.missing_codes else [1, 2, 3],
                                    "caption": "fixture", "bpm": 92}])
                    else:
                        self.send(wav_bytes(), "audio/wav")
                elif self.path == "/props":
                    self.send({"models": []})
                else:
                    self.send({"status": "ready"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="music-generator-api-")
        self.data = Path(self.temp.name)
        self.original_con = db._con
        self.paths = patch.multiple(db, DATA=self.data, SONGS_DIR=self.data / "songs",
                                    DB_PATH=self.data / "music.db")
        self.paths.start()
        db._con = db.connect()
        self.settings = patch.dict(db.DEFAULT_SETTINGS, engine="mock", lm_url="")
        self.settings.start()
        main._wakeup = asyncio.Event()
        main._running.clear()
        self.client = TestClient(main.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        db._con.close()
        db._con = self.original_con
        self.settings.stop()
        self.paths.stop()
        self.temp.cleanup()

    def wait_song(self, sid, statuses=("done", "error", "cancelled"), timeout=12):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            song = self.client.get(f"/api/songs/{sid}").json()
            if song["status"] in statuses:
                return song
            time.sleep(0.05)
        self.fail(f"Song {sid} never reached {statuses}: {song}")

    def generate(self, **overrides):
        response = self.client.post("/api/generate", json={"prompt": "Warm synthesizer", "duration": 0.1,
                                                         "seed": 100, **overrides})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_variants_wav_favorites_and_zip(self):
        folder = self.client.post("/api/folders", json={"name": "Test"}).json()
        result = self.generate(variants=2, folder_id=folder["id"], title="Demo")
        songs = [self.wait_song(sid) for sid in result["ids"]]
        self.assertEqual([s["status"] for s in songs], ["done", "done"])
        self.assertEqual([s["seed"] for s in songs], [100, 101])
        self.assertTrue(all(s["group_id"] == result["group_id"] for s in songs))
        listed = self.client.get("/api/songs", params={"group": result["group_id"]}).json()
        self.assertEqual({s["letter"] for s in listed}, {"A", "B"})
        for sid in result["ids"]:
            response = self.client.get(f"/api/songs/{sid}/audio", params={"download": True})
            self.assertIn("attachment", response.headers["content-disposition"])
            with wave.open(io.BytesIO(response.content)) as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertGreater(audio.getnframes(), 0)
        self.client.patch(f"/api/songs/{result['ids'][0]}", json={"favorite": True})
        self.assertEqual(len(self.client.get("/api/songs?favorites=true").json()), 1)
        archive = self.client.get("/api/download", params={"folder": folder["id"]})
        self.assertEqual(archive.status_code, 200, archive.text)
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            self.assertEqual(len(bundle.namelist()), 2)
            self.assertEqual(len(set(bundle.namelist())), 2)
            self.assertTrue(all(bundle.read(name).startswith(b"RIFF") for name in bundle.namelist()))
        self.assertEqual(list(self.data.glob("mg-*.zip")), [])

    def test_cancel_running_and_queued_then_retry(self):
        ids = self.generate(variants=2)["ids"]
        self.wait_song(ids[0], ("running",))
        self.assertTrue(self.client.delete(f"/api/songs/{ids[1]}").json()["cancelled"])
        self.assertTrue(self.client.delete(f"/api/songs/{ids[0]}").json()["cancelled"])
        for sid in ids:
            self.assertEqual(self.wait_song(sid)["status"], "cancelled")
        self.client.post(f"/api/songs/{ids[0]}/retry")
        self.assertEqual(self.wait_song(ids[0])["status"], "done")
        self.assertEqual(self.client.get(f"/api/songs/{ids[1]}").json()["status"], "cancelled")

    def test_invalid_settings_are_atomic(self):
        before = self.client.get("/api/settings").json()
        for values in ({"engine": "bad"}, {"server_url": "file:///private"},
                       {"server_url": "http://"}, {"poll_interval": 0}, {"poll_interval": "nope"},
                       {"timeout_minutes": -1}, {"lm_url": "ssh://gpu-server"}):
            with self.subTest(values=values):
                self.assertEqual(self.client.put("/api/settings", json=values).status_code, 422)
                self.assertEqual(self.client.get("/api/settings").json(), before)
        # A partially valid object must not save the first field before rejecting the second.
        self.assertEqual(self.client.put("/api/settings", json={"engine": "acestep_cpp",
                                                               "poll_interval": -5}).status_code, 422)
        self.assertEqual(self.client.get("/api/settings").json(), before)

    def test_remote_protocol_and_error_retry(self):
        with FakeAceServer() as server:
            response = self.client.put("/api/settings", json={"engine": "acestep_cpp",
                                                                "server_url": server.url, "lm_url": "",
                                                                "poll_interval": 0.1})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(self.client.get("/api/health").json()["ok"])
            server.missing_codes = True
            sid = self.generate()["ids"][0]
            self.assertEqual(self.wait_song(sid)["status"], "error")
            server.missing_codes = False
            self.client.post(f"/api/songs/{sid}/retry")
            song = self.wait_song(sid)
            self.assertEqual(song["status"], "done", song)
            self.assertEqual(song["engine"], "acestep_cpp")
            lm_payload = next(payload for route, payload in server.requests if route == "/lm")
            self.assertEqual(lm_payload["seed"], 100)
            self.assertEqual(lm_payload["output_format"], "wav16")
            self.assertEqual(lm_payload["lyrics"], "[Instrumental]")
            self.assertTrue(any(route == "/synth" for route, _ in server.requests))

    def test_invalid_generation_and_empty_download(self):
        self.assertEqual(self.client.post("/api/generate", json={"variants": 0}).status_code, 422)
        self.assertEqual(self.client.post("/api/generate", json={"prompt": ""}).status_code, 422)
        self.assertEqual(self.client.get("/api/download").status_code, 404)
        self.assertEqual(self.client.get("/api/songs/missing").status_code, 404)

    def test_unmanaged_lifecycle_actions_do_not_spawn_processes(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main.sys, "platform", "win32"), \
                patch.object(main.subprocess, "Popen") as spawn:
            self.assertFalse(self.client.get("/api/runtime").json()["managed"])
            self.assertEqual(self.client.post("/api/shutdown", headers={"x-lang": "de"}).status_code, 409)
            self.assertEqual(self.client.post("/api/update/apply", headers={"x-lang": "de"}).status_code, 409)
            spawn.assert_not_called()

    def test_update_blocks_generation_and_recovers_after_failure(self):
        entered, release = threading.Event(), threading.Event()
        responses = []

        def paused_update(_lang):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test did not release the paused updater")
            raise RuntimeError("Offline update fixture failure")

        def submit_update():
            responses.append(self.client.post("/api/update/apply", headers={"x-lang": "de"}))

        with patch.object(main.lifecycle, "runtime_info", return_value={"managed": True}), \
                patch.object(updater, "_apply", side_effect=paused_update):
            thread = threading.Thread(target=submit_update)
            thread.start()
            try:
                self.assertTrue(entered.wait(timeout=5), "Update never entered the fixture")
                blocked = self.client.post("/api/generate", json={"prompt": "During update"})
                self.assertEqual(blocked.status_code, 409, blocked.text)
                self.assertEqual(self.client.get("/api/songs").json(), [])
                analysis = self.client.post("/api/analyze", files={"audio": ("test.wav", wav_bytes(), "audio/wav")})
                self.assertEqual(analysis.status_code, 409, analysis.text)
            finally:
                release.set()
                thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(responses), 1)
            self.assertEqual(responses[0].status_code, 400)
        # A failed update must unlock the queue again.
        self.assertEqual(self.client.post("/api/generate", json={"prompt": "After failure",
                                                                "duration": .1}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
