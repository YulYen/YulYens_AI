# Whisper STT Setup (Spracheingabe)

## Install faster-whisper

```bash
pip install faster-whisper
```

Kein System-ffmpeg nötig — faster-whisper dekodiert Audio über PyAV
(gebündeltes ffmpeg), funktioniert also auch unter Windows out of the box.

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

## Runtime behavior

- Nur Web-UI, nur Einzelchat: Nach der Persona-Wahl erscheint neben dem
  Eingabefeld ein Mikrofon. Aufnehmen → stoppen → das Transkript wird ans
  Eingabefeld **angehängt** und kann vor dem Senden editiert werden.
- Die **erste** Aufnahme lädt das Whisper-Modell (beim allerersten Mal
  inkl. Download nach `~/.cache/huggingface`) — das dauert einen Moment.
  Danach bleibt das Modell im Speicher gecacht.
- Ist faster-whisper nicht installiert oder `stt.enabled: false`, bleibt
  das Mikro komplett unsichtbar; die App läuft unverändert.
