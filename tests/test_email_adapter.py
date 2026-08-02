from email.message import EmailMessage

import pytest
from email_adapter.service import EmailAdapterConfig, EmailAdapterService


class FakeProvider:
    def __init__(self):
        self.calls = []

    def answer(self, question, persona):
        self.calls.append((question, persona))
        return f"Antwort von {persona}: {question.strip()}"


class FakeImap:
    def __init__(self, raw_messages):
        self.raw_messages = raw_messages
        self.commands = []
        self.created = []
        self.logged_out = False
        # Schalter für die Fehlerfälle aus #14f.
        self.fail_copy = False
        self.fail_store = False

    def login(self, user, password):
        self.commands.append(("login", user, password))
        return "OK", []

    def select(self, mailbox, readonly=False):
        self.commands.append(("select", mailbox, readonly))
        return "OK", []

    def uid(self, command, *args):
        self.commands.append(("uid", command, *args))
        command_l = command.lower()
        if command_l == "search":
            return "OK", [b" ".join(self.raw_messages.keys())]
        if command_l == "fetch":
            uid = args[0]
            return "OK", [(b"BODY[]", self.raw_messages[uid])]
        if command_l == "copy":
            return ("NO", []) if self.fail_copy else ("OK", [])
        if command_l == "store":
            if self.fail_store:
                raise OSError("IMAP STORE failed")
            return "OK", []
        raise AssertionError(f"Unexpected IMAP uid command: {command} {args}")

    def create(self, mailbox):
        self.created.append(mailbox)
        return "OK", []

    def expunge(self):
        self.commands.append(("expunge",))
        return "OK", []

    def logout(self):
        self.logged_out = True
        return "OK", []


class FakeSmtp:
    def __init__(self):
        self.messages = []
        self.logged_in = None
        self.quit_called = False

    def starttls(self):
        pass

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.messages.append(msg)

    def quit(self):
        self.quit_called = True


def _raw_mail(
    *,
    sender="max@example.org",
    to="lea@example.de",
    body="Hallo Leah",
    headers=None,
):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = "Frage"
    msg["Message-ID"] = "<msg-1@example.org>"
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(body)
    return msg.as_bytes()


def _service(imap, smtp, provider=None, **cfg_overrides):
    return EmailAdapterService(
        _cfg(**cfg_overrides),
        provider or FakeProvider(),
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )


def _cfg(**overrides):
    data = {
        "enabled": True,
        "poll_interval_seconds": 1,
        "address_persona_map": {"lea@example.de": "LEAH"},
        "allowed_senders": ["max@example.org"],
        "imap": {
            "host": "imap.example.de",
            "username": "imap-user@example.de",
            "password": "secret",
        },
        "smtp": {
            "host": "smtp.example.de",
            "username": "smtp-user@example.de",
            "password": "secret",
            "from_address": "lea@example.de",
        },
        "processing": {"processed_mailbox": "Processed"},
    }
    data.update(overrides)
    return EmailAdapterConfig.from_mapping(data)


def test_email_adapter_routes_mail_to_persona_and_replies():
    imap = FakeImap({b"101": _raw_mail()})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = EmailAdapterService(
        _cfg(),
        provider,
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )

    assert service.run_once() == 1

    assert provider.calls == [("Hallo Leah", "LEAH")]
    assert len(smtp.messages) == 1
    reply = smtp.messages[0]
    assert reply["To"] == "max@example.org"
    assert reply["From"] == "lea@example.de"
    assert reply["Subject"] == "Re: Frage"
    assert "Antwort von LEAH" in reply.get_content()
    assert ("uid", "copy", b"101", "Processed") in imap.commands
    assert (
        "uid",
        "store",
        b"101",
        "+FLAGS.SILENT",
        "(\\Deleted \\Seen)",
    ) in imap.commands
    assert smtp.quit_called
    assert imap.logged_out


def test_email_adapter_quotes_original_message_in_reply():
    imap = FakeImap({b"101": _raw_mail(body="Hallo Leah\nWie geht es dir?")})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = EmailAdapterService(
        _cfg(),
        provider,
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )

    assert service.run_once() == 1

    content = smtp.messages[0].get_content()
    assert "max@example.org schrieb:" in content
    assert "> Hallo Leah" in content
    assert "> Wie geht es dir?" in content
    # The persona answer still comes first, above the quoted original.
    assert content.index("Antwort von LEAH") < content.index("> Hallo Leah")


def test_email_adapter_uses_localized_quote_attribution():
    imap = FakeImap({b"101": _raw_mail(body="Hello Leah")})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = EmailAdapterService(
        _cfg(quote={"attribution_no_date": "On older mail {sender} wrote:"}),
        provider,
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )

    assert service.run_once() == 1

    content = smtp.messages[0].get_content()
    assert "On older mail max@example.org wrote:" in content
    assert "> Hello Leah" in content


