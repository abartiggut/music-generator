# Gemeinsame Einstellungen für Install, Start und Stopp. Wird per "source" eingebunden.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="$ROOT/engine/acestep.cpp"
MODELS="$ENGINE/models"
DATA="$ROOT/data"
CONF="$DATA/engine.conf"          # vom Installer geschrieben: MODE, LM_FILE

PORT=8765         # Web-App
SYNTH_PORT=8085   # ace-server Synthese (Metal)
LM_PORT=8086      # ace-server Sprachmodell (nur im Modus "split", auf CPU)

# Getestete acestep.cpp-Version; neuere könnten die API ändern.
ACESTEP_REPO="https://github.com/ServeurpersoCom/acestep.cpp"
ACESTEP_REV="b7ba6d9ce2f19ca7627fb8f340032c3ebe8ae253"
HF_BASE="https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/main"

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

laeuft() { lsof -i :"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

# MODE=split  -> Sprachmodell auf CPU (Port 8086), Synthese auf Metal (Port 8085)
# MODE=single -> alles auf einem Metal-Server (Port 8085)
lade_conf() {
  MODE=split
  LM_FILE=""
  [ -f "$CONF" ] && . "$CONF"
}

# Terminal-Fenster nach getaner Arbeit selbst schließen (wie die übrigen APPS-Skripte).
fenster_schliessen() {
  local tty_now
  tty_now=$(tty 2>/dev/null) || return 0
  (sleep 1; osascript -e "tell application \"Terminal\" to close (first window whose tty is \"$tty_now\")" >/dev/null 2>&1) &
  disown
}
