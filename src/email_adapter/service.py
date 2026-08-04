from __future__ import annotations

import html
import imaplib
import logging
import re
import smtplib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.policy import default
from email.utils import getaddresses, make_msgid, parseaddr
from typing import Protocol, cast

from api.provider import AiApiProvider
from core.utils import resolve_secret

# Sichtbare Markierung am Ende eines gekürzten Mailtextes (#14h).
_TRUNCATION_MARKER = " […]"


class ImapClient(Protocol):
    def login(self, user: str, password: str): ...
    def select(self, mailbox: str, readonly: bool = False): ...
    def uid(self, command: str, *args): ...
    def create(self, mailbox: str): ...
    def expunge(self): ...
    def logout(self): ...


class SmtpClient(Protocol):
    def starttls(self): ...
    def login(self, user: str, password: str): ...
    def send_message(self, msg: EmailMessage): ...
    def quit(self): ...


@dataclass(frozen=True)
class EmailAdapterConfig:
    """Runtime settings for the persona e-mail adapter."""

    enabled: bool = False
    poll_interval_seconds: int = 60
    address_persona_map: dict[str, str] = field(default_factory=dict)
    # Wer den Adapter überhaupt benutzen darf (#14e). Einträge sind entweder
    # eine volle Adresse ("max@example.org") oder eine ganze Domain
    # ("@example.org"). Pflichtfeld bei `enabled: true` — ohne Liste fährt
    # jeder, der die Adresse kennt, die Personas.
    allowed_senders: tuple[str, ...] = ()
    # Obergrenze für den übernommenen Mailtext (#14h). Gilt einmal beim Lesen,
    # deshalb erben Prompt *und* Antwortzitat sie automatisch.
    max_body_chars: int = 4000
    source_mailbox: str = "INBOX"
    processed_mailbox: str | None = "INBOX/YulYenProcessed"
    processed_flag: str = "YulYenProcessed"
    search_criteria: str = "UNSEEN"

    imap_host: str = ""
    imap_port: int = 993
    imap_ssl: bool = True
    imap_username: str = ""
    imap_password: str = ""

    smtp_host: str = ""
    smtp_port: int = 465
    smtp_ssl: bool = True
    smtp_starttls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""

    # Localized templates for the quoted original mail in replies.
    quote_attribution: str = "Am {date} schrieb {sender}:"
    quote_attribution_no_date: str = "{sender} schrieb:"

    @classmethod
    def from_mapping(cls, data: dict | None) -> EmailAdapterConfig:
        data = data or {}
        imap_cfg = data.get("imap", {}) or {}
        smtp_cfg = data.get("smtp", {}) or {}
        processing_cfg = data.get("processing", {}) or {}
        quote_cfg = data.get("quote", {}) or {}

        return cls(
            enabled=_as_bool(data.get("enabled", False)),
            poll_interval_seconds=max(1, int(data.get("poll_interval_seconds", 60))),
            address_persona_map=_normalize_mapping(data.get("address_persona_map", {})),
            allowed_senders=_normalize_allowlist(data.get("allowed_senders")),
            max_body_chars=max(0, int(data.get("max_body_chars", 4000))),
            source_mailbox=str(processing_cfg.get("source_mailbox", "INBOX")),
            processed_mailbox=_optional_str(
                processing_cfg.get("processed_mailbox", "INBOX/YulYenProcessed")
            ),
            processed_flag=str(processing_cfg.get("processed_flag", "YulYenProcessed")),
            search_criteria=str(processing_cfg.get("search_criteria", "UNSEEN")),
            imap_host=str(imap_cfg.get("host", "")),
            imap_port=int(imap_cfg.get("port", 993)),
            imap_ssl=_as_bool(imap_cfg.get("ssl", True)),
            imap_username=resolve_secret(imap_cfg.get("username", "")),
            imap_password=resolve_secret(imap_cfg.get("password", "")),
            smtp_host=str(smtp_cfg.get("host", "")),
            smtp_port=int(smtp_cfg.get("port", 465)),
            smtp_ssl=_as_bool(smtp_cfg.get("ssl", True)),
            smtp_starttls=_as_bool(smtp_cfg.get("starttls", False)),
            smtp_username=resolve_secret(smtp_cfg.get("username", "")),
            smtp_password=resolve_secret(smtp_cfg.get("password", "")),
            smtp_from_address=resolve_secret(smtp_cfg.get("from_address", "")),
            quote_attribution=str(quote_cfg.get("attribution", cls.quote_attribution)),
            quote_attribution_no_date=str(
                quote_cfg.get("attribution_no_date", cls.quote_attribution_no_date)
            ),
        )

    @property
    def system_addresses(self) -> set[str]:
        addresses = set(self.address_persona_map)
        for candidate in (
            self.imap_username,
            self.smtp_username,
            self.smtp_from_address,
        ):
            parsed = _addr(candidate)
            if parsed:
                addresses.add(parsed)
        return addresses

    def sender_allowed(self, sender: str) -> bool:
        """Steht dieser Absender auf der Allowlist? (#14e)

        Ein Eintrag ist entweder eine volle Adresse oder eine ganze Domain
        (``@example.org``). Bewusst kein Regex: eine falsch gesetzte öffnet die
        Liste still für alle, und genau diese Fehlerrichtung meldet sich nie
        von selbst (siehe #62).
        """
        address = _addr(sender)
        if not address:
            return False
        domain = address.rpartition("@")[2]
        for entry in self.allowed_senders:
            if entry.startswith("@"):
                if domain and domain == entry[1:]:
                    return True
            elif address == entry:
                return True
        return False

    def validate(self) -> None:
        if not self.enabled:
            return
        missing = []
        if not self.imap_host:
            missing.append("email_adapter.imap.host")
        if not self.imap_username:
            missing.append("email_adapter.imap.username")
        if not self.imap_password:
            missing.append("email_adapter.imap.password")
        if not self.smtp_host:
            missing.append("email_adapter.smtp.host")
        if not self.smtp_username:
            missing.append("email_adapter.smtp.username")
        if not self.smtp_password:
            missing.append("email_adapter.smtp.password")
        if not self.address_persona_map:
            missing.append("email_adapter.address_persona_map")
        # Fail-closed, wie bei fehlenden Zugangsdaten: der Dienst kostet
        # LLM-Läufe und verschickt Mail unter der Domain des Betreibers. Ohne
        # Allowlist gäbe es dafür keinerlei Schranke.
        if not self.allowed_senders:
            missing.append("email_adapter.allowed_senders")
        if missing:
            raise ValueError(
                "Missing e-mail adapter configuration: " + ", ".join(missing)
            )


