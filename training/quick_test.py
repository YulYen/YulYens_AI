# quick_test_doris.py
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import torch

BASE_MODEL = "unsloth/llama-3-8b-Instruct-bnb-4bit"
ADAPTER    = "out_lora_doris"

tok = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tok.pad_token_id is None:
    tok.pad_token_id = tok.eos_token_id

# Basismodell laden
base = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    device_map="auto"
)

# LoRA-Adapter drauf
model = PeftModel.from_pretrained(base, ADAPTER)
model.eval()

def chat(q: str, max_new_tokens=128):
    prompt = f"User: {q}\nDORIS:"
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **ids,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.5,
            top_p=0.9
        )
    text = tok.decode(out[0], skip_special_tokens=True)
    # nur den DORIS-Teil nach dem Prompt zurückgeben
    return text.split("DORIS:")[-1].strip()

# Testfragen
print("Q: Sag mir was sehr nettes, bitte!")
print("DORIS:", chat("Sag mir was sehr nettes, bitte!"))
print()
print("Q: Wie hoch ist der Eifelturm in Paris?")
print("DORIS:", chat("Wie hoch ist der Eifelturm in Paris?"))