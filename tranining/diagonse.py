import torch, bitsandbytes as bnb, importlib.util as iu
print("torch.cuda.is_available():", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
print("bnb_version:", bnb.__version__)
print("has_cuda_setup_module:", iu.find_spec("bitsandbytes.cuda_setup") is not None)

# harter Reality-Check: lädt wirklich auf GPU?
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
MODEL_ID = "unsloth/llama-3-8b-Instruct-bnb-4bit"
bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
)
tok = AutoTokenizer.from_pretrained(MODEL_ID)
m = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=bnb_cfg, device_map="auto")
print("first param device:", next(m.parameters()).device)
try:
    print("hf_device_map keys:", list(getattr(m, "hf_device_map", {}).keys())[:8])
except Exception as e:
    print("hf_device_map not available:", e)