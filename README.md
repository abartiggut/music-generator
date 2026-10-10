<p align="center">
  <a href="https://github.com/abartiggut">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/branding/abartiggut-on-dark.svg">
      <source media="(prefers-color-scheme: light)" srcset="assets/branding/abartiggut-on-light.svg">
      <img src="assets/branding/abartiggut-on-light.svg" alt="abartiggut – Steinbock mit Wortmarke" width="280">
    </picture>
  </a>
</p>

# Music Generator – Windows-Version von abartiggut

> **Windows-Fork:** Dieses Repository ist ein Fork von
> [rabbitfiremediacreation/music-generator](https://github.com/rabbitfiremediacreation/music-generator).
> **abartiggut hat diesen Fork für Windows angepasst, damit auch Nutzerinnen und
> Nutzer von Windows 10/11 das Tool verwenden können.** Die Windows-Erweiterungen
> werden in diesem Repository gepflegt.

Eigene Songs mit einer lokalen oder entfernten Musik-Engine erzeugen.
Web-Oberfläche für [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) über
[acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp) (CUDA, Metal oder CPU).

Dieser [abartiggut-Fork](https://github.com/abartiggut/music-generator) ergänzt native
Windows-Installation, kontrollierte Start-/Stoppsteuerung und einen SSH-Tunnel zu
einem Linux-GPU-Rechner. Ursprung: [rabbitfiremediacreation/music-generator](https://github.com/rabbitfiremediacreation/music-generator).

## Windows-Version herunterladen

**[Windows-Version als ZIP herunterladen](https://github.com/abartiggut/music-generator/archive/refs/heads/main.zip)**

Das ZIP enthält den Quellcode und den Windows-Installer `Install.cmd` für Windows
10/11. ZIP entpacken und den gewünschten Betriebsmodus gemäss der
**[Windows-Anleitung](docs/windows.md)** installieren. Die Musik-Engine und die
Modelle werden separat eingerichtet; Voraussetzungen für eine lokale NVIDIA-GPU
oder einen entfernten GPU-Server stehen in der Anleitung.

Für Installation und spätere Updates über Git:

```powershell
git clone https://github.com/abartiggut/music-generator.git
cd music-generator
.\Install.cmd
```

Standard: Windows-Web-App mit einer bereits eingerichteten Engine auf **GPU-Server**,
erreichbar über den vorhandenen SSH-Alias `gpu-server`. Die App öffnet
`http://127.0.0.1:8765`; der Tunnel verbindet die Engine auf Port `18085`.
Ein anderer Rechner kann mit `-SshHost` gewählt werden. Der Windows-Installer
installiert keine Software auf dem GPU-Rechner.

Ohne GPU und ohne SSH zum Ausprobieren:

```powershell
.\Install.cmd -Mode Mock
```

Danach per Doppelklick **Music Generator ON.cmd** starten und
**Music Generator OFF.cmd** stoppen. Die entfernte Engine wird separat verwaltet.
Der Mock-Modus erzeugt Testklänge, keine KI-Musik.

Weitere Modi, CUDA-Voraussetzungen, GPU-Server-Einrichtung, Tests und Fehlerbehebung:
**[Windows-Anleitung](docs/windows.md)**.
Ergebnisse der echten Blackwell- und Windows-Tests: **[Testbericht](docs/test-report.md)**.

Die vorhandene **[Installationsanleitung.pdf](Installationsanleitung.pdf)** beschreibt
die ursprüngliche Mac-Version.

## Installation auf dem Mac

Voraussetzungen: Mac mit Apple Silicon (M1–M4), mindestens 8 GB Arbeitsspeicher, 7–11 GB frei.

```bash
git clone https://github.com/abartiggut/music-generator.git ~/MusicGenerator
open ~/MusicGenerator/Install.command
```

Der Installer

1. prüft Chip, Arbeitsspeicher und freien Platz,
2. schlägt das passende Sprachmodell vor (0.6B unter 12 GB, 1.7B bis 24 GB, 4B darüber),
3. installiert was fehlt: Apple-Entwicklerwerkzeuge, `uv`, `cmake` (ohne Homebrew, ohne Passwort),
4. baut acestep.cpp in der getesteten Version (`b7ba6d9`),
5. lädt nur die benötigten Modelle (fortsetzbar),
6. testet, ob das Sprachmodell auf dem Grafikchip richtig rechnet (sonst CPU, siehe unten),
7. richtet die Symbole für **Music Generator ON / OFF** ein und startet die App.

Er kann jederzeit erneut laufen; Erledigtes wird übersprungen.
Optionen: `--yes` (keine Rückfragen), `--lm 0.6B|1.7B|4B`, `--no-start`.

## Benutzen

- **Music Generator ON** startet Modellserver und App und öffnet http://localhost:8765
- **Music Generator OFF** beendet alles und schließt die Browser-Tabs

## Aktualisieren

In der App: Zahnrad › **Nach Updates suchen** › **Jetzt aktualisieren** (holt die neue Fassung von GitHub und startet die App neu; ändert sich acestep.cpp, weist sie auf den Installer hin). Oder von Hand:

```bash
cd ~/MusicGenerator && git pull
open Install.command
```

Songs und Einstellungen in `data/` bleiben erhalten.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `Install.command` | Installer |
| `Music Generator ON/OFF.command` | Start und Stopp |
| `scripts/common.sh` | gemeinsame Pfade, Ports, acestep.cpp-Version |
| `scripts/metal_selftest.py` | Grafikchip-Test des Installers |
| `app/` | FastAPI-Backend: Queue, Bibliothek, Anbindung an ace-server |
| `static/` | Oberfläche |
| `docs/anleitung/` | Quelle der Installationsanleitung. `capture.py` fotografiert die laufende App (`uv run --with websockets python docs/anleitung/capture.py`), `build_pdf.py` baut daraus das PDF (`uv run --with reportlab python docs/anleitung/build_pdf.py Installationsanleitung.pdf`) |
| `engine/` | acestep.cpp und Modelle (vom Installer, nicht im Repo) |
| `data/` | Songs, Datenbank, Logs, `engine.conf` (nicht im Repo) |

## Grafikchip und die zwei Modi

Auf dem Apple M4 liefert das Sprachmodell unter Metal in acestep.cpp `b7ba6d9` fehlerhafte Ergebnisse
(0 Audio-Codes). Der Installer erkennt das mit einem kurzen Probelauf und schreibt nach `data/engine.conf`:

- `MODE=split` – Sprachmodell auf der CPU (Port 8086), Klangerzeugung auf Metal (Port 8085)
- `MODE=single` – alles auf einem Metal-Server (Port 8085)

Nach einem Update von acestep.cpp (`ACESTEP_REV` in `scripts/common.sh`) testet der Installer neu.

## Lizenz der Modelle

ACE-Step 1.5 steht unter Apache 2.0. Die Modelle werden beim Installieren von
[Hugging Face](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF) geladen und sind nicht Teil dieses Repositorys.
Vor kommerzieller Nutzung die Lizenz- und Trainingsdaten-Lage selbst prüfen.

## Lizenz

Der Code in diesem Repository steht unter der [MIT-Lizenz](LICENSE).
`static/vendor/wavesurfer.min.js` stammt von [wavesurfer.js](https://github.com/katspaugh/wavesurfer.js) (BSD-3-Clause).
