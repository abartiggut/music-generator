"""SQLite-Speicher für Songs (Metadaten) und Einstellungen."""
import json
import math
import os
import sqlite3
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("MUSIC_GENERATOR_DATA_DIR", ROOT / "data")).resolve()
SONGS_DIR = DATA / "songs"
DB_PATH = DATA / "music.db"

def _engine_conf() -> dict:
    """Vom Installer geschrieben (data/engine.conf): MODE=single|split, LM_FILE=…"""
    conf = {}
    try:
        for line in (DATA / "engine.conf").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip()
    except OSError:
        pass
    return conf


_conf = _engine_conf()

DEFAULT_SETTINGS = {
    "engine": "acestep_cpp",           # "acestep_cpp" oder "mock"
    "server_url": "http://127.0.0.1:8085" if sys.platform == "darwin" else "http://127.0.0.1:18085",
    # Sprachmodell: eigener CPU-Server (Modus split) oder leer = gleicher Server wie Synthese (single)
    "lm_url": "http://127.0.0.1:8086" if sys.platform == "darwin" and _conf.get("MODE") != "single" else "",
    "lm_model": _conf.get("LM_FILE", ""),     # leer = erstes Sprachmodell im Modellordner
    "poll_interval": 1.5,
    "timeout_minutes": 30,
}

_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    SONGS_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


_con = connect()


def init():
    with _lock:
        _con.executescript(
            """
            CREATE TABLE IF NOT EXISTS songs (
                id          TEXT PRIMARY KEY,
                group_id    TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                finished_at TEXT,
                status      TEXT NOT NULL,          -- queued | running | done | error | cancelled
                message     TEXT,
                title       TEXT,
                caption     TEXT NOT NULL,
                lyrics      TEXT,
                seed        INTEGER NOT NULL,
                params      TEXT NOT NULL,          -- JSON: vollständige Anfrage
                result_meta TEXT,                   -- JSON: vom Modell ergänzte Werte (bpm, key, lyrics …)
                engine      TEXT,
                file        TEXT,
                favorite    INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_songs_status ON songs(status);
            CREATE INDEX IF NOT EXISTS idx_songs_group ON songs(group_id);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS folders (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
            """
        )
        # Ordner der Bibliothek (nur in der App; die Dateien bleiben, wo sie sind). NULL = unsortiert
        if "folder_id" not in [r["name"] for r in _con.execute("PRAGMA table_info(songs)")]:
            _con.execute("ALTER TABLE songs ADD COLUMN folder_id TEXT")
        # Nach einem Absturz hängengebliebene Jobs wieder einreihen
        _con.execute("UPDATE songs SET status='queued', message=NULL WHERE status='running'")
        _con.commit()


def execute(sql: str, args: tuple = ()) -> None:
    with _lock:
        _con.execute(sql, args)
        _con.commit()


def query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _con.execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def get_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    for r in query("SELECT key, value FROM settings"):
        s[r["key"]] = json.loads(r["value"])
    # Früher gespeicherte Standardadresse des CPU-Servers: im Ein-Server-Modus läuft dort nichts
    if _conf.get("MODE") == "single" and s["lm_url"].rstrip("/") == "http://127.0.0.1:8086":
        s["lm_url"] = ""
    for key in ("engine", "server_url", "lm_url", "lm_model"):
        value = os.environ.get("MUSIC_GENERATOR_" + key.upper())
        if value is not None:
            s[key] = value
    return s


def save_settings(values: dict) -> dict:
    current = get_settings()
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            raise ValueError(f"Unknown setting: {key}")
        if key in {"engine", "server_url", "lm_url", "lm_model"} and os.environ.get("MUSIC_GENERATOR_INSTANCE_ID") and value != current[key]:
            raise ValueError("Connection settings are controlled by the launcher. Stop the app and change data/launcher.json or run Install.ps1.")
        if key == "engine" and (not isinstance(value, str) or value not in {"mock", "acestep_cpp"}):
            raise ValueError("engine must be mock or acestep_cpp")
        if key in {"server_url", "lm_url"}:
            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError(f"{key} must be an HTTP(S) URL")
            if not value and key == "lm_url":
                continue
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError(f"{key} must be an HTTP(S) URL without credentials, query or fragment")
            _ = parts.port
        if key in {"poll_interval", "timeout_minutes"}:
            upper = 30 if key == "poll_interval" else 240
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not .1 <= value <= upper:
                raise ValueError(f"{key} must be between 0.1 and {upper}")
        if key == "lm_model" and (not isinstance(value, str) or len(value) > 256 or any(c in value for c in "\r\n")):
            raise ValueError("lm_model must be a short model filename")
    for k, v in values.items():
        if k not in DEFAULT_SETTINGS:
            continue
        if v == DEFAULT_SETTINGS[k]:
            # Vorgaben nicht festschreiben, sonst überstimmen sie später den Installer (engine.conf)
            execute("DELETE FROM settings WHERE key=?", (k,))
        else:
            execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )
    return get_settings()
