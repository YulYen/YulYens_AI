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

def replace_wiki_token(text: str, local_ip: str) -> str:
    logging.debug(f"Wiki-Check in Text: {repr(text)}")

    def ersetze(match):
        thema = match.group(1)
        link = f"http://{local_ip}:8080/content/wikipedia_de_all_nopic_2025-06/{thema}"
        ersatz = f"Leah schlägt bei Wikipedia nach: {link}"
        logging.info(f"Ersetze !wiki!{thema} → {ersatz}")
        return ersatz
    return re.sub(r"\[wiki:([^\]]+)\]", ersetze, text)