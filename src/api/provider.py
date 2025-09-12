from __future__ import annotations
from config.config_singleton import Config

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



    def answer(self, question: str, persona: str) -> str:
        """Bearbeitet eine Frage mit gegebener Persona und gibt die Antwort als Text zurück."""

        frage = (question or "").strip()
       
        if  len(frage)==0:
            return cfg.texts["empty_question"]
        
        streamer = self.factory.get_streamer_for_persona(persona)

        return streamer.respond_one_shot(
            frage,
            keyword_finder=self.keyword_finder,
            wiki_mode=self.wiki_mode,
            wiki_proxy_port=self.wiki_proxy_port,
            wiki_snippet_limit=self.wiki_snippet_limit,
            wiki_timeout=self.wiki_timeout,
            persona=persona,

        ).strip()
