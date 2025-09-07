"""
train_lora.py — Minimal-QLoRA für 200 Doris-Q&As.
Klar, kurz, ohne Magie: lädt 4-Bit-Basismodell, maskiert den Prompt, trainiert nur Adapter.
"""

from pathlib import Path
from typing import Dict

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig,
    set_seed,
)
from peft import LoraConfig, get_peft_model

# ---- Konfiguration (explizit, knapp) -----------------------------------------
MODEL_ID   = "unsloth/llama-3-8b-Instruct-bnb-4bit"   # HF-Checkpoint (kein GGUF)
DATA_PATH  = "data/doris_200.jsonl"                   # {"q": "...", "a": "..."} pro Zeile
OUT_DIR    = "out_lora_doris"

MAX_LEN    = 1024   # bei VRAM-Druck 768 oder 512 nehmen
EPOCHS     = 1
LR         = 2e-4
BATCH      = 1
ACCUM      = 16
WARMUP     = 0.03
LOG_STEPS  = 10

# LoRA auf klassische Llama/Mistral-Projektionen
LORA_R        = 16
LORA_ALPHA    = 16
LORA_DROPOUT  = 0.05
TARGET_MODULES = ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]
# ------------------------------------------------------------------------------


def build_prompt(q: str) -> str:
    return f"User: {q.strip()}\nDORIS:"


def encode_example(ex: Dict[str, str], tok: AutoTokenizer) -> Dict[str, list]:
    """Tokenisiert und maskiert Prompt (Loss=-100), pad auf MAX_LEN."""
    prompt = build_prompt(ex["q"])
    answer = " " + ex["a"].strip() + "\n"   # führendes Leerzeichen hilft Token-Grenzen

    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    a_ids = tok(answer, add_special_tokens=False)["input_ids"]

    input_ids = (p_ids + a_ids)[:MAX_LEN]
    labels    = ([-100]*len(p_ids) + a_ids)[:MAX_LEN]
    attn      = [1]*len(input_ids)

    pad = MAX_LEN - len(input_ids)
    if pad > 0:
        input_ids += [tok.pad_token_id]*pad
        attn      += [0]*pad
        labels    += [-100]*pad

    return {"input_ids": input_ids, "attention_mask": attn, "labels": labels}


def main() -> None:
    set_seed(42)
    if not Path(DATA_PATH).is_file():
        raise FileNotFoundError(f"Dataset fehlt: {DATA_PATH}")

    use_cuda = torch.cuda.is_available()
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if use_cuda else torch.float32,
    )

    tok = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
    if tok.pad_token_id is None:
        tok.pad_token_id = tok.eos_token_id
    tok.padding_side = "right"

    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb,
        device_map="auto",
    )
    base.gradient_checkpointing_enable()

    peft_cfg = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES,
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, peft_cfg)

    ds = load_dataset("json", data_files=DATA_PATH, split="train")
    tok_ds = ds.map(lambda ex: encode_example(ex, tok), remove_columns=ds.column_names)

    args = TrainingArguments(
        output_dir=OUT_DIR,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH,
        gradient_accumulation_steps=ACCUM,
        learning_rate=LR,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP,
        logging_steps=LOG_STEPS,
        save_strategy="epoch",     # nur am Epochenende
        # vorher (gut für Linux/WSL):
        # optim="paged_adamw_8bit",
        # Windows (pragmatisch, stabil):
        optim="adamw_torch",
        bf16=use_cuda,             # bfloat16 auf moderner GPU
        report_to=[],              # kein W&B etc.
    )

    trainer = Trainer(model=model, args=args, train_dataset=tok_ds)
    trainer.train()

    model.save_pretrained(OUT_DIR)
    tok.save_pretrained(OUT_DIR)
    print(f"Fertig. Adapter liegt in: {OUT_DIR}")


if __name__ == "__main__":
    main()