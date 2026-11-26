# Piper TTS Setup

## Install Piper

```bash
pip install piper-tts
```

## Configure TTS in `config.yaml`

Make sure TTS is enabled and voices are configured:

```yaml
tts:
  enabled: true
  features:
    terminal_auto_create_wav: true
  voices:
    default:
      de: "de_DE-thorsten-high"
      en: "en_US-amy-medium"
    personas_de:
      DORIS: "de_DE-kerstin-low"
      POPCORN: "de_DE-pavoque-low"
      LEAH: "de_DE-kerstin-low"
      PETER: "de_DE-thorsten-high"
```

## Download voices

1. Create a folder named `voices` in the project root.
2. Download the ONNX voices configured in `config.yaml` (default + persona voices).
3. Place the downloaded files into the `voices` folder.

## Runtime behavior

- In the terminal UI, automatic WAV generation and playback works on Windows, Linux and macOS.
- Output files are written to `out/<timestamp>_<persona>.wav` on every platform.
- Windows plays via `winsound` (stdlib); Linux and macOS dispatch to `paplay`/`aplay`/`ffplay` or `afplay`. No player installed means no playback — the WAV is still written to `out/`.
- In the Web UI, the "Read aloud 🔊" button plays the latest reply in the
  browser (`tts.features.web_read_aloud`, default on) — platform-independent,
  since no `winsound` is involved. The button only appears when piper-tts is
  installed. Voices are loaded once and cached per model path.
