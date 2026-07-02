from ui.persona_chooser import prompt_persona_choice

TEXTS = {
    "choose_persona": "Wähle eine Persona:",
    "terminal_persona_prompt": "Nummer:",
    "terminal_invalid_selection": "Ungültige Auswahl.",
}

PERSONAS = [
    {"name": "LEAH", "description": "warmherzig"},
    {"name": "PETER", "description": "sachlich"},
]


def _patch_personas(monkeypatch):
    monkeypatch.setattr("ui.persona_chooser._load_system_prompts", lambda: PERSONAS)


def test_valid_choice_returns_persona_name(monkeypatch, capsys):
    _patch_personas(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    result = prompt_persona_choice(["LEAH", "PETER"], TEXTS, "terminal_persona_prompt")

    assert result == "PETER"
    out = capsys.readouterr().out
    assert "1. LEAH – warmherzig" in out
    assert "2. PETER – sachlich" in out


def test_invalid_inputs_reprompt_until_valid(monkeypatch, capsys):
    _patch_personas(monkeypatch)
    answers = iter(["abc", "0", "99", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    result = prompt_persona_choice(["LEAH", "PETER"], TEXTS, "terminal_persona_prompt")

    assert result == "LEAH"
    out = capsys.readouterr().out
    assert out.count(TEXTS["terminal_invalid_selection"]) == 3
