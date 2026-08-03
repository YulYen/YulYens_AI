"""Der nutzergebundene Zugriff auf gespeicherte Gespräche (#25/#56).

Hier wohnt eine Sicherheitszusage, keine bloße Datenbeschaffung: **jeder** Weg
in ein gespeichertes Gespräch reicht den Nutzer an die Ablage durch. Die
Gesprächs-ID kommt aus einem `gr.Dropdown`, dessen `preprocess` den Wert des
Clients ungeprüft durchreichte (GHSA-26jh-r8g2-6fpr) — die Auswahl im Browser
ist also keine Schranke.

Bis zur Herauslösung ging jede Aussage darüber durch ein volles `WebUI`-Objekt.
Jetzt steht sie hier, wo sie hingehört.
"""

import pytest
from ui.history_access import DEFAULT_HISTORY_LIMIT, ConversationHistory


class _Ref:
    def __init__(self, ref_id, user):
        self.id = ref_id
        self.user = user
        self.persona = "LEAH"
        self.model = "m"
        self.title = "Titel"
        self.created_at = "2026-08-03T10:00:00"
        self.updated_at = "2026-08-03T10:00:00"
        self.app = "web"


class _Store:
    """Ablage, die den Nutzer ernst nimmt — wie die echte seit #54."""

    def __init__(self, owners: dict[str, str]):
        self.owners = owners
        self.calls: list[tuple] = []

    def list_conversations(self, user, limit):
        self.calls.append(("list", user, limit))
        return [_Ref(i, owner) for i, owner in self.owners.items() if owner == user]

    def load(self, conversation_id, *, user=None):
        self.calls.append(("load", conversation_id, user))
        if self.owners.get(conversation_id) != user:
            return None
        return _Ref(conversation_id, user), [{"role": "user", "content": "Frage"}]

    def delete(self, conversation_id, *, user=None):
        self.calls.append(("delete", conversation_id, user))
        return self.owners.get(conversation_id) == user


def _history(owners, **kwargs):
    store = _Store(owners)
    return ConversationHistory(lambda: store, **kwargs), store


# ---- Die Zusage -----------------------------------------------------------


def test_a_foreign_conversation_behaves_like_a_missing_one():
    """Die Antwort darf nicht verraten, dass es die ID gibt."""
    history, _ = _history({"c-fremd": "andere"})
    assert history.load("c-fremd", "ich") is None


def test_deleting_a_foreign_conversation_does_nothing():
    history, _ = _history({"c-fremd": "andere"})
    assert history.delete("c-fremd", "ich") is False


def test_the_own_conversation_opens():
    history, _ = _history({"c-1": "ich"})
    loaded = history.load("c-1", "ich")
    assert loaded is not None
    ref, messages = loaded
    assert ref.id == "c-1"
    assert messages


@pytest.mark.parametrize("method", ["load", "delete"])
def test_every_way_in_passes_the_user_to_the_store(method):
    """Die eigentliche Zusage: kein Weg kommt am Nutzer vorbei."""
    history, store = _history({"c-1": "ich"})
    getattr(history, method)("c-1", "ich")
    assert store.calls[-1][2] == "ich", store.calls


def test_the_listing_only_shows_the_own_conversations():
    history, _ = _history({"c-1": "ich", "c-2": "andere", "c-3": "ich"})
    assert [cid for _label, cid in history.choices("ich")] == ["c-1", "c-3"]


def test_an_anonymous_user_gets_the_fallback_identity():
    """Ohne Anmeldung sind alle `local` (#72) — leer wäre eine andere Zusage."""
    history, store = _history({}, fallback_user="local")
    history.choices(None)
    assert store.calls[-1][1] == "local"


# ---- Kein leerer Aufruf ---------------------------------------------------


def test_an_empty_id_never_reaches_the_store():
    history, store = _history({"c-1": "ich"})
    assert history.load("", "ich") is None
    assert history.delete(None, "ich") is False
    assert store.calls == []


# ---- Grenze und Robustheit ------------------------------------------------


def test_the_limit_comes_from_the_config():
    history, store = _history({}, limit=2)
    history.choices("ich")
    assert store.calls[-1][2] == 2


@pytest.mark.parametrize("nonsense", ["viele", None, 0, -5])
def test_nonsense_limits_fall_back_instead_of_breaking(nonsense):
    history, store = _history({}, limit=nonsense)
    history.choices("ich")
    assert store.calls[-1][2] >= 1
    if nonsense in ("viele", None):
        assert history.limit == DEFAULT_HISTORY_LIMIT


def test_a_broken_store_costs_the_list_not_the_page():
    """Ein Fehlschlag darf die Oberfläche nie zerreißen."""

    class _Boom:
        def list_conversations(self, **_kwargs):
            raise RuntimeError("Datei weg")

        def load(self, *_args, **_kwargs):
            raise RuntimeError("Datei weg")

        def delete(self, *_args, **_kwargs):
            raise RuntimeError("Datei weg")

    history = ConversationHistory(lambda: _Boom())
    assert history.choices("ich") == []
    assert history.load("c-1", "ich") is None
    assert history.delete("c-1", "ich") is False
