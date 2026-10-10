"""Anbindung an Modell-Server.

acestep.cpp (ace-server) arbeitet asynchron:
  POST /lm    -> {"id": ...}   LM ergänzt Metadaten, Lyrics und audio_codes
  POST /synth -> {"id": ...}   DiT + VAE rendern Audio
  GET  /job?id=X            -> {"status": ...}
  GET  /job?id=X&result=1   -> Ergebnis (/lm: JSON-Array, /synth: multipart/mixed)
"""
import asyncio
import email
import email.policy
import io
import json
import math
import random
import re
import struct
import time
import wave
from typing import Awaitable, Callable

import httpx

Progress = Callable[[str], Awaitable[None]]


def _fmt_time(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class EngineError(Exception):
    pass


class AudioCodesError(EngineError):
    """The LM completed, but its audio conditioning cannot produce a song."""


def _validate_audio_codes(codes) -> None:
    if not codes:
        raise AudioCodesError("Sprachmodell hat keine Audio-Codes geliefert. Bitte Modellserver und Sprachmodell-Konfiguration prüfen.")
    if isinstance(codes, str):
        if not re.fullmatch(r"\s*\d+(?:\s*,\s*\d+)*\s*", codes):
            raise AudioCodesError("Sprachmodell hat ungültige Audio-Codes geliefert.")
        values = [int(value) for value in codes.split(",")]
    elif isinstance(codes, list) and all(isinstance(value, int) and not isinstance(value, bool) for value in codes):
        values = codes
    else:
        raise AudioCodesError("Sprachmodell hat ungültige Audio-Codes geliefert.")
    if any(value < 0 or value >= 65536 for value in values):
        raise AudioCodesError("Sprachmodell hat ungültige Audio-Codes geliefert.")
    # ACE-Step uses five codes per second. Thirty seconds of an identical
    # short pattern is collapsed conditioning, even if /lm reports success.
    for period in range(1, 9):
        repeated = 0
        for index in range(period, len(values)):
            repeated = repeated + 1 if values[index] == values[index - period] else 0
            if repeated + period >= 150:
                raise AudioCodesError("Sprachmodell hat eine lange Audio-Code-Schleife erzeugt. Bitte die Generierung erneut starten.")


def _metadata_result(data, label: str) -> dict:
    """One request expects one nonempty metadata object, never arbitrary JSON."""
    message = f"{label} hat keine gültigen Metadaten geliefert. Bitte Modellserver und Sprachmodell-Konfiguration prüfen."
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict) or not data:
        raise EngineError(message)
    for key in ("caption", "lyrics", "keyscale", "vocal_language"):
        value = data.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise EngineError(message)
            try:
                value.encode("utf-8")
            except UnicodeError as error:
                raise EngineError(message) from error
    for key in ("bpm", "duration"):
        value = data.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise EngineError(message)
    return data


# Felder, die wir an ace-server durchreichen (Rest bleibt auf Server-Defaults)
ACE_FIELDS = {
    "caption", "lyrics", "bpm", "duration", "keyscale", "timesignature",
    "vocal_language", "seed", "lm_temperature", "lm_cfg_scale", "inference_steps",
    "guidance_scale", "output_format", "lm_model", "synth_model", "use_cot_caption",
}


# DiT-Modell: nur noch SFT (50 Schritte, klingt deutlich besser als turbo)
DIT_MODEL = "acestep-v15-sft-Q8_0.gguf"


