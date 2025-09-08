from __future__ import annotations
from config.config_singleton import Config

cfg = Config()


class AiApiProvider:
    def __init__(self, *, keyword_finder, wiki_mode,
                 wiki_proxy_port, wiki_snippet_limit, wiki_timeout, factory):
        self.keyword_finder = keyword_finder
        self.wiki_mode = wiki_mode
        self.wiki_proxy_port = wiki_proxy_port
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_timeout = wiki_timeout
        self.factory = factory



    def answer(self, question: str, persona: str) -> str:
        q = (question or "").strip()
        if not q:
            return cfg.ui["texts"]["empty_question"]
        
        streamer = self.factory.get_streamer_for_persona(persona)

        return streamer.respond_one_shot(
            q,
            keyword_finder=self.keyword_finder,
            wiki_mode=self.wiki_mode,
            wiki_proxy_port=self.wiki_proxy_port,
            wiki_snippet_limit=self.wiki_snippet_limit,
            wiki_timeout=self.wiki_timeout,
            persona=persona,

        ).strip()
