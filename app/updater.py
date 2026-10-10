"""Updates aus dem GitHub-Repository: prüfen, holen, neu starten."""
import asyncio
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from . import db, lifecycle

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"
REPO_URL = "https://github.com/abartiggut/music-generator.git"
router = APIRouter(prefix="/api/update")


def tr(lang: str, de: str, en: str) -> str:
    return en if lang == "en" else de


def git(*args: str, timeout: int = 60) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # nie nach Passwort fragen
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {args[0]} fehlgeschlagen")
    return r.stdout.strip()


def _has_head() -> bool:
    """Git-Ordner mit mindestens einem Commit? (Falsch auch nach einer abgebrochenen Umstellung auf Git.)"""
    if not (ROOT / ".git").exists():
        return False
    try:
        git("rev-parse", "--verify", "--quiet", "HEAD")
        return True
    except RuntimeError:
        return False


def _status(lang: str = "de") -> dict:
    if not _has_head():
        raise RuntimeError(tr(lang, "ZIP-Installationen werden nicht automatisch überschrieben. Bitte den abartiggut-Fork in einen neuen Ordner klonen und die Bibliothek übernehmen.",
                              "ZIP installations cannot be updated automatically. Clone the abartiggut fork into a new folder and migrate your library."))
    _verify_repository(lang)
    git("fetch", "--quiet", "origin", BRANCH, timeout=30)
    remote = f"origin/{BRANCH}"
    behind = int(git("rev-list", "--count", f"HEAD..{remote}"))
    ahead = int(git("rev-list", "--count", f"{remote}..HEAD"))
    changes = git("log", f"HEAD..{remote}", "--format=%s", "-n", "15").splitlines() if behind else []
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    changed_files = git("diff", "--name-only", f"HEAD..{remote}").splitlines() if behind else []
    return {
        "current": git("rev-parse", "--short", "HEAD"), "latest": git("rev-parse", "--short", remote),
        "behind": behind, "ahead": ahead, "changes": changes, "dirty": dirty,
        # Neue acestep.cpp-Version oder neue Pakete: der Installer muss danach noch einmal laufen
        "needs_install": bool({"scripts/common.sh", "scripts/install-windows.ps1", "Install.ps1"} & set(changed_files)),
    }


def _verify_repository(lang: str = "de") -> None:
    origin = git("remote", "get-url", "origin").rstrip("/")
    accepted = {REPO_URL, REPO_URL.removesuffix(".git"), "git@github.com:abartiggut/music-generator.git",
                "ssh://git@github.com/abartiggut/music-generator.git"}
    if origin not in accepted:
        raise RuntimeError(tr(lang, "Updates sind nur für origin=abartiggut/music-generator erlaubt.",
                              "Updates require origin=abartiggut/music-generator."))
    if git("branch", "--show-current") != BRANCH:
        raise RuntimeError(tr(lang, "Automatische Updates sind nur auf dem main-Branch erlaubt. Eigene Entwicklungsbranches bitte mit Git aktualisieren.",
                              "Automatic updates require the main branch. Update development branches with Git."))


@router.get("/check")
async def check(x_lang: str = Header("de")):
    try:
        return {"ok": True, **await asyncio.to_thread(_status, x_lang)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _friendly(e, x_lang)}


def _friendly(e: Exception, lang: str = "de") -> str:
    msg = str(e) or e.__class__.__name__
    if isinstance(e, subprocess.TimeoutExpired):
        return tr(lang, "Keine Antwort von GitHub (Internetverbindung?).", "No response from GitHub (internet connection?).")
    if "Could not resolve" in msg or "unable to access" in msg:
        return tr(lang, "GitHub ist nicht erreichbar (Internetverbindung?).", "GitHub is not reachable (internet connection?).")
    return msg


