from __future__ import annotations
from config.config_singleton import Config
from config.personas import get_all_persona_names


class UnknownPersonaError(ValueError):
    """Wird ausgelöst, wenn eine unbekannte Persona angefragt wird."""

    pass

cfg = Config()


class AiApiProvider:
    """Stellt KI-Antworten über die API bereit (One-Shot)."""

    def __init__(self, *, keyword_finder, wiki_mode,
                 wiki_proxy_port, wiki_snippet_limit, wiki_timeout, factory):
        self.keyword_finder = keyword_finder
        self.wiki_mode = wiki_mode
        self.wiki_proxy_port = wiki_proxy_port
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_timeout = wiki_timeout
        self.factory = factory
        self._known_personas = tuple(get_all_persona_names())
        self._known_personas_lower = {name.lower() for name in self._known_personas}



    def answer(self, question: str, persona: str) -> str:
        """Bearbeitet eine Frage mit gegebener Persona und gibt die Antwort als Text zurück."""

        frage = (question or "").strip()
       
        if  len(frage)==0:
            return cfg.texts["empty_question"]
        
        persona_name = (persona or "").strip()
        if persona_name.lower() not in self._known_personas_lower:
            known = ", ".join(self._known_personas)
            raise UnknownPersonaError(
                f"Unbekannte Persona '{persona_name}'. Verfügbare Personas: {known}."
            )

        streamer = self.factory.get_streamer_for_persona(persona_name)

        return streamer.respond_one_shot(
            frage,
            keyword_finder=self.keyword_finder,
            wiki_mode=self.wiki_mode,
            wiki_proxy_port=self.wiki_proxy_port,
            wiki_snippet_limit=self.wiki_snippet_limit,
            wiki_timeout=self.wiki_timeout,
            persona=persona_name,

        ).strip()
