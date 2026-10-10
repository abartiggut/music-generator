# Windows und eigene GPU-Server

Die Oberfläche und Songbibliothek laufen nativ unter Windows. Die Musik berechnet
wahlweise eine lokale NVIDIA-GPU oder eine entfernte acestep.cpp-Engine.
WSL ist dafür nicht nötig.

## Installation

Voraussetzungen: Windows 10/11, Git for Windows und Internet für die erste Installation.
Der Installer richtet eine eigene Python-3.12-Umgebung über `uv` ein. Bestehende
Python-Installationen werden dabei nicht verändert. Wenn `uv` fehlt, wird der
offizielle Benutzer-Installer von Astral verwendet.

```powershell
git clone https://github.com/abartiggut/music-generator.git
cd music-generator
.\Install.cmd
```

Beim ersten Aufruf ist **Mock** der Standard: Testklänge ohne KI-Modelle oder
Serververbindung. Für echte KI-Musik wähle eine der unten beschriebenen GPU-Modi.
Der SSH-Modus benötigt den Windows-OpenSSH-Client und einen bereits eingerichteten
Schlüsselzugang zu deinem eigenen GPU-Server. Der Installer prüft diesen ohne
interaktive Passwortabfrage. Die Engine muss auf dem GPU-Server separat
eingerichtet sein und auf `127.0.0.1:18085` laufen.

Nach der Installation: `Music Generator ON.cmd` startet die App und öffnet den
Browser; `Music Generator OFF.cmd` beendet sie. Die Web-App und der SSH-Tunnel
laufen unsichtbar als eigene Prozesse. Wiederholtes Starten ist möglich, ohne
weitere Instanzen anzulegen. Fremde Prozesse auf belegten Ports werden nicht beendet.

## Betriebsarten

| Modus | Installationsaufruf | Berechnung |
| --- | --- | --- |
| SSH-Server | `.\Install.cmd -Mode Ssh -SshHost GPU-SERVER` | Eigene Engine über SSH-Tunnel |
| Direkter Server | `.\Install.cmd -Mode Remote -ServerUrl http://SERVER:18085` | Bereits erreichbare Engine |
| Test | `.\Install.cmd -Mode Mock` | Einfache Testklänge; ohne KI-Modell |
| Lokale GPU | `.\Install.cmd -Mode Local -LmSize 4B` | Native Windows-CUDA-Engine |

Zum Moduswechsel zuerst `Music Generator OFF.cmd` ausführen und danach den
Installer mit dem gewünschten Modus erneut starten. Ohne explizite Parameter
erhält ein erneuter Installeraufruf die vorhandene Konfiguration und Bibliothek.

`GPU-SERVER` beziehungsweise `SERVER` sind Platzhalter für deinen eigenen Server.

Weitere Parameter: `-NoStart`, `-NoBrowser`, `-Port 8765`, `-SshHost GPU-SERVER`,
`-RemotePort 18085` und `-TunnelPort 18085`. Der letzte Port ist lokal auf Windows,
der vorletzte ist auf dem GPU-Rechner. Web- und Modellport müssen unterschiedlich sein.

Beispiel für einen anderen GPU-Rechner und andere Ports:

```powershell
.\Install.cmd -Mode Ssh -SshHost GPU-SERVER -RemotePort 18085 -TunnelPort 18086 -Port 8766
```

Ein direkter Server hat hier keine Benutzeranmeldung; verwende ihn nur in einem
vertrauenswürdigen Netz. Der SSH-Modus hält Web-App, Tunnel und Engine an Loopback
und benötigt keine öffentliche Freigabe des Modellservers.

## Lokale NVIDIA-GPU

Der lokale Installer benötigt Visual Studio **2022** mit dem Paket
**Desktop development with C++**, CMake **ab 3.24**, NVIDIA-Treiber und CUDA Toolkit
**ab 12.8**. Der Treiber allein enthält keinen CUDA-Compiler. Diese Systemwerkzeuge
werden nicht automatisch installiert.

Die Engine wird aus den Quellen auf Revision `b7ba6d9` gebaut. Der Installer lädt
vier GGUF-Dateien, prüft Grösse und SHA-256 und setzt unterbrochene Downloads fort.
Die Modelldateien und ihre feste Revision stehen in `scripts/models.json`.
Mit dem 4B-Sprachmodell sind die Downloads zusammen rund **8,1 GB**; zusätzlich
brauchen Compiler, Build und Songs Speicher. Für kleinere GPUs können `1.7B`
oder `0.6B` gewählt werden. Diese Auswahl ist keine Garantie für einen bestimmten
Speicherbedarf bei beliebiger Songlänge.

Das Klangmodell ist derzeit SFT Q8, die Ausgabe WAV mit 48 kHz und 16 Bit.
Die CUDA-Starts verwenden `--no-fa --clamp-fp16`: Im Blackwell-Test lieferte
die ursprüngliche Konfiguration bei der Audioanalyse ungültige LM-Ausgabe.
Diese Kombination ergab gültige Metadaten; sie wird deshalb auch beim
lokalen CUDA-Start verwendet. Ein fester Seed steuert beide Modellphasen.
Die aktuellen XL-Modelle der Python-Anwendung sind in diesem Fork nicht integriert.
Die offizielle Python-ACE-Step-API ist kein direkter Ersatz für die hier verwendete
acestep.cpp-API.

