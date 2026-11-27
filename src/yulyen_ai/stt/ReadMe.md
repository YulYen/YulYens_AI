# Whisper STT Setup (Spracheingabe)

## Install faster-whisper

```bash
pip install faster-whisper "av<19"
```

Kein System-ffmpeg nötig — faster-whisper dekodiert Audio über PyAV
(gebündeltes ffmpeg), funktioniert also auch unter Windows out of the box.

**Warum `av<19`:** faster-whisper 1.2.1 ruft `av.open(…, metadata_errors=…)`
auf, und PyAV 19 kennt das Argument nicht mehr. faster-whisper selbst deckelt
`av` nicht, ein nacktes `pip install faster-whisper` holt also die kaputte
Kombination. Die WebUI meldet das dann mit genau diesem Befehl. Der Deckel kann
weg, sobald eine faster-whisper-Version erscheint, die mit PyAV 19 umgehen kann
(`pip index versions faster-whisper`).

## Configure STT in `config.yaml`

```yaml
stt:
  enabled: true            # Mikro erscheint nur, wenn zusätzlich faster-whisper installiert ist
  model: "small"           # tiny | base | small | medium | large-v3
  device: "auto"           # auto | cpu | cuda
  compute_type: "auto"     # auto | int8 | float16 …
  language: "de"           # null = Auto-Erkennung
```

- `model`: `small` ist der Sweet Spot für Deutsch auf CPU/GPU. `tiny`/`base`
  sind schneller, aber ungenauer; `large-v3` braucht eine kräftige GPU.
- `language`: fest auf `de` verdrahtet ist schneller und robuster als
  Auto-Erkennung; auf `null` setzen, wenn gemischt gesprochen wird.
- `device`: `auto` nimmt die GPU, wenn eine NVIDIA-Karte da ist — braucht dort
  aber die CUDA-12-Laufzeit (cuBLAS, cuDNN), die faster-whisper nicht
  mitbringt. Fehlt sie, weicht `auto` bei der ersten Aufnahme mit einer Warnung
  im Log auf die CPU aus und bleibt dort. `cuda` ausdrücklich gesetzt weicht
  nicht aus, sondern zeigt den Fehler. `small` auf der CPU braucht für einen
  kurzen Satz etwa eine Sekunde.

## Runtime behavior

- Nur Web-UI, nur Einzelchat: Nach der Persona-Wahl erscheint neben dem
  Eingabefeld ein Mikrofon. Aufnehmen → stoppen → das Transkript wird ans
  Eingabefeld **angehängt** und kann vor dem Senden editiert werden.
- Die **erste** Aufnahme lädt das Whisper-Modell (beim allerersten Mal
  inkl. Download nach `~/.cache/huggingface`) — das dauert einen Moment.
  Danach bleibt das Modell im Speicher gecacht.
- Ist faster-whisper nicht installiert oder `stt.enabled: false`, bleibt
  das Mikro komplett unsichtbar; die App läuft unverändert.
