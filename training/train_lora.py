"""
train_lora.py — Minimal-QLoRA für 200 Doris-Q&As.
Klar, kurz, ohne Magie: lädt 4-Bit-Basismodell, maskiert den Prompt, trainiert nur Adapter.
"""

from pathlib import Path
from typing import Dict

import torch
from datasets import load_dataset
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    set_seed,
    default_data_collator,
    BitsAndBytesConfig,
    logging as hf_logging,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# ---- Konfiguration (explizit, knapp) -----------------------------------------
MODEL_ID = "LeoLM/leo-hessianai-13b-chat"
DATA_PATH  = "data/kuratiert_neu_doris.jsonl"         # {"user": "...", "assistant": "..."} pro Zeile


MAX_LEN    = 256   # DORIS-Beispiele sind sehr kurz, bei anderen Trainings wegen VRAM-Druck z.B. 768 oder 512 nehmen
EPOCHS     = 1
LR         = 1e-4
BATCH      = 1
ACCUM      = 4     # weniger Accum -> mehr, kürzere Steps -> sichtbarer Fortschrittsbalken
WARMUP     = 0.03

# LoRA-Ziele (Llama/Mistral-typische Projektionen)
LORA_R        = 8
LORA_ALPHA    = 16
LORA_DROPOUT  = 0.1
TARGET_MODULES = ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]
# ------------------------------------------------------------------------------


def build_prompt(q: str) -> str:
    return f"User: {q.strip()}\nDORIS:"


def encode_example(ex: Dict[str, str], tok: AutoTokenizer) -> Dict[str, list]:
    """Tokenisiert per Chat-Template und maskiert Prompt (Loss=-100)."""
    messages = [
        {"role": "system", "content": "Du bist DORIS: spitz, sarkastisch, kurz angebunden."},
        {"role": "user", "content": ex["user"]},
    ]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    answer = " " + ex["assistant"].strip() + tok.eos_token

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
    if use_cuda:
        # etwas schneller & stabiler auf NVIDIA (keine Genauigkeitseinbußen bei bf16)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")

    # HF-Logging angenehm gesprächig (für echten Fortschritt sorgt tqdm unten)
    hf_logging.set_verbosity_info()

    # --- Tokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
    if tok.pad_token_id is None:
        tok.pad_token_id = tok.eos_token_id
    tok.padding_side = "right"

    # --- BitsAndBytes (4-bit)
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if use_cuda else torch.float32,
    )

    # --- Config zuerst laden und rope_scaling bereinigen (Warnung killen)
    cfg = AutoConfig.from_pretrained(MODEL_ID)
    rs = getattr(cfg, "rope_scaling", None)
    if isinstance(rs, dict):
        # Normalize auf das Schema mit "rope_type"
        if "type" in rs and "rope_type" not in rs:
            cfg.rope_scaling = {"rope_type": rs.get("type", "linear"), "factor": rs.get("factor", 2.0)}
        elif "rope_type" in rs and "type" in rs:
            cfg.rope_scaling = {"rope_type": rs.get("rope_type", "linear"), "factor": rs.get("factor", 2.0)}

    # --- Auto-Offload: KEIN "disk" in max_memory (accelerate erwartet ints/'cpu')
    max_memory = {
        0:     "7GiB",   # GPU 0, etwas Luft für Gradients
        "cpu": "24GiB",  # an deinen RAM anpassen
    }

    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        config=cfg,
        quantization_config=bnb_cfg,
        torch_dtype=torch.bfloat16 if use_cuda else torch.float32,
        device_map="auto",
        max_memory=max_memory,
        offload_folder="offload_cache",   # Disk-Offload-Ordner
        low_cpu_mem_usage=True,
    )

    # --- K-Bit-Training vorbereiten
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True)
    # künftige Torch-Warnung vermeiden und i. d. R. stabiler:
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    base.config.use_cache = False
    # Stabil und verfügbar auf Windows (statt evtl. kaputtem FA2)
    base.config.attn_implementation = "sdpa"

    # --- LoRA
    peft_cfg = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES,
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, peft_cfg)

    # --- Daten
    ds = load_dataset("json", data_files=DATA_PATH, split="train")
    tok_ds = ds.map(lambda ex: encode_example(ex, tok), remove_columns=ds.column_names)

    # --- Output-Verzeichnis modellbezogen
    model_name = MODEL_ID.split("/")[-1].replace(":", "_")
    out_dir = Path(f"out_lora_{model_name}_doris")
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Training
    args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH,
        gradient_accumulation_steps=ACCUM,
        group_by_length=True,
        dataloader_num_workers=0,
        learning_rate=LR,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP,
        # klarer Live-Fortschritt:
        disable_tqdm=False,
        logging_steps=1,
        logging_first_step=True,
        log_level="info",
        save_strategy="steps",
        save_steps=50,
        optim="adamw_torch",
        bf16=use_cuda,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tok_ds,
        data_collator=default_data_collator,
    )
    trainer.train()

    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))
    print(f"Fertig. Hurra! Adapter liegt in: {out_dir}")


if __name__ == "__main__":
    main()
