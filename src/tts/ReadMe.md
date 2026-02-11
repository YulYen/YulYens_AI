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

- In Terminal UI, WAV files are generated automatically when TTS is enabled.
- Output files are written to `out/<timestamp>_<persona>.wav`.
- The file is played automatically right after generation.
