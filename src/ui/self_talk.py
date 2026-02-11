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


def _build_self_talk_guardrail(
    texts: dict, persona_self: str, persona_other: str, task: str
) -> str:
    return texts.format(
        "terminal_self_talk_guardrail",
        persona_self=persona_self,
        persona_other=persona_other,
        task=task,
    )


def is_end_of_self_talk(reply: str) -> bool:
    stripped_reply = (reply or "").strip()
    return "endegelaende" in stripped_reply or stripped_reply.endswith("_ende_")


class SelfTalkRunner:
    def __init__(
        self,
        factory,
        texts: dict,
        persona_a: str,
        persona_b: str,
        initial_prompt: str,
    ):
        self.persona_a = persona_a
        self.persona_b = persona_b
        self.turn_a = True
        self.turn_index = 1
        self.streamer_a = factory.get_streamer_for_persona(persona_a)
        self.streamer_b = factory.get_streamer_for_persona(persona_b)

        self.history_a: list[dict[str, str]] = [
            {
                "role": "user",
                "content": _build_self_talk_guardrail(
                    texts, persona_a, persona_b, initial_prompt
                ),
            }
        ]
        self.history_b: list[dict[str, str]] = [
            {
                "role": "user",
                "content": _build_self_talk_guardrail(
                    texts, persona_b, persona_a, initial_prompt
                ),
            }
        ]

    def _current_turn(self):
        if self.turn_a:
            return self.persona_a, self.streamer_a, self.history_a
        return self.persona_b, self.streamer_b, self.history_b

    def run_turn(self, on_token=None) -> tuple[str, str, bool, int]:
        persona_name, streamer, history = self._current_turn()
        reply = ""
        t_start = time.time()
        first_token_time: float | None = None
        chunk_count = 0

        for token in streamer.stream(messages=history):
            if first_token_time is None:
                first_token_time = time.time()
            reply += token
            chunk_count += 1
            if on_token is not None:
                on_token(persona_name, token)

        if self.turn_a:
            self.history_a.append({"role": "assistant", "content": reply})
            self.history_b.append({"role": "user", "content": reply})
        else:
            self.history_b.append({"role": "assistant", "content": reply})
            self.history_a.append({"role": "user", "content": reply})

        t_end = time.time()
        t_first_ms = None if first_token_time is None else int((first_token_time - t_start) * 1000)
        logging.info(
            "Self talk stream done for %s: chunks=%d chars=%d t_first_ms=%s t_total_ms=%d",
            persona_name,
            chunk_count,
            len(reply),
            t_first_ms,
            int((t_end - t_start) * 1000),
        )
        if chunk_count == 0:
            logging.warning("Self talk stream for %s produced no output chunks.", persona_name)

        should_stop = is_end_of_self_talk(reply)
        current_turn_index = self.turn_index
        if not should_stop:
            self.turn_a = not self.turn_a
            self.turn_index += 1

        return persona_name, reply, should_stop, current_turn_index


def run(factory, config, terminal_ui) -> None:
    texts = config.texts
    print(texts["terminal_self_talk_title"])
    persona_a = _choose_persona(texts, texts["terminal_self_talk_persona_a_prompt"])
    persona_b = _choose_persona(texts, texts["terminal_self_talk_persona_b_prompt"])
    initial_prompt = _prompt_initial(texts)

    runner = SelfTalkRunner(factory, texts, persona_a, persona_b, initial_prompt)

    logging.info("Starting self talk between %s and %s", persona_a, persona_b)
    logging.info("Initial prompt length: %d", len(initial_prompt))

    try:
        while True:
            active_persona = runner.persona_a if runner.turn_a else runner.persona_b
            logging.info(
                "Self talk turn %d: persona=%s history_a=%d history_b=%d",
                runner.turn_index,
                active_persona,
                len(runner.history_a),
                len(runner.history_b),
            )
            print(f"{Fore.CYAN}[{active_persona}]{Style.RESET_ALL} ", end="", flush=True)
            persona_name, reply, should_stop, turn_index = runner.run_turn(
                on_token=lambda _persona, token: print(token, end="", flush=True)
            )
            print()
            terminal_ui._maybe_create_tts_wav(reply, True, persona_name=persona_name)
            logging.info("Self talk turn %d complete (reply length: %d)", turn_index, len(reply))
            if not reply.strip():
                logging.warning("Self talk turn %d returned an empty reply.", turn_index)
            if should_stop:
                logging.info(
                    "Self talk ended with end token at turn %d (reply suffix).", turn_index
                )
                break
    except KeyboardInterrupt:
        logging.info("Self talk stopped by user.")
        print()
        print(texts.get("terminal_self_talk_exit", "Stopping AI Dialog."))
