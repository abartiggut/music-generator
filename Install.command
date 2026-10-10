#!/bin/bash
# Music Generator – Installer für macOS.
# Prüft den Mac, installiert was fehlt, lädt das passende Modell und startet die App.
# Kann jederzeit erneut gestartet werden (z. B. nach "git pull"): Erledigtes wird übersprungen.
#
# Optionen:  --yes        keine Rückfragen, Empfehlung übernehmen
#            --lm SIZE    Sprachmodell erzwingen: 0.6B, 1.7B oder 4B
#            --no-start   App am Ende nicht starten
source "$(dirname "$0")/scripts/common.sh"
cd "$ROOT" || exit 1

AUTO=0; START=1; LM_SIZE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) AUTO=1 ;;
    --no-start) START=0 ;;
    --lm) LM_SIZE="$2"; shift ;;
  esac
  shift
done

abbruch() {
  echo ""; echo "✗ $1"
  [ "$AUTO" = 1 ] || read -n 1 -s -r -p "Beliebige Taste drücken zum Schließen..."
  exit 1
}
schritt() { echo ""; echo "▸ $1"; }
ja() {   # Rückfrage mit Enter = ja
  [ "$AUTO" = 1 ] && return 0
  local a; read -r -p "$1 [Enter = ja, n = nein] " a
  [ -z "$a" ] || [[ "$a" =~ ^[jJyY] ]]
}

mkdir -p "$DATA"
echo "═══════════════════════════════════════════"
echo "  MUSIC GENERATOR · Installation"
echo "═══════════════════════════════════════════"

# --- 1. Mac prüfen ------------------------------------------------------------
schritt "Mac prüfen"
ARCH=$(uname -m)
CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null)
RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
FREE_GB=$(df -g "$ROOT" | awk 'NR==2 {print $4}')
echo "  Chip:        $CHIP ($ARCH)"
echo "  Arbeitsspeicher: $RAM_GB GB"
echo "  macOS:       $(sw_vers -productVersion)"
echo "  Frei auf der Festplatte: $FREE_GB GB"

if [ "$ARCH" != "arm64" ]; then
  echo ""
  echo "  Hinweis: Intel-Mac. Getestet ist nur Apple Silicon (M1–M4); es kann sehr langsam sein."
  ja "  Trotzdem fortfahren?" || abbruch "Abgebrochen."
fi

# --- 2. Modellgröße wählen ------------------------------------------------------
if   [ "$RAM_GB" -lt 12 ]; then EMPF="0.6B"
elif [ "$RAM_GB" -lt 24 ]; then EMPF="1.7B"
else                            EMPF="4B"
fi
if [ -z "$LM_SIZE" ]; then
  LM_SIZE="$EMPF"
  if [ "$AUTO" != 1 ]; then
    echo ""
    echo "  Sprachmodell (plant Aufbau, Tempo, Tonart; größer = bessere Songs, mehr Speicher):"
    echo "    1) 0.6B  – 0,7 GB, für 8 GB Arbeitsspeicher"
    echo "    2) 1.7B  – 2,0 GB, für 16 GB"
    echo "    3) 4B    – 4,5 GB, ab 24 GB"
    read -r -p "  Auswahl [Enter = $EMPF empfohlen] " a
    case "$a" in 1) LM_SIZE="0.6B" ;; 2) LM_SIZE="1.7B" ;; 3) LM_SIZE="4B" ;; esac
  fi
fi
case "$LM_SIZE" in 0.6B|1.7B|4B) ;; *) abbruch "Unbekannte Modellgröße: $LM_SIZE (erlaubt: 0.6B, 1.7B, 4B)" ;; esac
LM_FILE="acestep-5Hz-lm-${LM_SIZE}-Q8_0.gguf"
echo "  → Sprachmodell $LM_SIZE, Klangmodell SFT (hohe Qualität)"

