from __future__ import annotations


class AiApiProvider:
    def __init__(self, streamer, *, keyword_finder, wiki_mode,
                 wiki_proxy_port, wiki_snippet_limit, wiki_timeout):
        self.streamer = streamer
        self.keyword_finder = keyword_finder
        self.wiki_mode = wiki_mode
        self.wiki_proxy_port = wiki_proxy_port
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_timeout = wiki_timeout

    def answer(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return "Bitte stell mir eine Frage 🙂"
        return self.streamer.respond_one_shot(
            q,
            keyword_finder=self.keyword_finder,
            wiki_mode=self.wiki_mode,
            wiki_proxy_port=self.wiki_proxy_port,
            wiki_snippet_limit=self.wiki_snippet_limit,
            wiki_timeout=self.wiki_timeout,

        ).strip()
