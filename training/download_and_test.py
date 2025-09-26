# download_and_test.py
import importlib.util as iu
import os

import torch, bitsandbytes as bnb
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = "LeoLM/leo-hessianai-13b-chat" 

# -------------------- Diagnose (GPU/BnB/Sanity) --------------------
print("=== Diagnose ===")
print("torch.cuda.is_available():", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
print("bnb_version:", bnb.__version__)
print("has_cuda_setup_module:", iu.find_spec("bitsandbytes.cuda_setup") is not None)

bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
)

print("\nLade Tokenizer ...")
tok = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
if tok.pad_token_id is None:
    tok.pad_token_id = tok.eos_token_id

print("Lade Modell ...")
OFFLOAD_DIR = os.path.join(os.path.dirname(__file__), "offload")
os.makedirs(OFFLOAD_DIR, exist_ok=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_cfg,
    device_map="auto",
    offload_folder=OFFLOAD_DIR,
    offload_state_dict=True,
    # enable CPU offload for layers that don't fit in GPU memory
    load_in_8bit_fp32_cpu_offload=True,
)
first_dev = next(model.parameters()).device
print("first param device:", first_dev)
try:
    print("hf_device_map keys:", list(getattr(model, "hf_device_map", {}).keys())[:8])
except Exception as e:
    print("hf_device_map not available:", e)

# -------------------- Kleiner Chat-Test (nur neu erzeugte Tokens ausgeben) --------------------
print("\n=== Testdurchlauf ===")
messages = [
    {"role": "system", "content": "Du bist DORIS: kurz, schnoddrig, faktenliebend."},
    {"role": "user", "content": "Sag was Lustiges über Computer."},
]
prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

inputs = tok(prompt, return_tensors="pt").to(model.device)
prompt_len = inputs["input_ids"].shape[1]

model.eval()
with torch.inference_mode():
    out = model.generate(
        **inputs,
        max_new_tokens=100,
        do_sample=True, top_p=0.9, temperature=0.7,
        repetition_penalty=1.1, no_repeat_ngram_size=4,
        eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id,
    )

gen_only = out[0, prompt_len:]
print(tok.decode(gen_only, skip_special_tokens=True).strip())
