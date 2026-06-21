from __future__ import annotations

import html
import imaplib
import logging
import os
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
from typing import Protocol

from api.provider import AiApiProvider


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

    @classmethod
    def from_mapping(cls, data: dict | None) -> EmailAdapterConfig:
        data = data or {}
        imap_cfg = data.get("imap", {}) or {}
        smtp_cfg = data.get("smtp", {}) or {}
        processing_cfg = data.get("processing", {}) or {}

        return cls(
            enabled=_as_bool(data.get("enabled", False)),
            poll_interval_seconds=max(1, int(data.get("poll_interval_seconds", 60))),
            address_persona_map=_normalize_mapping(data.get("address_persona_map", {})),
            source_mailbox=str(processing_cfg.get("source_mailbox", "INBOX")),
            processed_mailbox=_optional_str(
                processing_cfg.get("processed_mailbox", "INBOX/YulYenProcessed")
            ),
            processed_flag=str(processing_cfg.get("processed_flag", "YulYenProcessed")),
            search_criteria=str(processing_cfg.get("search_criteria", "UNSEEN")),
            imap_host=str(imap_cfg.get("host", "")),
            imap_port=int(imap_cfg.get("port", 993)),
            imap_ssl=_as_bool(imap_cfg.get("ssl", True)),
            imap_username=_resolve_secret(imap_cfg.get("username", "")),
            imap_password=_resolve_secret(imap_cfg.get("password", "")),
            smtp_host=str(smtp_cfg.get("host", "")),
            smtp_port=int(smtp_cfg.get("port", 465)),
            smtp_ssl=_as_bool(smtp_cfg.get("ssl", True)),
            smtp_starttls=_as_bool(smtp_cfg.get("starttls", False)),
            smtp_username=_resolve_secret(smtp_cfg.get("username", "")),
            smtp_password=_resolve_secret(smtp_cfg.get("password", "")),
            smtp_from_address=_resolve_secret(smtp_cfg.get("from_address", "")),
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
        self._imap_factory = imap_factory or _open_imap
        self._smtp_factory = smtp_factory or _open_smtp
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
            self._send_reply(incoming, answer)
            self._mark_processed(imap, uid)
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

        msg = message_from_bytes(raw, policy=default)
        return IncomingEmail(
            uid=uid,
            sender=_addr(msg.get("Reply-To") or msg.get("From")),
            recipients=_recipients(msg),
            subject=_decode_header(msg.get("Subject", "")),
            body=_extract_text(msg),
            message_id=msg.get("Message-ID"),
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
        if incoming.message_id:
            msg["In-Reply-To"] = incoming.message_id
            msg["References"] = incoming.message_id
        msg.set_content(answer.strip() or " ")

        smtp = self._smtp_factory(self.cfg)
        try:
            if self.cfg.smtp_starttls:
                smtp.starttls()
            smtp.login(self.cfg.smtp_username, self.cfg.smtp_password)
            smtp.send_message(msg)
        finally:
            _safe_smtp_quit(smtp)

    def _mark_processed(self, imap: ImapClient, uid: bytes) -> None:
        if self.cfg.processed_mailbox:
            imap.create(self.cfg.processed_mailbox)
            copy_status, _ = imap.uid("copy", uid, self.cfg.processed_mailbox)
            if copy_status != "OK":
                raise RuntimeError(
                    f"Could not copy e-mail uid={uid!r} to {self.cfg.processed_mailbox!r}."
                )
            imap.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted \\Seen)")
            imap.expunge()
            return

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


def _open_imap(cfg: EmailAdapterConfig) -> ImapClient:
    if cfg.imap_ssl:
        return imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
    return imaplib.IMAP4(cfg.imap_host, cfg.imap_port)


def _open_smtp(cfg: EmailAdapterConfig) -> SmtpClient:
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


def _resolve_secret(value) -> str:
    if isinstance(value, dict) and "env" in value:
        return os.environ.get(str(value["env"]), "")
    if value is None:
        return ""
    text = str(value)
    if text.startswith("env:"):
        return os.environ.get(text[4:].strip(), "")
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text.strip())
    if match:
        return os.environ.get(match.group(1), "")
    return text


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


def _extract_text(msg: Message) -> str:
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


def _part_content(part: Message) -> str:
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        content = payload.decode(charset, errors="replace")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _reply_subject(subject: str) -> str:
    clean = (subject or "").strip()
    if not clean:
        return "Re: Anfrage an Yul Yen's AI Orchestra"
    if clean.lower().startswith("re:"):
        return clean
    return f"Re: {clean}"
