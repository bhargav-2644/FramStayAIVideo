"""Write and send the outreach emails, and read replies so the sequence stops."""

from __future__ import annotations

import email
import imaplib
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path

MAX_ATTACHMENT_BYTES = 9 * 1024 * 1024
STOP_WORDS = ("stop", "unsubscribe", "remove me", "not interested", "don't contact", "do not contact")


def _footer(sender: dict) -> str:
    return (
        f"{sender['name']}, {sender['business']}, {sender['city']}, {sender['phone']}\n\n"
        "This is a short, one-time note. Reply \"stop\" and I will delete the preview "
        "and not contact you again."
    )


def _whatsapp(outreach: dict, name: str) -> str:
    number = str(outreach.get("whatsapp_number") or "").strip()
    if not number:
        return ""
    text = f"Hi, I saw the preview of {name}".replace(" ", "%20")
    return f"\nOr message me on WhatsApp: https://wa.me/{number}?text={text}\n"


def compose(lead: dict, touch: int, outreach: dict) -> tuple[str, str]:
    """Subject and body for touch 0 (first email) or a follow-up."""
    name = lead["name"]
    sender = outreach["sender"]
    if touch == 0:
        subject = f"A short cinematic preview of {name}"
        body = (
            "Hi,\n\n"
            f"I make short cinematic drone-style videos for farm stays and villas. "
            f"I put together a quick AI preview of {name} from the photos on your "
            "Google listing; it is attached.\n\n"
            "It is a concept made from still photos, not real drone footage. If you like it, "
            "I can make a full version from your own photos: about 60 seconds, wide and "
            "vertical cuts for Instagram and your booking page, from "
            f"Rs {outreach.get('price_from', '10,000')}.\n\n"
            "Just reply to this email if you would like to see more."
            f"{_whatsapp(outreach, name)}\n"
        )
    elif touch == 1:
        subject = f"Re: A short cinematic preview of {name}"
        body = (
            "Hi,\n\n"
            f"Following up on the preview of {name} I sent a few days ago, in case it got "
            "buried. Happy to make a version for Instagram Reels too.\n"
            f"{_whatsapp(outreach, name)}\n"
        )
    else:
        subject = f"Re: A short cinematic preview of {name}"
        body = (
            "Hi,\n\n"
            "Last note from me. If a cinematic video isn't a priority right now, no problem: "
            f"I'll delete the preview of {name}. If you'd like it later, just reply.\n\n"
        )
    return subject, body + "\n" + _footer(sender)


def build_message(lead: dict, touch: int, outreach: dict, video: Path | None) -> EmailMessage:
    sender = outreach["sender"]
    subject, body = compose(lead, touch, outreach)
    msg = EmailMessage()
    msg["From"] = formataddr((sender["name"], sender["email"]))
    msg["To"] = lead["email"]
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=sender["email"].split("@")[1])
    msg["List-Unsubscribe"] = f"<mailto:{sender['email']}?subject=stop>"
    msg.set_content(body)
    if touch == 0 and video and video.exists():
        data = video.read_bytes()
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"{video.name} is {len(data) // 1_000_000} MB, too big to attach")
        msg.add_attachment(data, maintype="video", subtype="mp4",
                           filename=f"{lead['name']} - preview.mp4")
    return msg


class Mailer:
    """Sends through SMTP, or writes .eml files to an outbox folder on a dry run."""

    def __init__(self, smtp: dict, password: str | None, outbox: Path, dry_run: bool):
        self.smtp = smtp
        self.password = password
        self.outbox = outbox
        self.dry_run = dry_run

    def send(self, msg: EmailMessage, name: str) -> str:
        if self.dry_run:
            self.outbox.mkdir(parents=True, exist_ok=True)
            safe = "".join(c if c.isalnum() else "-" for c in name)[:60]
            path = self.outbox / f"{safe}-{abs(hash(msg['Message-ID'])) % 10_000:04d}.eml"
            path.write_bytes(bytes(msg))
            return f"dry run: wrote {path}"
        with smtplib.SMTP(self.smtp["host"], int(self.smtp.get("port", 587)), timeout=60) as s:
            s.starttls()
            s.login(self.smtp["username"], self.password or "")
            s.send_message(msg)
        return f"sent to {msg['To']}"


def is_stop(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in STOP_WORDS)


def _body_text(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


def fetch_replies(imap: dict, password: str, since: str) -> list[tuple[str, str, str]]:
    """(from address, subject, body) of inbox messages since a date like 01-Oct-2026."""
    out = []
    with imaplib.IMAP4_SSL(imap["host"], int(imap.get("port", 993))) as box:
        box.login(imap["username"], password)
        box.select("INBOX", readonly=True)
        _, ids = box.search(None, "SINCE", since)
        for i in ids[0].split():
            _, data = box.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            sender = parseaddr(msg.get("From", ""))[1].lower()
            out.append((sender, msg.get("Subject", ""), _body_text(msg)))
    return out
