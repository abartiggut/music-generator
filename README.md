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
> werden in diesem Repository gepflegt. **Wir unterstützen hier ausschliesslich
> Windows.** Für macOS sind Anleitung und Support beim Originalprojekt zu finden.

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

Standard bei einer neuen Installation: **Mock-Modus mit Testklängen, ohne
KI-Musikgenerierung**. Die App öffnet `http://127.0.0.1:8765`.
Für echte KI-Musik eine lokale NVIDIA-GPU oder einen eigenen GPU-Server
gemäss der Windows-Anleitung einrichten. Beispiel für einen eigenen SSH-Alias:

```powershell
.\Install.cmd -Mode Ssh -SshHost GPU-SERVER
```

`GPU-SERVER` ist ein Platzhalter für deinen eingerichteten SSH-Zugang.
Der Windows-Installer installiert keine Software auf dem entfernten GPU-Rechner.
Ein erneuter Aufruf ohne Parameter erhält die vorhandene lokale Konfiguration.

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

## macOS

Die **[Mac-Anleitung findest du im Original-Repository](https://github.com/rabbitfiremediacreation/music-generator#readme)**.
Bitte verwende für macOS das Originalprojekt und richte Mac-Fragen an dessen
Entwickler. Dieser Fork bietet Anleitung und Support für Windows.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `Install.cmd` / `Install.ps1` | Windows-Installer |
| `Music Generator ON.cmd` / `Music Generator OFF.cmd` | Windows-Start und -Stopp |
| `scripts/windows/` | gemeinsame Windows-Funktionen und lokale Musik-Engine |
| `app/` | FastAPI-Backend: Queue, Bibliothek, Anbindung an ace-server |
| `static/` | Oberfläche |
| `docs/windows.md` | Windows-Anleitung |
| `docs/test-report.md` | Ergebnisse der Windows- und GPU-Tests |
| `engine/` | acestep.cpp und Modelle (vom Installer, nicht im Repo) |
| `data/` | Songs, Datenbank, Logs, `engine.conf` (nicht im Repo) |

## Lizenz der Modelle

ACE-Step 1.5 steht unter Apache 2.0. Die Modelle werden beim Installieren von
[Hugging Face](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF) geladen und sind nicht Teil dieses Repositorys.
Vor kommerzieller Nutzung die Lizenz- und Trainingsdaten-Lage selbst prüfen.

## Lizenz

Der Code in diesem Repository steht unter der [MIT-Lizenz](LICENSE).
`static/vendor/wavesurfer.min.js` stammt von [wavesurfer.js](https://github.com/katspaugh/wavesurfer.js) (BSD-3-Clause).