# Dateien + Größe in MB (für die Speicherplatz-Prüfung)
FILES="vae-BF16.gguf:340 Qwen3-Embedding-0.6B-Q8_0.gguf:780 acestep-v15-sft-Q8_0.gguf:2550"
case "$LM_SIZE" in 0.6B) FILES="$FILES $LM_FILE:710" ;; 1.7B) FILES="$FILES $LM_FILE:1980" ;; 4B) FILES="$FILES $LM_FILE:4460" ;; esac
NEED_MB=0
for e in $FILES; do [ -f "$MODELS/${e%%:*}" ] || NEED_MB=$(( NEED_MB + ${e##*:} )); done
NEED_GB=$(( (NEED_MB + 1023) / 1024 + 3 ))   # + Build, Python und etwas Platz für Songs
echo "  Download: $(( (NEED_MB + 1023) / 1024 )) GB · benötigt insgesamt etwa $NEED_GB GB frei"
[ "$FREE_GB" -ge "$NEED_GB" ] || abbruch "Zu wenig Speicherplatz: $FREE_GB GB frei, etwa $NEED_GB GB nötig."
ja "  Installation starten?" || abbruch "Abgebrochen."

# --- 3. Werkzeuge -------------------------------------------------------------
schritt "Apple-Entwicklerwerkzeuge (Compiler, git)"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install >/dev/null 2>&1
  abbruch "Es öffnet sich ein Apple-Fenster zur Installation der Entwicklerwerkzeuge. Bitte dort bestätigen und danach 'Install' erneut starten."
fi
echo "  vorhanden"

schritt "uv (Python-Umgebung)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh || abbruch "uv konnte nicht installiert werden."
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

schritt "cmake (zum Bauen des Modellservers)"
if ! command -v cmake >/dev/null 2>&1; then
  uv tool install cmake || abbruch "cmake konnte nicht installiert werden."
fi
cmake --version | head -1

schritt "Python-Pakete der App"
uv sync --quiet || abbruch "Python-Pakete konnten nicht installiert werden."
echo "  ok"

# --- 4. Modellserver (acestep.cpp) ---------------------------------------------
schritt "Modellserver acestep.cpp ($ACESTEP_REV)"
if [ ! -d "$ENGINE/.git" ]; then
  mkdir -p "$ROOT/engine"
  git clone --quiet "$ACESTEP_REPO" "$ENGINE" || abbruch "Download von acestep.cpp fehlgeschlagen."
fi
( cd "$ENGINE" \
  && { git cat-file -e "$ACESTEP_REV^{commit}" 2>/dev/null || git fetch --quiet origin; } \
  && git checkout --quiet "$ACESTEP_REV" \
  && git submodule update --init --recursive --quiet ) || abbruch "acestep.cpp konnte nicht auf Version $ACESTEP_REV gebracht werden."

# The binary reports a short build hash; checkout remains pinned to the full commit.
if "$ENGINE/build/ace-server" --help 2>&1 | head -1 | grep -q "${ACESTEP_REV:0:7}"; then
  echo "  bereits gebaut"
else
  echo "  wird gebaut (dauert einige Minuten) …"
  ( cd "$ENGINE" && ./buildcpu.sh ) > "$DATA/build.log" 2>&1 || abbruch "Bauen fehlgeschlagen, Details in data/build.log"
  echo "  fertig"
fi

# --- 5. Modelle -----------------------------------------------------------------
schritt "Modelle laden"
mkdir -p "$MODELS"
for e in $FILES; do
  f="${e%%:*}"
  if [ -f "$MODELS/$f" ]; then echo "  ✓ $f"; continue; fi
  echo "  ↓ $f"
  curl -L --fail -C - --progress-bar -o "$MODELS/$f.part" "$HF_BASE/$f" \
    && mv "$MODELS/$f.part" "$MODELS/$f" || abbruch "Download von $f fehlgeschlagen. Install erneut starten setzt den Download fort."
done

# --- 6. Grafikchip testen ------------------------------------------------------
# Auf manchen Chips (z. B. M4) rechnet das Sprachmodell unter Metal falsch.
# Dann läuft es auf der CPU (Modus "split"), sonst reicht ein Server (Modus "single").
schritt "Grafikchip testen"
OLD_MODE=""; OLD_LM=""; OLD_REV=""
[ -f "$CONF" ] && { OLD_MODE=$(sed -n 's/^MODE=//p' "$CONF"); OLD_LM=$(sed -n 's/^LM_FILE=//p' "$CONF"); OLD_REV=$(sed -n 's/^TESTED_REV=//p' "$CONF"); }
if [ -n "$OLD_MODE" ] && [ "$OLD_LM" = "$LM_FILE" ] && [ "$OLD_REV" = "$ACESTEP_REV" ]; then
  MODE="$OLD_MODE"
  echo "  schon getestet: Modus $MODE"
else
  TEST_PORT=8099
  laeuft "$TEST_PORT" && abbruch "Port $TEST_PORT ist belegt, bitte später erneut versuchen."
  "$ENGINE/build/ace-server" --host 127.0.0.1 --port "$TEST_PORT" --models "$MODELS" --max-batch 1 \
    > "$DATA/selftest.log" 2>&1 &
  TEST_PID=$!
  for _ in $(seq 1 120); do curl -s "http://127.0.0.1:$TEST_PORT/health" >/dev/null && break; sleep 0.5; done
  echo "  Sprachmodell probeweise auf Metal (kann 1–2 Minuten dauern) …"
  if uv run python scripts/metal_selftest.py "$TEST_PORT" "$LM_FILE"; then MODE=single; else MODE=split; fi
  kill "$TEST_PID" 2>/dev/null; wait "$TEST_PID" 2>/dev/null
  echo "  → Modus $MODE"
fi
cat > "$CONF" <<EOF
MODE=$MODE
LM_FILE=$LM_FILE
TESTED_REV=$ACESTEP_REV
EOF

# --- 7. Start-/Stopp-Symbole ----------------------------------------------------
schritt "Start- und Stopp-Symbole einrichten"
bash "$ROOT/scripts/symbole.sh"
echo "  ok"

# --- Fertig ---------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════"
echo "  Fertig. Starten mit 'Music Generator ON',"
echo "  beenden mit 'Music Generator OFF'."
echo "═══════════════════════════════════════════"
if [ "$START" = 1 ]; then
  exec "$ROOT/Music Generator ON.command"
fi