## Engine auf einem Linux-GPU-Server einrichten

`scripts/remote/setup_engine.py` richtet die Engine ohne `sudo` ein. Voraussetzung:
Linux x86_64 mit Blackwell-GPU, NVIDIA-Treiber für CUDA 12.9, `git`, `curl`, `g++`,
`systemd --user`, Python 3.12 und `uv` unter `~/.local/bin/uv`.
Das Skript baut ausdrücklich für CUDA-Architektur 120 (Blackwell); es ist kein
universeller Installer für ältere GPU-Generationen.

Übertrage `scripts/remote/setup_engine.py` und `scripts/models.json` auf den Rechner
in einen neuen Arbeitsordner und starte dort:

```bash
~/.local/bin/uv run --python 3.12 --no-project python setup_engine.py --manifest models.json --start
```

Die Quellen landen unter `~/apps/music-generator-engine`, CUDA-Werkzeuge und
Installationsnachweis unter `~/.local/share/music-generator-engine`. Das Skript
verwendet eine eigene, geprüfte CUDA-12.9.1-Toolchain; `/usr/local/cuda` und andere
KI-Anwendungen werden nicht geändert. CUDA-Werkzeuge kommen von NVIDIA,
Modelle von Hugging Face, jeweils mit festgelegten SHA-256-Prüfsummen.

Der neue Dienst **music-generator-engine.service** lauscht auf Loopback-Port 18085.
Ein bestehender anderer Listener oder eine abweichende Dienstdatei werden erhalten.
Der Dienst wird nicht automatisch für den Rechnerstart aktiviert.

```bash
systemctl --user start music-generator-engine
systemctl --user status music-generator-engine --no-pager
systemctl --user stop music-generator-engine
journalctl --user -u music-generator-engine -n 40 --no-pager
```

Das Stoppen der Windows-App bricht ihren aktiven Auftrag ab und schliesst den
Tunnel. Es beendet den Dienst auf dem GPU-Server nicht.

## Daten, Updates und Diagnose

`data/launcher.json` enthält die Startkonfiguration, `data/music.db` die Metadaten
und `data/songs/` die Songs. Alles liegt ausserhalb der Git-Versionierung.
Gesicherte Kopien dieser Dateien erhalten die Bibliothek bei einer Neuinstallation.
`MUSIC_GENERATOR_DATA_DIR` kann für separate Testinstanzen gesetzt werden.

Verbindungseinstellungen sind während eines verwalteten Starts im Setup gesperrt;
der Installer beziehungsweise die Startkonfiguration bestimmt sie. Der Timeout
bleibt einstellbar. Beim Stoppen werden wartende und laufende Aufträge abgebrochen;
sie können in der Bibliothek erneut gestartet werden.
Während einer laufenden Audioanalyse weist der Stop-Knopf das Beenden mit einem
Hinweis ab (HTTP 409). Danach kann erneut gestoppt werden. Ungültige
Modellantworten werden verständlich angezeigt.

Updates werden ausschliesslich von `abartiggut/music-generator`, Branch `main`,
geholt. Lokale Änderungen, neue unversionierte Dateien, eigene Commits oder ein
abweichender Ursprung verhindern das automatische Update. ZIP-Installationen
werden nicht überschrieben. Updates sind während laufender Aufträge gesperrt.
Bei einem Web-Neustart bleiben SSH-Tunnel und Musik-Engine erhalten.

```powershell
.\.venv\Scripts\python.exe -m app.launcher status
Get-Content .\data\launcher.log -Tail 30
Get-Content .\data\server.log -Tail 30
Get-Content .\data\ssh-tunnel.log -Tail 30
```

Bei einem belegten Port einen anderen wählen. Wenn die Oberfläche läuft, aber
**Offline** zeigt, prüfe den Modellserver und die Verbindung. Nach einem
abgebrochenen Start kann eine verwaiste `data/launcher.lock` übrig bleiben; prüfe
vor deren Entfernung, dass kein Startvorgang mehr läuft.

## Tests

```powershell
uv sync --frozen --python 3.12
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Die Tests verwenden temporäre Datenbanken und eigene Testprozesse. Sie prüfen
Warteschlange, Varianten, WAV/ZIP, Abbruch/Retry, den HTTP-Ablauf zur Engine,
Windows-Prozesssteuerung, Neustart und Schutz eigener Git-Änderungen.
Die GitHub-Actions-Matrix führt sie auf Windows und Ubuntu aus.
Diese Tests enthalten keinen GPU-Benchmark und keine Bewertung der Klangqualität.

Die Testklänge des Mock-Modus sind ausdrücklich keine Nachweise für funktionierende
KI-Musikgenerierung. Ein nativer Windows-CUDA-Build braucht einen eigenen GPU-Test;
ein Test über SSH prüft stattdessen die Windows-App und den entfernten CUDA-Server.
