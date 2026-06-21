from email.message import EmailMessage

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
        if command_l in {"copy", "store"}:
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


def _raw_mail(*, sender="max@example.org", to="lea@example.de", body="Hallo Leah"):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = "Frage"
    msg["Message-ID"] = "<msg-1@example.org>"
    msg.set_content(body)
    return msg.as_bytes()


def _cfg(**overrides):
    data = {
        "enabled": True,
        "poll_interval_seconds": 1,
        "address_persona_map": {"lea@example.de": "LEAH"},
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