class AceStepCpp:
    name = "acestep_cpp"

    def __init__(self, base_url: str, lm_url: str = "", poll_interval: float = 1.5, timeout_minutes: float = 30,
                 lm_model: str = ""):
        self.base = base_url.rstrip("/")
        # Auf Apple M4 liefert das LM unter Metal Unsinn (0 Codes) -> eigener CPU-Server
        self.lm_base = (lm_url or base_url).rstrip("/")
        self.poll = poll_interval
        self.timeout = timeout_minutes * 60
        # Liegen mehrere Sprachmodelle im Ordner, nähme der Server sonst das erste (alphabetisch)
        self.lm_model = lm_model
        self._job: tuple[str, str] | None = None   # (Server, Job-ID) des gerade laufenden Auftrags

    async def cancel(self) -> None:
        """Laufenden Auftrag beim Modellserver abbrechen, damit er nicht weiterrechnet."""
        if not self._job:
            return
        base, job_id = self._job
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(f"{base}/job", params={"id": job_id, "cancel": 1})
        except httpx.HTTPError:
            pass

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}/health")
            r.raise_for_status()
            if self.lm_base != self.base:
                try:
                    (await c.get(f"{self.lm_base}/health")).raise_for_status()
                except Exception as e:
                    raise EngineError(f"LM-Server {self.lm_base} nicht erreichbar") from e
            info = {"ok": True, "health": r.json()}
            try:
                p = await c.get(f"{self.base}/props")
                if p.status_code == 200:
                    info["props"] = p.json()
            except Exception:
                pass
            return info

    async def _wait(self, c: httpx.AsyncClient, base: str, job_id: str, label: str, start: float, progress: Progress) -> httpx.Response:
        self._job = (base, job_id)
        # start = Zeitpunkt des Gesamtauftrags (nicht dieser Phase) -> die Anzeige zählt einfach durch
        while True:
            r = await c.get(f"{base}/job", params={"id": job_id})
            r.raise_for_status()
            status = str(r.json().get("status", "")).lower()
            if status == "done":
                res = await c.get(f"{base}/job", params={"id": job_id, "result": 1})
                res.raise_for_status()
                return res
            if any(w in status for w in ("err", "fail", "cancel")):
                raise EngineError(f"{label} fehlgeschlagen: {r.text}")
            elapsed = int(time.monotonic() - start)
            if elapsed > self.timeout:
                await self.cancel()   # Modellserver nicht am alten Auftrag weiterrechnen lassen
                raise EngineError(f"{label}: Zeitüberschreitung nach {elapsed}s")
            await progress(_fmt_time(elapsed))
            await asyncio.sleep(self.poll)

    async def generate(self, params: dict, progress: Progress) -> tuple[bytes, str, dict]:
        req = {k: v for k, v in params.items() if k in ACE_FIELDS and v not in (None, "")}
        seed = req.get("seed")
        fixed_seed = isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0
        if fixed_seed:
            # ace-server randomises the LM independently unless lm_seed is explicit.
            req["lm_seed"] = seed
        req.setdefault("use_cot_caption", False)  # Prompt wörtlich übernehmen
        req["output_format"] = "wav16"            # 48 kHz / 16 Bit, verlustfrei
        req["synth_model"] = DIT_MODEL
        if self.lm_model:
            req["lm_model"] = self.lm_model
        start = time.monotonic()   # zählt über beide Phasen (Sprachmodell + Synthese) durch
        async with httpx.AsyncClient(timeout=60) as c:
            # 1) Sprachmodell: Songstruktur + Audio-Codes. A completed LM job
            # can still collapse into a code loop. Retry only this phase with
            # deterministic LM seeds; never render known-broken conditioning.
            lm_seed = req.get("lm_seed", random.randrange(2**32))
            for attempt in range(3):
                req["lm_seed"] = (lm_seed + attempt) % 2**32
                r = await c.post(f"{self.lm_base}/lm", json=req)
                if r.status_code >= 400:
                    raise EngineError(f"/lm: HTTP {r.status_code} {r.text[:300]}")
                res = await self._wait(c, self.lm_base, str(r.json()["id"]), "Sprachmodell", start, progress)
                try:
                    enriched = _metadata_result(res.json(), "Das Sprachmodell")
                except (ValueError, UnicodeError) as error:
                    raise EngineError("Das Sprachmodell hat ungültiges JSON geliefert. Bitte Modellserver und Sprachmodell-Konfiguration prüfen.") from error
                try:
                    _validate_audio_codes(enriched.get("audio_codes"))
                except AudioCodesError:
                    if attempt == 2:
                        raise
                    await progress(f"Audio-Codes unbrauchbar – neuer Versuch ({attempt + 2}/3)")
                    continue
                break
            enriched["output_format"] = req["output_format"]
            enriched["synth_model"] = req["synth_model"]
            if fixed_seed:
                enriched["seed"] = seed

            # 2) Synthese
            r = await c.post(f"{self.base}/synth", json=enriched)
            if r.status_code >= 400:
                raise EngineError(f"/synth: HTTP {r.status_code} {r.text[:300]}")
            res = await self._wait(c, self.base, str(r.json()["id"]), "Synthese", start, progress)
            audio, ext = _extract_audio(res)
        meta = {k: enriched.get(k) for k in ("bpm", "duration", "keyscale", "timesignature", "vocal_language", "lyrics", "caption")}
        meta.update(lm_seed=req["lm_seed"], lm_attempts=attempt + 1)
        return audio, ext, meta


    async def analyze(self, audio: bytes, filename: str) -> dict:
        """Song hochladen, Modell beschreibt Stil, Tempo, Tonart, Lyrics (/understand, läuft auf dem LM-Server)."""
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{self.lm_base}/understand", files={"audio": (filename, audio)})
            if r.status_code >= 400:
                raise EngineError(f"/understand: HTTP {r.status_code} {r.text[:300]}")
            res = await self._wait(c, self.lm_base, str(r.json()["id"]), "Analyse", time.monotonic(), lambda _msg: asyncio.sleep(0))
            data = _metadata_result(_extract_json(res), "Die Audioanalyse")
            if not {"caption", "lyrics", "bpm", "duration", "keyscale", "timesignature", "vocal_language"} & data.keys():
                raise EngineError("Die Audioanalyse hat keine auswertbaren Metadaten geliefert. Bitte Modellserver und Sprachmodell-Konfiguration prüfen.")
            return data


