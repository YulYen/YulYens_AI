from __future__ import annotations

import logging

from colorama import Fore, Style

from config.personas import get_all_persona_names, _load_system_prompts


def _choose_persona(texts: dict, prompt: str) -> str:
    names = get_all_persona_names()
    print(texts["choose_persona"])
    for idx, name in enumerate(names, start=1):
        desc = next(p for p in _load_system_prompts() if p["name"] == name)["description"]
        persona_line = f"{idx}. {name} – {desc}"
        print(persona_line)

    while True:
        sel = input(f"{prompt} ").strip()
        try:
            choice = int(sel) - 1
            if 0 <= choice < len(names):
                persona_name = names[choice]
                print(
                    texts["terminal_persona_selected"].format(persona_name=persona_name)
                )
                return persona_name
        except ValueError:
            pass
        print(texts["terminal_invalid_selection"])


def _prompt_initial(texts: dict) -> str:
    while True:
        initial = input(texts["terminal_self_talk_initial_prompt"] + " ").strip()
        if initial:
            return initial
        hint = texts.get("terminal_self_talk_initial_prompt_required")
        if hint:
            print(f"{Fore.YELLOW}{hint}{Style.RESET_ALL}")


def _stream_reply(streamer, history: list[dict[str, str]], label: str) -> str:
    print(f"{Fore.CYAN}[{label}]{Style.RESET_ALL} ", end="", flush=True)
    reply = ""
    for token in streamer.stream(messages=history):
        reply += token
        print(token, end="", flush=True)
    print()
    return reply


def run(factory, config) -> None:
    texts = config.texts
    print(texts["terminal_self_talk_title"])
    persona_a = _choose_persona(texts, texts["terminal_self_talk_persona_a_prompt"])
    persona_b = _choose_persona(texts, texts["terminal_self_talk_persona_b_prompt"])
    initial_prompt = _prompt_initial(texts)

    streamer_a = factory.get_streamer_for_persona(persona_a)
    streamer_b = factory.get_streamer_for_persona(persona_b)

    history_a: list[dict[str, str]] = [{"role": "user", "content": initial_prompt}]
    history_b: list[dict[str, str]] = []

    logging.info("Starting self talk between %s and %s", persona_a, persona_b)

    try:
        turn_a = True
        while True:
            if turn_a:
                reply = _stream_reply(streamer_a, history_a, persona_a)
                history_a.append({"role": "assistant", "content": reply})
                history_b.append({"role": "user", "content": reply})
            else:
                reply = _stream_reply(streamer_b, history_b, persona_b)
                history_b.append({"role": "assistant", "content": reply})
                history_a.append({"role": "user", "content": reply})
            turn_a = not turn_a
    except KeyboardInterrupt:
        print()
        print(texts.get("terminal_self_talk_exit", "Stopping self talk."))
