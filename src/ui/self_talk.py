from __future__ import annotations

import logging
import time

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
    chunk_count = 0
    t_start = time.time()
    first_token_time: float | None = None
    for token in streamer.stream(messages=history):
        if first_token_time is None:
            first_token_time = time.time()
        reply += token
        chunk_count += 1
        print(token, end="", flush=True)
    print()
    t_end = time.time()
    if first_token_time is None:
        t_first_ms = None
    else:
        t_first_ms = int((first_token_time - t_start) * 1000)
    logging.info(
        "Self talk stream done for %s: chunks=%d chars=%d t_first_ms=%s t_total_ms=%d",
        label,
        chunk_count,
        len(reply),
        t_first_ms,
        int((t_end - t_start) * 1000),
    )
    if chunk_count == 0:
        logging.warning("Self talk stream for %s produced no output chunks.", label)
    return reply


def _build_self_talk_guardrail(
    texts: dict, persona_self: str, persona_other: str, task: str
) -> str:
    return texts.format(
        "terminal_self_talk_guardrail",
        persona_self=persona_self,
        persona_other=persona_other,
        task=task,
    )


def run(factory, config, terminal_ui) -> None:
    texts = config.texts
    print(texts["terminal_self_talk_title"])
    persona_a = _choose_persona(texts, texts["terminal_self_talk_persona_a_prompt"])
    persona_b = _choose_persona(texts, texts["terminal_self_talk_persona_b_prompt"])
    initial_prompt = _prompt_initial(texts)

    streamer_a = factory.get_streamer_for_persona(persona_a)
    streamer_b = factory.get_streamer_for_persona(persona_b)

    history_a: list[dict[str, str]] = [
        {
            "role": "user",
            "content": _build_self_talk_guardrail(
                texts, persona_a, persona_b, initial_prompt
            ),
        }
    ]
    history_b: list[dict[str, str]] = [
        {
            "role": "user",
            "content": _build_self_talk_guardrail(
                texts, persona_b, persona_a, initial_prompt
            ),
        }
    ]

    logging.info("Starting self talk between %s and %s", persona_a, persona_b)
    logging.info("Initial prompt length: %d", len(initial_prompt))

    try:
        turn_a = True
        turn_index = 1
        while True:
            if turn_a:
                logging.info(
                    "Self talk turn %d (A): persona=%s history_a=%d history_b=%d",
                    turn_index,
                    persona_a,
                    len(history_a),
                    len(history_b),
                )
                reply = _stream_reply(streamer_a, history_a, persona_a)
                history_a.append({"role": "assistant", "content": reply})
                history_b.append({"role": "user", "content": reply})
            else:
                logging.info(
                    "Self talk turn %d (B): persona=%s history_a=%d history_b=%d",
                    turn_index,
                    persona_b,
                    len(history_a),
                    len(history_b),
                )
                reply = _stream_reply(streamer_b, history_b, persona_b)
                terminal_ui._maybe_create_tts_wav(reply, True)
                history_b.append({"role": "assistant", "content": reply})
                history_a.append({"role": "user", "content": reply})
            logging.info("Self talk turn %d complete (reply length: %d)", turn_index, len(reply))
            if not reply.strip():
                logging.warning("Self talk turn %d returned an empty reply.", turn_index)
            stripped_reply = reply.strip()
            if "_endegelaende_" in stripped_reply or stripped_reply.endswith("_ende_"):
                logging.info(
                    "Self talk ended with end token at turn %d (reply suffix).", turn_index
                )
                break
            turn_a = not turn_a
            turn_index += 1
    except KeyboardInterrupt:
        logging.info("Self talk stopped by user.")
        print()
        print(texts.get("terminal_self_talk_exit", "Stopping self talk."))
