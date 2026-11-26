"""Blind tasting (#99): probes, the two sides, the sheet and its key.

The key is the part that must never be wrong silently: a verdict credited to
the wrong side turns the next tuning decision around, and nobody would notice —
the sheet is blind by design.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
import yaml
from yulyen_ai.config import personas
from yulyen_ai.config.config_singleton import Config
from yulyen_ai.evals import tasting
from yulyen_ai.evals.tasting import Probe, Side, TastingError


def _side(label: str, answers: dict[str, str], errors: dict[str, str] | None = None):
    errors = errors or {}
    return {
        "label": label,
        "model": "m",
        "seed": 0,
        "commit": "abc",
        "warnings": [],
        "probes": [
            {
                "id": pid,
                "persona": "LEAH",
                "turns": (
                    [] if pid in errors else [{"user": f"q {pid}", "assistant": text}]
                ),
                "error": errors.get(pid, ""),
            }
            for pid, text in answers.items()
        ],
    }


def _sides(n: int = 6):
    ids = [f"p{i}" for i in range(n)]
    return (
        _side("seite-alt", {pid: f"ALT {pid}" for pid in ids}),
        _side("seite-neu", {pid: f"NEU {pid}" for pid in ids}),
    )


# --- probes -------------------------------------------------------------------


def test_shipped_probes_cover_every_classic_persona():
    probes = tasting.load_probes()

    assert len(probes) == 14
    assert {p.persona for p in probes} == set(personas.get_all_persona_names())


def test_duplicate_probe_ids_are_refused(tmp_path):
    path = tmp_path / "probes.yaml"
    probe = {"id": "x", "persona": "LEAH", "turns": ["Hallo"]}
    path.write_text(yaml.safe_dump({"probes": [probe, probe]}), encoding="utf-8")

    with pytest.raises(TastingError, match="twice"):
        tasting.load_probes(path)


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("classic", Side("classic")),
        ("classic@main", Side("classic", "main")),
        (
            "examples/classic_ministral14b@v2.0.0",
            Side("examples/classic_ministral14b", "v2.0.0"),
        ),
    ],
)
def test_side_spec(spec, expected):
    assert Side.parse(spec) == expected


@pytest.mark.parametrize("spec", ["", "@main", "classic@"])
def test_unreadable_side_spec(spec):
    with pytest.raises(TastingError):
        Side.parse(spec)


# --- one side -----------------------------------------------------------------


@pytest.mark.parametrize("ref", [None, "HEAD"])
def test_materialized_ensemble_is_what_the_persona_loader_reads(tmp_path, ref):
    """The copy is used, seeded — and the checked-in ensemble stays untouched."""
    checked_in = Path(tasting.REPO_ROOT, "ensembles/classic/personas_base.yaml")
    before = checked_in.read_bytes()

    target = tasting.materialize_ensemble(Side("classic", ref), tmp_path, seed=7)
    marker = "MARKIERUNG DER KOPIE"
    locale = target / "locales" / "de" / "personas.yaml"
    data = yaml.safe_load(locale.read_text(encoding="utf-8"))
    data["personas"]["LEAH"]["prompt"] = marker
    locale.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    cfg = Config("config.yaml")
    cfg.language = "de"
    cfg.ensemble = str(target)

    assert personas.get_prompt_by_name("LEAH") == marker
    assert (personas.get_options("LEAH") or {})["seed"] == 7
    assert checked_in.read_bytes() == before
    assert "seed" not in yaml.safe_load(before)["personas"][0].get("llm_options", {})


def test_no_seed_leaves_the_options_as_they_are(tmp_path):
    target = tasting.materialize_ensemble(Side("classic"), tmp_path, seed=None)
    base = yaml.safe_load((target / "personas_base.yaml").read_text(encoding="utf-8"))

    assert all("seed" not in (p.get("llm_options") or {}) for p in base["personas"])


def test_unknown_ref_and_unknown_ensemble_are_reported(tmp_path):
    with pytest.raises(TastingError, match="gibtsnicht"):
        tasting.materialize_ensemble(Side("classic", "gibtsnicht"), tmp_path, seed=0)
    with pytest.raises(TastingError, match="personas_base"):
        tasting.materialize_ensemble(Side("gibtsnicht"), tmp_path / "b", seed=0)


def test_each_turn_sees_the_sides_own_earlier_replies():
    seen: list[list[dict[str, str]]] = []

    def reply(persona, messages):
        seen.append(messages)
        return f"Antwort {len(messages)}"

    probe = Probe(id="p", persona="LEAH", turns=("eins", "zwei"))
    [result] = tasting.collect_answers([probe], reply)

    assert seen[1] == [
        {"role": "user", "content": "eins"},
        {"role": "assistant", "content": "Antwort 1"},
        {"role": "user", "content": "zwei"},
    ]
    assert [t["assistant"] for t in result["turns"]] == ["Antwort 1", "Antwort 3"]
    assert result["error"] == ""


def test_a_backend_error_is_an_error_not_an_answer():
    """Ollama down arrives as text (#95) — it must not be tasted as an answer."""
    probe = Probe(id="p", persona="LEAH", turns=("eins", "zwei"))
    [result] = tasting.collect_answers(
        [probe], lambda _p, _m: "BACKEND KAPUTT", error_marker="BACKEND"
    )

    assert result["error"].startswith("backend error")
    assert result["turns"] == []


# --- sheet and key --------------------------------------------------------------


def test_sheet_names_no_side():
    alt, neu = _sides()
    sheet, _key = tasting.build_sheet(alt, neu, random.Random(0))

    assert "seite-alt" not in sheet and "seite-neu" not in sheet


@pytest.mark.parametrize("n", [6, 7, 14])
def test_sides_are_split_evenly_across_positions(n):
    alt, neu = _sides(n)
    _sheet, key = tasting.build_sheet(alt, neu, random.Random(3))

    alt_first = sum(1 for order in key["order"].values() if order["1"] == "a")
    assert alt_first in (n // 2, n - n // 2)


def test_key_points_at_the_side_that_wrote_the_text():
    """Whatever stands under 'Seite 1' must be what the key calls side 1."""
    alt, neu = _sides(8)
    sheet, key = tasting.build_sheet(alt, neu, random.Random(5))

    for pid, order in key["order"].items():
        block = sheet.split(f"<!-- probe: {pid} -->")[1].split("---")[0]
        first_text = block.split("### Seite 1")[1].split("### Seite 2")[0]
        expected = "ALT" if order["1"] == "a" else "NEU"
        assert f"{expected} {pid}" in first_text


def test_probes_with_an_error_on_either_side_are_left_out():
    ids = {"p0": "x", "p1": "y"}
    alt = _side("alt", ids, errors={"p1": "kaputt"})
    neu = _side("neu", ids)
    sheet, key = tasting.build_sheet(alt, neu, random.Random(0))

    assert "p1" not in key["order"] and key["skipped"] == {"p1": "kaputt"}
    assert "<!-- probe: p1 -->" not in sheet


def test_sides_with_different_probes_are_refused():
    alt = _side("alt", {"p0": "x"})
    neu = _side("neu", {"p9": "y"})

    with pytest.raises(TastingError, match="different probes"):
        tasting.build_sheet(alt, neu, random.Random(0))


# --- tally ---------------------------------------------------------------------


def _judge(sheet: str, verdicts: list[str]) -> str:
    it = iter(verdicts)
    return "\n".join(
        f"Urteil: {next(it)}" if line.startswith("Urteil:") else line
        for line in sheet.splitlines()
    )


def test_tally_credits_the_side_behind_the_position():
    alt, neu = _sides(4)
    sheet, key = tasting.build_sheet(alt, neu, random.Random(1))
    # Immer die Seite wählen, auf der der NEU-Text steht.
    picks = ["1" if key["order"][pid]["1"] == "b" else "2" for pid in key["order"]]
    judged = _judge(sheet, picks).replace("Kommentar: ", "Kommentar: mehr Herz", 1)

    result = tasting.tally(judged, key, {pid: "LEAH" for pid in key["order"]})

    assert result.rows["LEAH"] == {"a": 0, "b": 4, "=": 0, "": 0}
    assert result.comments == [(next(iter(key["order"])), "seite-neu", "mehr Herz")]
    assert "| **gesamt** | **0** | **4** |" in tasting.format_tally(result)


def test_tally_counts_equal_and_open():
    alt, neu = _sides(3)
    sheet, key = tasting.build_sheet(alt, neu, random.Random(1))

    result = tasting.tally(_judge(sheet, ["=", "gleich", ""]), key, {})

    assert result.total() == {"a": 0, "b": 0, "=": 2, "": 1}


def test_a_verdict_that_is_not_one_two_or_equal_is_refused():
    alt, neu = _sides(2)
    sheet, key = tasting.build_sheet(alt, neu, random.Random(1))

    with pytest.raises(TastingError, match="expected 1, 2 or ="):
        tasting.tally(_judge(sheet, ["links", "1"]), key, {})
