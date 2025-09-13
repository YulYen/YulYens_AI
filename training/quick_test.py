"""Quick local test for the Doris model with a LoRA adapter.

Loads the base model in 4-bit using BitsAndBytes and attaches the LoRA
weights.  Then performs a small chat exchange to verify that everything
runs on the local machine (e.g. Leo cluster).
"""

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
import torch

BASE_MODEL = "LeoLM/leo-hessianai-13b"
ADAPTER = "out_lora_doris"


# Use 4-bit quantization so the model fits on smaller GPUs
bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
)


tok = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tok.pad_token_id is None:
    tok.pad_token_id = tok.eos_token_id

# Basismodell laden
base = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    device_map="auto",
    quantization_config=bnb_cfg,
)

# LoRA-Adapter drauf
model = PeftModel.from_pretrained(base, ADAPTER)
model.eval()


def chat(q: str, max_new_tokens: int = 128) -> str:
    prompt = f"User: {q}\nDORIS:"
    ids = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **ids,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.5,
            top_p=0.9,
        )
    text = tok.decode(out[0], skip_special_tokens=True)
    # nur den DORIS-Teil nach dem Prompt zurückgeben
    return text.split("DORIS:")[-1].strip()


if __name__ == "__main__":
    # Testfragen
    print("Q: Sag mir was sehr nettes, bitte!")
    print("DORIS:", chat("Sag mir was sehr nettes, bitte!"))
    print()
    print("Q: Wie hoch ist der Eifelturm in Paris?")
    print("DORIS:", chat("Wie hoch ist der Eifelturm in Paris?"))