@dataclass(frozen=True)
class IncomingEmail:
    uid: bytes
    sender: str
    recipients: list[str]
    subject: str
    body: str
    message_id: str | None
    date: str = ""
    automated: bool = False


class EmailAdapterService:
    """Polls an IMAP mailbox, routes messages to personas and replies via SMTP."""

    def __init__(
        self,
        cfg: EmailAdapterConfig,
        provider: AiApiProvider,
        *,
        imap_factory: Callable[[EmailAdapterConfig], ImapClient] | None = None,
        smtp_factory: Callable[[EmailAdapterConfig], SmtpClient] | None = None,
    ) -> None:
        self.cfg = cfg
        self.provider = provider
        self._imap_factory = imap_factory or open_imap
        self._smtp_factory = smtp_factory or open_smtp
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        logging.info("E-mail adapter polling started.")
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logging.exception("E-mail adapter polling cycle failed.")
            self._stop_event.wait(self.cfg.poll_interval_seconds)
        logging.info("E-mail adapter polling stopped.")

    def run_once(self) -> int:
        """Processes currently available messages once. Returns successful replies."""

        self.cfg.validate()
        if not self.cfg.enabled:
            logging.info("E-mail adapter is disabled by configuration.")
            return 0

        imap = self._imap_factory(self.cfg)
        processed_count = 0
        try:
            imap.login(self.cfg.imap_username, self.cfg.imap_password)
            imap.select(self.cfg.source_mailbox, readonly=False)
            for uid in self._search_uids(imap):
                if self._process_uid(imap, uid):
                    processed_count += 1
        finally:
            _safe_imap_logout(imap)

        return processed_count

    def _search_uids(self, imap: ImapClient) -> list[bytes]:
        status, data = imap.uid("search", None, self.cfg.search_criteria)
        if status != "OK" or not data:
            logging.warning("IMAP search returned status=%s data=%s", status, data)
            return []
        return data[0].split()

    def _process_uid(self, imap: ImapClient, uid: bytes) -> bool:
        try:
            incoming = self._fetch_email(imap, uid)
            if incoming is None:
                return False

            persona = self._persona_for(incoming.recipients)
            if persona is None:
                logging.info(
                    "Ignoring e-mail uid=%s because no recipient maps to a persona: %s",
                    uid.decode(errors="replace"),
                    incoming.recipients,
                )
                self._mark_processed(imap, uid)
                return False

            if incoming.sender in self.cfg.system_addresses:
                logging.warning(
                    "Ignoring e-mail uid=%s from own/system address %s to avoid loops.",
                    uid.decode(errors="replace"),
                    incoming.sender,
                )
                self._mark_processed(imap, uid)
                return False

            if not self.cfg.sender_allowed(incoming.sender):
                logging.warning(
                    "Ignoring e-mail uid=%s: sender %s is not on the allowlist.",
                    uid.decode(errors="replace"),
                    incoming.sender,
                )
                self._mark_processed(imap, uid)
                return False

            # RFC 3834 (#14g): einem Automaten zu antworten heisst, mit ihm in
            # eine Schleife zu geraten — beide Seiten halten sich fuer hoeflich.
            if incoming.automated:
                logging.info(
                    "Ignoring e-mail uid=%s because it is an automated message.",
                    uid.decode(errors="replace"),
                )
                self._mark_processed(imap, uid)
                return False

            if not incoming.body.strip():
                logging.info("Ignoring e-mail uid=%s because it has no text body.", uid)
                self._mark_processed(imap, uid)
                return False

            logging.info(
                "Answering e-mail uid=%s from %s with persona %s.",
                uid.decode(errors="replace"),
                incoming.sender,
                persona,
            )
            answer = self.provider.answer(incoming.body, persona)
            if not answer.strip() or answer.lstrip().startswith("[ERROR]"):
                logging.warning(
                    "No valid LLM answer for uid=%s (likely a transient backend "
                    "error, e.g. Ollama down); leaving the e-mail untouched in the "
                    "mailbox to retry on the next poll.",
                    uid.decode(errors="replace"),
                )
                return False
            # **Erst markieren, dann senden** (#14f). Andersherum kostet ein
            # fehlgeschlagenes Markieren — gescheitertes COPY, Quota, falscher
            # Ordnertrenner — nicht eine Antwort, sondern *jede*: die Mail
            # bleibt UNSEEN und wird bei jedem Poll neu beantwortet. Gemessen
            # waren das 4 identische Antworten in 4 Zyklen, bei 60-s-Poll also
            # 1440 Mails am Tag an denselben Empfänger, jede mit einem
            # LLM-Lauf — und `run_once()` meldete jedes Mal 0, es sah also aus,
            # als sei nichts passiert.
            #
            # Der neue Fehlerfall ist der bessere: markiert, aber Senden
            # scheitert → **eine** Antwort geht verloren statt tausend zu viel.
            self._mark_processed(imap, uid)
            self._send_reply(incoming, answer)
            return True
        except Exception:
            logging.exception("Failed to process e-mail uid=%s.", uid)
            return False

    def _fetch_email(self, imap: ImapClient, uid: bytes) -> IncomingEmail | None:
        status, data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK" or not data:
            logging.warning("Could not fetch e-mail uid=%s: status=%s", uid, status)
            return None

        raw = None
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                break
        if raw is None:
            logging.warning("IMAP fetch for uid=%s did not contain message bytes.", uid)
            return None

        # typeshed gibt `message_from_bytes(..., policy=default)` als
        # `Message` an. Zur Laufzeit baut die Policy über ihre
        # `message_factory` aber eine `EmailMessage` — und nur die hat
        # `get_content()`, auf dem `_extract_text` weiter unten steht. Der
        # cast hält genau diese Zusage fest, an der Stelle, an der sie
        # entsteht: `policy=default` ist tragend, nicht Geschmackssache.
        msg = cast(EmailMessage, message_from_bytes(raw, policy=default))
        return IncomingEmail(
            uid=uid,
            # **`From`, nicht `Reply-To`** (#14d). Über `Reply-To` liess sich
            # die Instanz dazu bringen, an einen *Dritten* zu schreiben — vom
            # Mailserver des Betreibers, also mit gültigem SPF/DKIM seiner
            # Domain, und mit dem Text des Absenders wörtlich im Zitat.
            # Dieselbe Zeile speist die Schleifenerkennung weiter unten: mit
            # `Reply-To` konnte man auch die umgehen, indem man `From` auf eine
            # Systemadresse setzte. Der Preis ist bewusst: wer `Reply-To`
            # legitim benutzt, bekommt die Antwort trotzdem an `From`.
            sender=_addr(msg.get("From")),
            recipients=_recipients(msg),
            subject=_decode_header(msg.get("Subject", "")),
            body=_truncate_body(_extract_text(msg), self.cfg.max_body_chars),
            message_id=msg.get("Message-ID"),
            date=_decode_header(msg.get("Date", "")),
            automated=_is_automated(msg),
        )

    def _persona_for(self, recipients: list[str]) -> str | None:
        for recipient in recipients:
            persona = self.cfg.address_persona_map.get(recipient)
            if persona:
                return persona
        return None

    def _send_reply(self, incoming: IncomingEmail, answer: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = _reply_subject(incoming.subject)
        msg["From"] = self.cfg.smtp_from_address or self.cfg.smtp_username
        msg["To"] = incoming.sender
        msg["Message-ID"] = make_msgid()
        # RFC 3834 (#14g): sagt der Gegenstelle, dass hier ein Automat
        # geantwortet hat — ein gut erzogener Autoresponder antwortet darauf
        # nicht zurück.
        msg["Auto-Submitted"] = "auto-replied"
        if incoming.message_id:
            msg["In-Reply-To"] = incoming.message_id
            msg["References"] = incoming.message_id
        msg.set_content(_reply_body(answer, incoming, self.cfg))

        smtp = self._smtp_factory(self.cfg)
        try:
            if self.cfg.smtp_starttls:
                smtp.starttls()
            smtp.login(self.cfg.smtp_username, self.cfg.smtp_password)
            smtp.send_message(msg)
        finally:
            _safe_smtp_quit(smtp)

    def _mark_processed(self, imap: ImapClient, uid: bytes) -> None:
        """Markiert die Mail als erledigt — mit ``\\Seen`` als letzter Reserve.

        Der Verschiebe-Weg (COPY in den Bearbeitet-Ordner) kann aus Gründen
        scheitern, die nichts mit dieser Mail zu tun haben: falscher
        Ordnertrenner (``INBOX.`` statt ``INBOX/``, siehe #14a), Quota, fehlende
        Rechte. Vorher flog dann eine Ausnahme, und weil die Mail UNSEEN blieb,
        beantwortete der nächste Poll sie erneut — und der übernächste wieder.

        Deshalb fällt die Methode auf ``\\Seen`` zurück: das reicht, damit die
        ``UNSEEN``-Suche die Mail nicht ein zweites Mal findet. Erst wenn auch
        das scheitert, gibt sie auf — dann darf und soll der Aufrufer das
        Senden unterlassen.
        """
        if self.cfg.processed_mailbox:
            try:
                imap.create(self.cfg.processed_mailbox)
                copy_status, _ = imap.uid("copy", uid, self.cfg.processed_mailbox)
                if copy_status != "OK":
                    raise RuntimeError(f"IMAP COPY returned {copy_status!r}")
                imap.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted \\Seen)")
                imap.expunge()
                return
            except Exception as exc:
                logging.warning(
                    "Could not move e-mail uid=%s to %r (%s) — falling back to "
                    "\\Seen so it is not answered again.",
                    uid.decode(errors="replace"),
                    self.cfg.processed_mailbox,
                    exc,
                )

        flags = f"(\\Seen {self.cfg.processed_flag})"
        imap.uid("store", uid, "+FLAGS.SILENT", flags)


