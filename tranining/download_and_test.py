import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = "unsloth/llama-3-8b-Instruct-bnb-4bit"

bnb = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
)

print("Lade Tokenizer ...")
tok = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
if tok.pad_token_id is None:
    tok.pad_token_id = tok.eos_token_id

print("Lade Modell ...")
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=bnb, device_map="auto")
model.eval()

messages = [
    {"role": "system", "content": "Du bist DORIS: kurz, schnoddrig, faktenliebend."},
    {"role": "user", "content": "Sag was Lustiges über Computer."},
]
prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

inputs = tok(prompt, return_tensors="pt").to(model.device)
prompt_len = inputs["input_ids"].shape[1]

with torch.inference_mode():
    out = model.generate(
        **inputs,
        max_new_tokens=100,
        do_sample=True, top_p=0.9, temperature=0.7,
        repetition_penalty=1.1, no_repeat_ngram_size=4,
        eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id,
    )

# NUR die neu erzeugten Tokens (ohne Prompt) decoden:
gen_only = out[0, prompt_len:]
print(tok.decode(gen_only, skip_special_tokens=True).strip())
