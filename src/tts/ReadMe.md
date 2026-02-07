# Piper TTS Setup

## Install Piper

```bash
pip install piper-tts
```

## Download voices

1. Create a folder named `voices` in the project root.
2. Download the German ONNX voices used by this project:
   - `de_DE-kerstin-low.onnx`
   - `de_DE-karlsson-low.onnx`
   - `de_DE-pavoque-low.onnx`
   - `de_DE-thorsten-high.onnx`
3. Place the downloaded files into the `voices` folder.

You can then run the example:

```bash
python src/tts/hello_piper.py
```