def start_email_adapter(
    cfg_mapping: dict | None, provider: AiApiProvider | None
) -> threading.Thread | None:
    cfg = EmailAdapterConfig.from_mapping(cfg_mapping)
    if not cfg.enabled:
        logging.info("E-mail adapter disabled.")
        return None
    if provider is None:
        logging.error("E-mail adapter enabled but no one-shot provider is available.")
        return None

    cfg.validate()
    service = EmailAdapterService(cfg, provider)
    thread = threading.Thread(
        target=service.run_forever, name="EmailAdapter", daemon=True
    )
    thread.start()
    return thread


def open_imap(cfg: EmailAdapterConfig) -> ImapClient:
    if cfg.imap_ssl:
        return imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
    return imaplib.IMAP4(cfg.imap_host, cfg.imap_port)


def open_smtp(cfg: EmailAdapterConfig) -> SmtpClient:
    if cfg.smtp_ssl:
        return smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port)
    return smtplib.SMTP(cfg.smtp_host, cfg.smtp_port)


def _safe_imap_logout(imap: ImapClient) -> None:
    try:
        imap.logout()
    except Exception:
        logging.debug("Ignoring IMAP logout error.", exc_info=True)


def _safe_smtp_quit(smtp: SmtpClient) -> None:
    try:
        smtp.quit()
    except Exception:
        logging.debug("Ignoring SMTP quit error.", exc_info=True)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _normalize_allowlist(value) -> tuple[str, ...]:
    """Liste aus Adressen und ``@domain``-Einträgen, normalisiert (#14e)."""
    if not isinstance(value, list | tuple | set):
        return ()
    entries = []
    for item in value:
        text = str(item or "").strip().lower()
        if not text:
            continue
        if text.startswith("@"):
            entries.append(text)
            continue
        parsed = _addr(text)
        if parsed:
            entries.append(parsed)
    return tuple(dict.fromkeys(entries))


