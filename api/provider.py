from __future__ import annotations


class AiApiProvider:
    def __init__(self, streamer, *, keyword_finder, wiki_mode,
                 wiki_proxy_base, wiki_snippet_limit):
        self.streamer = streamer
        self.keyword_finder = keyword_finder
        self.wiki_mode = wiki_mode
        self.wiki_proxy_base = wiki_proxy_base
        self.wiki_snippet_limit = wiki_snippet_limit

    def answer(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return "Bitte stell mir eine Frage 🙂"
        return self.streamer.respond_one_shot(
            q,
            keyword_finder=self.keyword_finder,
            wiki_mode=self.wiki_mode,
            wiki_proxy_base=self.wiki_proxy_base,
            wiki_snippet_limit=self.wiki_snippet_limit,
        ).strip()
