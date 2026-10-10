# Windows/GPU-Server-Test vom 10. Oktober 2026

Die Windows-App wurde nativ unter Windows mit Python 3.12 getestet. Die echte
Berechnung lief über ihren SSH-Tunnel zu `gpu-server` und dessen NVIDIA RTX PRO 6000
Blackwell Workstation Edition mit 96 GB VRAM. Engine: acestep.cpp `b7ba6d9`,
CUDA 12.9.1, Architektur 120; LM 4B Q8, SFT Q8, VAE BF16. Alle vier Modelldateien
wurden gegen die festen SHA-256-Prüfsummen im Manifest geprüft.

## Echte Generierung durch die Windows-App

Alle Proben nutzten 50 Syntheseschritte, feste Seeds und
`--no-fa --clamp-fp16`. Gemessen wurde die Zeit von der Einreihung bis zum
fertigen Download, mit einem Pollintervall von zwei Sekunden. Es waren einzelne
Aufträge; die Werte sind kein Belastungstest und keine Geschwindigkeitsgarantie.

| Auftrag | Gewünscht | WAV-Länge | Gesamtzeit | Seed |
| --- | ---: | ---: | ---: | ---: |
| Synthpop-Instrumental | 20 s | 19,60 s | 12,39 s | 4242 |
| Synthpop mit deutschem Text | 30 s | 30,00 s | 12,34 s | 4243 |
| Längeres Instrumental | 90 s | 89,44 s | 14,64 s | 4244 |

Alle Dateien: Stereo, 48 kHz, 16 Bit PCM, gültige WAV-Dateien mit messbarem
Audiosignal. Die Engine-Logs bestätigen CUDA für LM, Textencoder, DiT und VAE.
Im Leerlauf nach den Tests waren rund 58,6 GB VRAM frei; bestehende Anwendungen
belegten schon vor der Installation rund 38 GB. Die Engine entlädt ihre Modelle
zwischen Aufträgen. Temporäre Diagnoseserver wurden beendet.

Der Gesangstest wurde anschliessend durch `/api/analyze` verarbeitet: gültige
Metadaten nach 8,69 s, erkannte Sprache Deutsch. Die Analyse ist eine
Modellschätzung: Text, Tempo und Stil können vom Auftrag oder tatsächlichen
Audio abweichen. Sie ersetzt keine verlässliche Transkription. Klangqualität
und genaue Umsetzung der Lyrics müssen durch Anhören beurteilt werden.

Die ursprüngliche CUDA-Konfiguration lieferte bei der Analyse teils ungültige
UTF-8-/leere JSON-Ausgabe. Die oben genannten Optionen lieferten gültige
Ergebnisse. Leere oder fehlerhafte Modellantworten ergeben jetzt verständliche
Fehler. Ein fester Seed wird an beide Modellphasen weitergereicht; bitgleiche
Ausgabe über verschiedene GPUs oder Treiberversionen ist nicht zugesichert.

## Oberfläche und Betrieb

In Chrome geprüft: Einstellungen speichern, zwei Varianten generieren,
Bibliothek, echte WAV-Wiedergabe mit laufender Zeitanzeige und Wellenform,
Stop-Knopf. Installation und ON/OFF-Wrapper wurden unter Windows geprüft;
auch Installerpfade mit Leerzeichen und Windows PowerShell 5.1.
Die Windows-App und der Tunnel laufen auf Loopback. Der eigene Linux-Engine-Dienst
läuft separat auf Port 18085; bestehende Dienste auf 8085 wurden erhalten.

## Automatisierte Tests und Grenzen

25 Tests bestehen lokal unter Windows. Die GitHub-Actions-Matrix führt dieselben
Tests zusätzlich auf `windows-latest` und `ubuntu-latest` aus. Abgedeckt sind
Queue, Varianten, WAV/ZIP, Favourites, Abbruch/Retry, reale HTTP-Protokollabfolge
gegen einen kontrollierten Testserver, ungültige Modellantworten, Seed-Übergabe,
Analyse-/Shutdown-Sperre, verwalteter Neustart und Erhalt fremder Prozesse sowie
lokaler Git-Änderungen.

Der native Windows-CUDA-Build wurde hier mangels installierter Visual-Studio-
C++-Werkzeuge nicht ausgeführt. Der bewiesene GPU-Betriebsweg ist daher
**native Windows-App mit CUDA-Engine auf GPU-Server**. Die Mac-Start-/Update-Regressionen
sind isoliert getestet, die komplette Mac-Anwendung wurde in dieser Arbeit
nicht neu installiert.
