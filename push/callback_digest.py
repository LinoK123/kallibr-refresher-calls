"""Monday call-back email: one email per team member listing their overdue and this week's call-backs.

Sent by the nightly push on the designated PC after a successful push, on the first run of each
Monday-to-Sunday week (a marker file records the week last sent). Design:
docs/superpowers/specs/2026-11-18-callbacks-design.md
"""
import html as htmllib
import smtplib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import config

SYDNEY = ZoneInfo("Australia/Sydney")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def week_start(today: date) -> date:
    """The Monday of the week containing `today`."""
    return today - timedelta(days=today.weekday())


def fmt_day(d: date) -> str:
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


@dataclass(frozen=True)
class Item:
    card_name: str
    org_name: str | None
    date: date


@dataclass
class Digest:
    email: str
    full_name: str
    overdue: list = field(default_factory=list)
    week: list = field(default_factory=list)


def _sydney_date(timestamp: str) -> date:
    return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).astimezone(SYDNEY).date()


def collect(client, today: date) -> list[Digest]:
    """Each active team member's held cards with a call-back that is overdue or due by Sunday.
    A call-back set before the holder took the card (a previous holder's) doesn't count, nor does
    a card with no open refreshers."""
    staff = {s["id"]: s for s in client.select("staff", "id,email,full_name,active") if s.get("active")}
    card_of = {s["contact_id"]: s["card_key"]
               for s in client.select("students", "contact_id,card_key", order="contact_id")}
    open_cards = set()
    for l in client.select("lines", "contact_id,status,in_window", status="in.(not_called,pending)"):
        if l.get("status") in ("not_called", "pending") and l.get("in_window", True) is not False:
            if l["contact_id"] in card_of:
                open_cards.add(card_of[l["contact_id"]])
    sunday = week_start(today) + timedelta(days=6)
    per: dict[str, Digest] = {}
    cards = client.select("cards", "card_key,target_name,org_name,claimed_by,claimed_at,callback_on",
                          order="card_key", claimed_by="not.is.null", callback_on="not.is.null")
    for c in cards:
        who, callback = c.get("claimed_by"), c.get("callback_on")
        if not who or who not in staff or not callback or c["card_key"] not in open_cards:
            continue
        when = date.fromisoformat(str(callback)[:10])
        if when > sunday or (c.get("claimed_at") and when < _sydney_date(c["claimed_at"])):
            continue
        d = per.setdefault(who, Digest(staff[who]["email"], staff[who]["full_name"]))
        (d.overdue if when < today else d.week).append(Item(c["target_name"], c.get("org_name"), when))
    for d in per.values():
        d.overdue.sort(key=lambda i: (i.date, i.card_name))
        d.week.sort(key=lambda i: (i.date, i.card_name))
    return sorted(per.values(), key=lambda d: d.email)


def render(d: Digest, today: date) -> tuple[str, str, str]:
    """(subject, plain text, HTML). Every value is escaped in the HTML."""
    monday = fmt_day(week_start(today))
    first = (d.full_name or "").split(" ")[0] or "there"
    label = lambda i: f"{i.card_name}" + (f" ({i.org_name})" if i.org_name else "")
    text = [f"Hi {first},", "", f"Your call-backs for the week starting {monday}:"]
    html = [f"<p>Hi {htmllib.escape(first)},</p>", f"<p>Your call-backs for the week starting {htmllib.escape(monday)}:</p>"]
    for title, items in (("Overdue", d.overdue), ("This week", d.week)):
        if not items:
            continue
        text += ["", title] + [f"- {fmt_day(i.date)}: {label(i)}" for i in items]
        html.append(f"<p><b>{htmllib.escape(title)}</b></p><ul>"
                    + "".join(f"<li>{htmllib.escape(fmt_day(i.date))}: {htmllib.escape(label(i))}</li>" for i in items)
                    + "</ul>")
    text += ["", f"Open the call list: {config.SITE_URL}"]
    html.append(f'<p><a href="{htmllib.escape(config.SITE_URL)}">Open the call list</a></p>')
    return f"Your call-backs this week (from {monday})", "\n".join(text) + "\n", "\n".join(html)


def smtp_sender(user: str, password: str, smtp=smtplib.SMTP):
    """A function that sends one email through Gmail SMTP (STARTTLS) as `user`."""
    def send(to: str, subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = f"{config.EMAIL_FROM_NAME} <{user}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        with smtp(config.SMTP_HOST, config.SMTP_PORT, timeout=60) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    return send


def run_digest(client, today: date, marker_path, sender, force: bool = False, only: str | None = None) -> str:
    """Send this week's call-back emails once. Returns a one-line summary; never raises for a send failure.
    `force` ignores the marker; `only` limits to one address and leaves the marker alone (for testing)."""
    monday = week_start(today).isoformat()
    marker = Path(marker_path)
    if not force and not only and marker.exists() and marker.read_text(encoding="utf-8").strip() == monday:
        return "Call-back emails: already sent this week"
    digests = collect(client, today)
    if only:
        digests = [d for d in digests if d.email.lower() == only.strip().lower()]
    sent, errors = 0, []
    for d in digests:
        subject, text, html = render(d, today)
        try:
            sender(d.email, subject, text, html)
            sent += 1
        except Exception as e:                      # one bad address must not stop the others
            errors.append(f"{d.email}: {type(e).__name__}")
    if not only and (sent or not digests):          # all failed: try again on the next run
        marker.write_text(monday + "\n", encoding="utf-8")
    summary = f"Call-back emails: {sent} sent, {len(errors)} failed"
    if not digests:
        summary += " (nobody has call-backs due this week)"
    if errors:
        summary += " (" + "; ".join(errors)[:300] + ")"
    return summary