def _extract_json(res: httpx.Response):
    """/understand liefert wie /synth multipart/mixed: JSON-Teil (Metadaten) + Roh-Latents."""
    ctype = res.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        try:
            return res.json()
        except (ValueError, UnicodeError) as error:
            raise EngineError("Die Audioanalyse hat ungültiges JSON geliefert. Bitte Modellserver und Sprachmodell-Konfiguration prüfen.") from error
    if "multipart" not in ctype:
        raise EngineError(f"Unerwartete Antwort von /understand: {ctype}")
    msg = email.message_from_bytes(
        f"Content-Type: {ctype}\r\n\r\n".encode() + res.content, policy=email.policy.HTTP
    )
    for part in msg.iter_parts():
        if part.get_content_type().startswith("application/json"):
            try:
                return json.loads(part.get_payload(decode=True))
            except (ValueError, UnicodeError, TypeError) as error:
                raise EngineError("Die Audioanalyse hat ungültiges JSON geliefert. Bitte Modellserver und Sprachmodell-Konfiguration prüfen.") from error
    raise EngineError("Kein JSON-Teil in der /understand-Antwort gefunden")


def _extract_audio(res: httpx.Response) -> tuple[bytes, str]:
    ctype = res.headers.get("content-type", "")
    if ctype.startswith("audio/"):
        return res.content, _ext_for(ctype)
    if "multipart" not in ctype:
        raise EngineError(f"Unerwartete Antwort von /synth: {ctype}")
    msg = email.message_from_bytes(
        f"Content-Type: {ctype}\r\n\r\n".encode() + res.content, policy=email.policy.HTTP
    )
    for part in msg.iter_parts():
        pt = part.get_content_type()
        if pt.startswith("audio/"):
            return part.get_payload(decode=True), _ext_for(pt)
    raise EngineError("Kein Audio-Teil in der /synth-Antwort gefunden")


def _ext_for(ctype: str) -> str:
    return "mp3" if "mpeg" in ctype or "mp3" in ctype else "wav"


class MockEngine:
    """Erzeugt ein kurzes Akkord-Arpeggio, um die App ohne Modell zu testen."""
    name = "mock"

    async def health(self) -> dict:
        return {"ok": True, "health": {"status": "mock"}}

    async def cancel(self) -> None:
        pass

    async def analyze(self, audio: bytes, filename: str) -> dict:
        return {"caption": "warm analog synths, mock analysis", "lyrics": "[Instrumental]", "bpm": 92, "keyscale": "C major", "timesignature": "4", "vocal_language": "", "duration": 45}

    async def generate(self, params: dict, progress: Progress) -> tuple[bytes, str, dict]:
        rnd = random.Random(params["seed"])
        seconds = min(float(params.get("duration") or 12), 20.0)
        bpm = int(params.get("bpm") or rnd.choice([84, 96, 110, 124]))
        for i in range(4):
            await progress(_fmt_time(i))
            await asyncio.sleep(0.4)
        return _synth_wav(rnd, seconds, bpm), "wav", {"bpm": bpm, "duration": seconds, "keyscale": "C major"}


def _synth_wav(rnd: random.Random, seconds: float, bpm: int, sr: int = 22050) -> bytes:
    roots = rnd.sample([48, 50, 53, 55, 57, 60], 4)
    step = 60 / bpm / 2
    n = int(seconds * sr)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            idx = int(t / step)
            root = roots[(idx // 8) % 4]
            note = root + [0, 4, 7, 12, 7, 4, 0, 7][idx % 8]
            f = 440 * 2 ** ((note - 69) / 12)
            env = math.exp(-6 * (t - idx * step))
            s = 0.35 * env * math.sin(2 * math.pi * f * t) + 0.08 * math.sin(2 * math.pi * f / 2 * t)
            frames += struct.pack("<h", int(max(-1, min(1, s)) * 32000))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def make_engine(settings: dict):
    if settings.get("engine") == "mock":
        return MockEngine()
    return AceStepCpp(settings["server_url"], settings.get("lm_url", ""), settings["poll_interval"],
                      settings["timeout_minutes"], settings.get("lm_model", ""))