def test_email_adapter_ignores_unmapped_recipient_and_marks_processed():
    imap = FakeImap({b"102": _raw_mail(to="unknown@example.de")})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = EmailAdapterService(
        _cfg(),
        provider,
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )

    assert service.run_once() == 0

    assert provider.calls == []
    assert smtp.messages == []
    assert ("uid", "copy", b"102", "Processed") in imap.commands


def test_email_adapter_does_not_answer_own_addresses():
    imap = FakeImap({b"103": _raw_mail(sender="lea@example.de")})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = EmailAdapterService(
        _cfg(),
        provider,
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )

    assert service.run_once() == 0

    assert provider.calls == []
    assert smtp.messages == []
    assert ("uid", "copy", b"103", "Processed") in imap.commands


class FakeErrorProvider:
    def __init__(self):
        self.calls = []

    def answer(self, question, persona):
        self.calls.append((question, persona))
        return "[ERROR] LLM is not responding correctly."


def test_email_adapter_keeps_mail_on_llm_error():
    """On a transient LLM failure the mail must stay in the inbox (no reply,
    not marked processed) so the next poll retries it."""
    imap = FakeImap({b"104": _raw_mail()})
    smtp = FakeSmtp()
    provider = FakeErrorProvider()
    service = EmailAdapterService(
        _cfg(),
        provider,
        imap_factory=lambda _cfg: imap,
        smtp_factory=lambda _cfg: smtp,
    )

    assert service.run_once() == 0

    # The LLM was attempted, but nothing is sent and the mail is left untouched.
    assert provider.calls == [("Hallo Leah", "LEAH")]
    assert smtp.messages == []
    assert not any(c[:2] == ("uid", "copy") for c in imap.commands)
    assert not any(c[:2] == ("uid", "store") for c in imap.commands)


def test_email_adapter_resolves_environment_secret(monkeypatch):
    monkeypatch.setenv("MAIL_PASSWORD", "from-env")

    cfg = EmailAdapterConfig.from_mapping(
        {
            "imap": {"password": "env:MAIL_PASSWORD"},
            "smtp": {"password": "${MAIL_PASSWORD}"},
        }
    )

    assert cfg.imap_password == "from-env"
    assert cfg.smtp_password == "from-env"


# ---- Härtung aus Review-Runde 2 (#14) --------------------------------------


def test_the_reply_goes_to_from_not_to_reply_to():
    """Der Reflektor (#14d).

    Mit `Reply-To` konnte ein fremder Absender die Instanz dazu bringen, an
    einen **Dritten** zu schreiben — vom Mailserver des Betreibers, also mit
    gültigem SPF/DKIM seiner Domain, und mit dem Text des Absenders wörtlich im
    Zitat. Beantwortet wird deshalb `From`.
    """
    imap = FakeImap(
        {b"101": _raw_mail(headers={"Reply-To": "opfer@fremde-domain.example"})}
    )
    smtp = FakeSmtp()
    service = _service(imap, smtp)

    assert service.run_once() == 1

    reply = smtp.messages[0]
    assert reply["To"] == "max@example.org"
    assert "opfer@fremde-domain.example" not in str(reply)


def test_reply_to_cannot_smuggle_past_the_loop_protection():
    """Dieselbe Zeile speiste die Schleifenerkennung (#14d).

    Wer `From` auf eine Systemadresse setzte und `Reply-To` woandershin, kam an
    der Prüfung „nicht der eigenen Adresse antworten" vorbei.
    """
    imap = FakeImap(
        {
            b"101": _raw_mail(
                sender="lea@example.de",  # eine Systemadresse
                headers={"Reply-To": "opfer@fremde-domain.example"},
            )
        }
    )
    smtp = FakeSmtp()
    service = _service(imap, smtp, allowed_senders=["@fremde-domain.example"])

    assert service.run_once() == 0
    assert smtp.messages == []


def test_a_sender_outside_the_allowlist_gets_no_answer():
    """Vorher konnte jeder, der die Adresse kennt, die Personas fahren (#14e)."""
    imap = FakeImap({b"101": _raw_mail(sender="fremder@woanders.example")})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = _service(imap, smtp, provider)

    assert service.run_once() == 0
    assert provider.calls == []  # kein LLM-Lauf für Fremde
    assert smtp.messages == []
    # Trotzdem als erledigt markiert, sonst taucht sie bei jedem Poll neu auf.
    assert imap.created == ["Processed"]


def test_a_whole_domain_can_be_allowed():
    """Für ein privates Setup meist genau das, was man will (#14e)."""
    imap = FakeImap({b"101": _raw_mail(sender="irgendwer@example.org")})
    smtp = FakeSmtp()
    service = _service(imap, smtp, allowed_senders=["@example.org"])

    assert service.run_once() == 1
    assert smtp.messages[0]["To"] == "irgendwer@example.org"