def _apply(lang: str = "de") -> dict:
    s = _status(lang)
    if not s["behind"]:
        raise RuntimeError(tr(lang, "Du hast bereits die aktuelle Version.", "You already have the latest version."))
    if s["dirty"]:
        raise RuntimeError(tr(lang, "Im Programmordner gibt es eigene Änderungen an Dateien. Das Update würde sie überschreiben.", "There are local changes to files in the program folder. The update would overwrite them."))
    if s["ahead"]:
        raise RuntimeError(tr(lang, "Diese Installation hat eigene Commits, die nicht auf GitHub sind. Automatisch geht das nicht.", "This installation has its own commits that are not on GitHub. Not possible automatically."))
    # Recheck after the network request: editing files while checking must remain safe.
    _verify_repository(lang)
    if git("status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError(tr(lang, "Lokale Änderungen oder neue Dateien verhindern das Update.", "Local changes or untracked files prevent this update."))
    if int(git("rev-list", "--count", f"origin/{BRANCH}..HEAD")):
        raise RuntimeError(tr(lang, "Eigene Commits verhindern das automatische Update.", "Local commits prevent this automatic update."))
    if db.one("SELECT COUNT(*) AS n FROM songs WHERE status IN ('queued','running')")["n"] or lifecycle.analyses:
        raise RuntimeError(tr(lang, "Es laufen noch Songs oder eine Audioanalyse. Bitte erst fertig werden lassen.", "Songs or an audio analysis are still running. Wait for completion first."))
    before = git("rev-parse", "HEAD")
    git("merge", "--ff-only", "--quiet", f"origin/{BRANCH}", timeout=120)
    if {"pyproject.toml", "uv.lock"} & set(git("diff", "--name-only", before, "HEAD").splitlines()):
        subprocess.run([_uv_executable(), "sync", "--frozen", "--python", "3.12", "--project", str(ROOT), "--quiet"],
                       cwd=ROOT, check=True, timeout=300, env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv")})
    return {**s, "current": git("rev-parse", "--short", "HEAD")}


def _apply_nogit(s: dict) -> dict:
    raise RuntimeError("ZIP installations require a fresh Git clone; files are never force-overwritten.")


def _uv_executable() -> str:
    found = shutil.which("uv")
    if found:
        return found
    filename = "uv.exe" if os.name == "nt" else "uv"
    for directory in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        candidate = directory / filename
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("uv wurde nicht gefunden. Bitte Install.ps1 erneut ausführen.")


@router.post("/apply")
async def apply(request: Request, x_lang: str = Header()):
    if not lifecycle.runtime_info()["managed"] and sys.platform != "darwin":
        raise HTTPException(409, tr(x_lang, "Für Updates zuerst mit python -m app.launcher start starten.",
                                  "Start with python -m app.launcher start before applying updates."))
    try:
        lifecycle.begin_maintenance("update")
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error
    try:
        busy = db.one("SELECT COUNT(*) AS n FROM songs WHERE status IN ('queued','running')")["n"]
        if busy or lifecycle.analyses:
            raise HTTPException(409, tr(x_lang, "Es laufen noch Songs oder eine Audioanalyse. Bitte erst fertig werden lassen oder abbrechen.", "Songs or an audio analysis are still running. Wait or cancel them first."))
        res = await asyncio.to_thread(_apply, x_lang)
    except HTTPException:
        lifecycle.end_maintenance("update")
        raise
    except Exception as e:  # noqa: BLE001
        lifecycle.end_maintenance("update")
        raise HTTPException(400, _friendly(e, x_lang)) from e
    asyncio.get_running_loop().call_later(0.8, _restart, request.url.port or 8765)
    return {"ok": True, **res}


def _restart(port: int) -> None:
    """Restart only the supervised web child; keep the SSH tunnel and model alive."""
    if lifecycle.runtime_info()["managed"]:
        lifecycle.request_action("restart")
        return
    if sys.platform != "darwin":
        raise RuntimeError("Restart requires the launcher on this platform.")
    # The original Mac ON.command owns model processes separately. Restart only this web process.
    with open(db.DATA / "server.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "app.restart", "--parent-pid", str(os.getpid()), "--port", str(port)],
                         cwd=ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    os.kill(os.getpid(), signal.SIGTERM)
