# No Model-File required, just:
ollama pull qwen2.5:7b
#
# qwen2.5:7b IST bereits Instruct (Default-Tag = 7b-instruct-q4_K_M, ~4,7 GB).
# Base-Variante (nicht gewollt): qwen2.5:7b-base
#
# Bessere Qualitaet via explizitem Tag:
#   ollama pull qwen2.5:7b-instruct-q5_K_M   # ~5,4 GB, passt noch in 8 GB VRAM
#   ollama pull qwen2.5:7b-instruct-q8_0     # ~8,1 GB, sprengt 8 GB VRAM