def _truncate_body(text: str, limit: int) -> str:
    """Kürzt den Mailtext auf ``limit`` Zeichen (#14h).

    **Einmal beim Lesen**, nicht an jeder Verwendungsstelle: der Prompt und das
    Zitat in der Antwort erben die Kürzung dadurch automatisch. Sonst könnte
    ein Fremder beliebig viel Text durch die Instanz an einen Dritten
    weitertransportieren.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + _TRUNCATION_MARKER


def _is_automated(msg: Message) -> bool:
    """Kommt die Mail von einem Automaten? (RFC 3834, #14g)

    Ohne diese Prüfung antwortet der Adapter dem nächsten
    Abwesenheitsassistenten, der ihm antwortet, der ihm antwortet — und beide
    Seiten halten sich für höflich.
    """
    auto = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto and auto != "no":
        return True
    precedence = (msg.get("Precedence") or "").strip().lower()
    if precedence in {"bulk", "list", "junk"}:
        return True
    return bool(msg.get("List-Id") or msg.get("List-Unsubscribe"))


def _normalize_mapping(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for address, persona in value.items():
        parsed = _addr(str(address))
        if parsed and persona:
            result[parsed] = str(persona).strip()
    return result


def _addr(value: str | None) -> str:
    if not value:
        return ""
    return parseaddr(value)[1].strip().lower()


def _recipients(msg: Message) -> list[str]:
    headers = []
    for name in ("To", "Cc", "Delivered-To", "X-Original-To"):
        headers.extend(msg.get_all(name, []))
    addresses = [_addr(addr) for _display, addr in getaddresses(headers)]
    return [address for address in addresses if address]


def _decode_header(value: str) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _extract_text(msg: EmailMessage) -> str:
    if msg.is_multipart():
        plain_parts = []
        html_parts = []
        for part in msg.walk():
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(_part_content(part))
            elif content_type == "text/html":
                html_parts.append(_html_to_text(_part_content(part)))
        if plain_parts:
            return "\n\n".join(part for part in plain_parts if part).strip()
        return "\n\n".join(part for part in html_parts if part).strip()

    if msg.get_content_type() == "text/html":
        return _html_to_text(_part_content(msg)).strip()
    return _part_content(msg).strip()


def _part_content(part: EmailMessage) -> str:
    """Den Text eines Teils holen — `EmailMessage`, nicht `Message`.

    Die Annotation ist keine Kosmetik: `get_content()` gibt es **nur** auf
    `EmailMessage`, und die entsteht allein daraus, dass oben mit
    `policy=default` geparst wird. Nimmt jemand die Policy weg, liefert der
    Parser die Basisklasse, `get_content()` wirft `AttributeError` — und der
    Fallback unten fängt nur `LookupError`/`UnicodeDecodeError`, greift also
    gerade **nicht**. `policy=default` ist damit tragend, und diese Signatur
    ist die Stelle, an der das steht.
    """
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):
        # `get_payload(decode=True)` ist in typeshed breit typisiert
        # (Message | bytes | Any) — hier interessiert nur der Byte-Fall, alles
        # andere hat in diesem Zweig nichts zu suchen.
        payload = part.get_payload(decode=True)
        charset = part.get_content_charset() or "utf-8"
        raw = payload if isinstance(payload, bytes) else b""
        content = raw.decode(charset, errors="replace")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _reply_body(answer: str, incoming: IncomingEmail, cfg: EmailAdapterConfig) -> str:
    """Persona answer followed by the quoted original mail, like usual clients."""
    body = answer.strip() or " "
    quote = _quote_original(incoming, cfg)
    if quote:
        return f"{body}\n\n{quote}"
    return body


def _quote_original(incoming: IncomingEmail, cfg: EmailAdapterConfig) -> str:
    original = (incoming.body or "").strip()
    if not original:
        return ""
    quoted = "\n".join(f"> {line}" for line in original.splitlines())
    sender = incoming.sender or "?"
    if incoming.date:
        attribution = cfg.quote_attribution.format(date=incoming.date, sender=sender)
    else:
        attribution = cfg.quote_attribution_no_date.format(sender=sender)
    return f"{attribution}\n{quoted}"


def _reply_subject(subject: str) -> str:
    clean = (subject or "").strip()
    if not clean:
        return "Re: Anfrage an Yul Yen's AI Orchestra"
    if clean.lower().startswith("re:"):
        return clean
    return f"Re: {clean}"
