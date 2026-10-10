# Automatische Tests

```powershell
uv sync --frozen --python 3.12
uv run --frozen python -m unittest discover -s tests -v
```

Die GitHub-Actions-Matrix führt dieselben Tests unter Windows und Ubuntu aus.
Die Tests brauchen weder CUDA noch Modell-Dateien, GPU-Server oder Internetzugang.

- API: Warteschlange, Varianten/Seeds, Abbrechen/Wiederholen, Favoriten,
  gültige WAV-Dateien, ZIP-Export und Validierung der Einstellungen;
  fremde Hostnamen werden blockiert, Update und Shutdown benötigen den Pflicht-Header.
- Modellanbindung: Ein lokaler HTTP-Testserver bildet das ace-server-Protokoll
  ab. Generierung und Fehlerbehandlung laufen über echte HTTP-Anfragen.
- Launcher: Echte Prozesse prüfen Start, Status, authentifizierten Neustart und
  Shutdown, gespeicherte Konfiguration, belegte Ports und fremde Prozess-IDs.
- Updater: Temporäre Git-Repositories prüfen Fast-Forward sowie Schutz bei
  falschem Fork, Entwicklungsbranch, lokalen Commits und geänderten Dateien.
- macOS: Simulierte Prozesse prüfen den bestehenden Neustartweg, das Warten
  auf den eigenen Elternprozess und den Schutz anderer Prozess-IDs.

Alle Bibliotheken, Zustandsdateien und Git-Repositories liegen in temporären
Ordnern. `MUSIC_GENERATOR_DATA_DIR` wird vor dem Import des App-Moduls gesetzt;
die vorhandene Bibliothek unter `data/` wird nicht verwendet.

Musikalische Qualität, echte CUDA-Ausführung und die SSH-Verbindung zu GPU-Server
müssen separat mit der installierten Engine geprüft werden.
