from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
import torch

BASE_MODEL = "LeoLM/leo-hessianai-13b-chat"
ADAPTER = "out_lora_doris"

# 4-bit quantization
bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
)

tok = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tok.pad_token_id is None:
    tok.pad_token_id = tok.eos_token_id

# Offload-Setup: GPU + CPU, aber kein "disk"
max_memory = {
    0: "7GiB",   # deine 4060 Ti, etwas Luft für Gradients
    "cpu": "24GiB"
}

base = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    device_map="auto",
    quantization_config=bnb_cfg,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    max_memory=max_memory,
    offload_folder="offload_cache",   # falls CPU-RAM nicht reicht
    low_cpu_mem_usage=True,
)

# LoRA-Adapter drauf
model = PeftModel.from_pretrained(base, ADAPTER)
model.eval()

def chat(q: str, max_new_tokens: int = 128) -> str:
    messages = [
        {"role": "system", "content": "Du bist DORIS: spitz, sarkastisch, kurz angebunden."},
        {"role": "user", "content": q},
    ]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.5,
            top_p=0.9,
        )
    text = tok.decode(out[0], skip_special_tokens=True)
    return text.split(messages[-1]["content"])[-1].strip()

if __name__ == "__main__":
    print("Q: Sag mir was sehr Nettes, bitte!")
    print("DORIS:", chat("Sag mir was sehr Nettes, bitte!"))
    print()
    print("Q: Wie hoch ist der Eiffelturm in Paris?")
    print("DORIS:", chat("Wie hoch ist der Eiffelturm in Paris?"))