def test_a_similar_domain_is_not_allowed():
    """`@example.org` darf nicht auf `evil-example.org` passen."""
    imap = FakeImap({b"101": _raw_mail(sender="wer@evil-example.org")})
    smtp = FakeSmtp()
    service = _service(imap, smtp, allowed_senders=["@example.org"])

    assert service.run_once() == 0
    assert smtp.messages == []


def test_the_adapter_refuses_to_start_without_an_allowlist():
    """Fail-closed wie bei fehlenden Zugangsdaten (#14e).

    Der Dienst kostet LLM-Läufe und verschickt Mail unter der Domain des
    Betreibers — ohne Allowlist gäbe es dafür keinerlei Schranke.
    """
    cfg = _cfg(allowed_senders=[])

    with pytest.raises(ValueError, match="allowed_senders"):
        cfg.validate()


def test_nothing_is_sent_when_the_mail_cannot_be_marked():
    """Der 1440-Mails-Fall (#14f).

    Vorher wurde erst gesendet und dann markiert. Scheiterte das Markieren,
    blieb die Mail UNSEEN und wurde bei jedem Poll erneut beantwortet — bei
    60-s-Poll 1440 Mails am Tag an denselben Empfänger, jede mit einem
    LLM-Lauf. Jetzt gilt: kein Markieren, kein Senden.
    """
    imap = FakeImap({b"101": _raw_mail()})
    imap.fail_store = True  # auch der \Seen-Fallback scheitert
    smtp = FakeSmtp()
    service = _service(imap, smtp)

    assert service.run_once() == 0
    assert smtp.messages == [], "es darf nichts rausgehen, was nicht markiert ist"


def test_a_failed_move_still_marks_the_mail_as_seen():
    """Der Fallback (#14f).

    Ein falscher Ordnertrenner (`INBOX.` statt `INBOX/`, siehe #14a), Quota
    oder fehlende Rechte lassen das Verschieben scheitern. `\\Seen` reicht,
    damit die UNSEEN-Suche die Mail nicht ein zweites Mal findet.
    """
    imap = FakeImap({b"101": _raw_mail()})
    imap.fail_copy = True
    smtp = FakeSmtp()
    service = _service(imap, smtp)

    assert service.run_once() == 1
    assert len(smtp.messages) == 1
    seen_flags = [
        cmd
        for cmd in imap.commands
        if cmd[:2] == ("uid", "store") and "\\Seen" in str(cmd)
    ]
    assert seen_flags, f"kein \\Seen gesetzt: {imap.commands}"


def test_the_reply_is_marked_as_an_automatic_answer():
    """RFC 3834 (#14g) — ein gut erzogener Autoresponder antwortet darauf nicht."""
    imap = FakeImap({b"101": _raw_mail()})
    smtp = FakeSmtp()
    service = _service(imap, smtp)

    assert service.run_once() == 1
    assert smtp.messages[0]["Auto-Submitted"] == "auto-replied"


@pytest.mark.parametrize(
    "headers",
    [
        {"Auto-Submitted": "auto-replied"},
        {"Auto-Submitted": "auto-generated"},
        {"Precedence": "bulk"},
        {"Precedence": "list"},
        {"List-Id": "<news.example.org>"},
        {"List-Unsubscribe": "<mailto:x@example.org>"},
    ],
)
def test_automated_mail_is_not_answered(headers):
    """Sonst dreht sich der Adapter mit dem nächsten Abwesenheitsassistenten
    im Kreis — beide Seiten halten sich für höflich (#14g)."""
    imap = FakeImap({b"101": _raw_mail(headers=headers)})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = _service(imap, smtp, provider)

    assert service.run_once() == 0
    assert provider.calls == []
    assert smtp.messages == []


def test_auto_submitted_no_is_a_normal_mail():
    """`Auto-Submitted: no` heißt laut RFC ausdrücklich *nicht* automatisch."""
    imap = FakeImap({b"101": _raw_mail(headers={"Auto-Submitted": "no"})})
    smtp = FakeSmtp()
    service = _service(imap, smtp)

    assert service.run_once() == 1


def test_an_oversized_body_is_cut_once_for_prompt_and_quote():
    """Ein Limit, eine Kürzung (#14h).

    Gekürzt wird beim Lesen, deshalb erben Prompt *und* Zitat sie automatisch.
    Sonst könnte ein Fremder über das Zitat beliebig viel Text durch die
    Instanz an einen Dritten weitertransportieren.
    """
    imap = FakeImap({b"101": _raw_mail(body="A" * 5000)})
    smtp = FakeSmtp()
    provider = FakeProvider()
    service = _service(imap, smtp, provider, max_body_chars=100)

    assert service.run_once() == 1

    prompt = provider.calls[0][0]
    assert len(prompt) < 200
    assert prompt.endswith("[…]")
    # Kein ununterbrochener Lauf über dem Limit — weder in der Antwort noch im
    # Zitat. (Zählen ginge hier schief: beides steht in derselben Mail.)
    quoted = smtp.messages[0].get_content()
    assert "A" * 101 not in quoted
    assert "[…]" in quoted
