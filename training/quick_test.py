"""
quick_test.py — zwei Modi:
- test_before(): Base-Chatmodell in 4-Bit laden und kurz chatten (Smoke-Test vor Training)
- test_after():  Base + LoRA-Adapter laden und kurz chatten (nach dem Training)

Robust für 8 GB VRAM: 4-Bit + Offload-Grenzen + SDPA.
"""

from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE_MODEL = "LeoLM/leo-hessianai-13b-chat"
ADAPTER    = "out_lora_leo-hessianai-13b-chat_doris"  # muss zum Training-Ausgabepfad passen

# Gemeinsames Test-Set (2 alte + 5 neue)
TEST_QUESTIONS = [
    "Mach mir bitte ein nettes Kompliment!",
    "Sag mir was nettes!",
    "Wie hoch ist der berühmte Eiffelturm in Paris?",
    "Wie heißt die Hauptstadt von Kanada?",
    "Wie viele Planeten hat unser Sonnensystem?",
    "Motiviere mich zum Aufräumen.",
    "Erkläre Quicksort in drei Sätzen – aber nicht langweilig.",
    "Was hältst du von Menschen, die 30 Browser-Tabs gleichzeitig offen haben?",
]

# 4-Bit Quantisierung (BnB)
bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
)

def _load_base():
    use_cuda = torch.cuda.is_available()
    if use_cuda:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")

    tok = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
    if tok.pad_token_id is None:
        tok.pad_token_id = tok.eos_token_id

    # Offload-Grenzen: GPU0 ~7GiB + CPU-RAM
    max_memory = {0: "7GiB", "cpu": "24GiB"}

    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        device_map="auto",
        quantization_config=bnb_cfg,
        torch_dtype=torch.bfloat16 if use_cuda else torch.float32,
        max_memory=max_memory,
        offload_folder="offload_cache",
        low_cpu_mem_usage=True,
    )
    # Stabil auf Windows
    try:
        base.config.attn_implementation = "sdpa"
    except Exception:
        pass

    return tok, base

def _chat(model, tok, question: str, max_new_tokens: int = 128) -> str:
    messages = [
        {"role": "system", "content": "Du bist DORIS: spitz, sarkastisch, kurz angebunden."},
        {"role": "user", "content": question},
    ]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    model.eval()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.6,
            top_p=0.9,
        )
    # simple Extraktion: alles nach der letzten User-Nachricht
    text = tok.decode(out[0], skip_special_tokens=True)
    return text.split(messages[-1]["content"])[-1].strip()

# --------- Modus 1: vor dem Training (nur Base) ----------
def test_before():
    print("DORIS vor LoRA-Finetuning:")
    tok, base = _load_base()
    for q in TEST_QUESTIONS:
        print("\nQ:", q)
        print("DORIS:", _chat(base, tok, q))

# --------- Modus 2: nach dem Training (Base + Adapter) ---
def test_after():
    print("DORIS nach LoRA-Finetuning:")
    tok, base = _load_base()
    adapter_path = Path(ADAPTER)
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter nicht gefunden: {adapter_path}")
    model = PeftModel.from_pretrained(base, str(adapter_path))
    for q in TEST_QUESTIONS:
        print("\nQ:", q)
        print("DORIS:", _chat(model, tok, q))

if __name__ == "__main__":
    # Achtung: beide Tests laden das Modell separat → doppelter VRAM-Bedarf
    test_before()   # ← vor dem Training (nur Base)
    test_after()    # ← nach dem Training (Base + LoRA)
