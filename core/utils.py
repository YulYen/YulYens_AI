    # --------- Utilities (ohne Seiteneffekte nach außen) ---------
import socket
from datetime import datetime
from system_prompts import system_prompts, get_prompt_by_name

def _wiki_mode_enabled(mode_val) -> bool:
    if isinstance(mode_val, bool):
        return mode_val
    s = str(mode_val).strip().lower()
    return s in ("online", "offline")

def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def _system_prompt_with_date(name) -> str:
    base = get_prompt_by_name(name)
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{base} | Heute ist der {today}."

def _greeting_text(cfg) -> str:
    tpl = cfg.ui["greeting"]  # KeyError erwünscht (keine Defaults)
    values = {
        "model_name":   cfg.core["model_name"],
        "persona_name":system_prompts[0]["name"],
    }
    return tpl.format_map(values)