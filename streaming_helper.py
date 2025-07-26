# streaming_helper.py
import re
import logging

def clean_token(token: str) -> str:
    # Dummy-Tags raus
    token = re.sub(r"<dummy\d+>", "", token)

    # Einzelne irrelevante Tokens rausfiltern
    stripped = token.strip().lower()
    if stripped in ["assistant", "assistent:", "antwort:"]:
        return ""

    return token