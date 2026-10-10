"""Authenticated loopback control for the supervisor that owns this web process."""
import json
import os
import sys
import urllib.request

maintenance = ""
analyses = 0


def begin_maintenance(action: str) -> None:
    global maintenance
    if maintenance:
        raise RuntimeError("Die App wird bereits aktualisiert oder beendet. Bitte warten.")
    maintenance = action


def end_maintenance(action: str) -> None:
    global maintenance
    if maintenance == action:
        maintenance = ""


def runtime_info() -> dict:
    managed = bool(os.environ.get("MUSIC_GENERATOR_INSTANCE_ID"))
    return {
        "platform": sys.platform,
        "managed": managed,
        "instance_id": os.environ.get("MUSIC_GENERATOR_INSTANCE_ID", ""),
        "mode": os.environ.get("MUSIC_GENERATOR_MODE", "direct"),
        "maintenance": maintenance,
        "capabilities": {"shutdown": managed or sys.platform == "darwin",
                         "restart": managed or sys.platform == "darwin",
                         "update": managed or sys.platform == "darwin"},
    }


def request_action(action: str) -> None:
    if action not in {"stop", "restart"} or not runtime_info()["managed"]:
        raise RuntimeError("Start the app with python -m app.launcher start first.")
    req = urllib.request.Request(
        f"http://127.0.0.1:{int(os.environ['MUSIC_GENERATOR_CONTROL_PORT'])}/{action}",
        data=b"{}", method="POST",
        headers={"Authorization": "Bearer " + os.environ["MUSIC_GENERATOR_CONTROL_TOKEN"],
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        json.load(response)
