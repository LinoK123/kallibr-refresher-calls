"""Monday manager report: last week's activity, inputs and outputs, emailed to every active manager.

Run by its own Windows scheduled task on Mondays at 09:00 (refresher_push.py --manager-report), once per
week (a marker file records the week last reported). Design:
docs/superpowers/specs/2026-11-18-manager-report-design.md
"""
import html as htmllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from callback_digest import fmt_day, week_start

SYDNEY = ZoneInfo("Australia/Sydney")
LOST_OUTCOMES = {"not_needed", "went_elsewhere", "left_company", "do_not_call"}


def prior_week(today: date) -> tuple[date, date]:
    """The Monday to Sunday before the week containing `today`."""
    monday = week_start(today) - timedelta(days=7)
    return monday, monday + timedelta(days=6)


def _sydney_date(timestamp) -> date | None:
    if not timestamp:
        return None
    return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).astimezone(SYDNEY).date()


def _date(value) -> date | None:
    return date.fromisoformat(str(value)[:10]) if value else None


def _rate(won: int, lost: int):
    return won / (won + lost) if won + lost else None


@dataclass
class Report:
    week_start: date
    week_end: date
    team: dict
    people: list


def collect(client, today: date) -> Report:
    monday, sunday = prior_week(today)
    in_week = lambda d: d is not None and monday <= d <= sunday
    since = (datetime.combine(monday, datetime.min.time()) - timedelta(days=1)).isoformat()   # a day early, trimmed below

    staff = [s for s in client.select("staff", "id,email,full_name,role,active") if s.get("active")]

    # inputs: calls, refreshers worked (outcomes in those calls), cards taken
    calls = {c["id"]: c["staff_id"] for c in client.select("call_logs", "id,staff_id,called_at", called_at=f"gte.{since}")
             if in_week(_sydney_date(c["called_at"]))}
    calls_by = defaultdict(int)
    for who in calls.values():
        calls_by[who] += 1
    worked_by, lost_by = defaultdict(int), defaultdict(int)
    if calls:
        outcomes = []
        ids = sorted(calls)
        for i in range(0, len(ids), 200):
            part = ids[i:i + 200]
            outcomes += client.select("line_outcomes", "id,call_log_id,outcome",
                                      call_log_id=f"in.({','.join(str(x) for x in part)})")
        for o in outcomes:
            who = calls.get(o["call_log_id"])
            if who is None:
                continue
            worked_by[who] += 1
            if o["outcome"] in LOST_OUTCOMES:
                lost_by[who] += 1
    taken_by, taken_all = defaultdict(set), set()
    for e in client.select("card_events", "id,card_key,staff_id,event,at", at=f"gte.{since}"):
        if e["event"] in ("claimed", "assigned") and e.get("staff_id") and in_week(_sydney_date(e["at"])):
            taken_by[e["staff_id"]].add(e["card_key"])
            taken_all.add(e["card_key"])

    # outputs and the list now
    lines = client.select("lines", "id,contact_id,status,in_window,won_by,won_at,won_without_call,first_listed_on")
    card_of = {s["contact_id"]: s["card_key"] for s in client.select("students", "contact_id,card_key", order="contact_id")}
    won_by, won_all, won_credited, open_cards = defaultdict(int), 0, 0, set()
    open_lines = not_called = new_listed = 0
    for l in lines:
        if l["status"] == "won" and in_week(_date(l.get("won_at"))):
            won_all += 1
            if l.get("won_by"):
                won_credited += 1
                won_by[l["won_by"]] += 1
        is_open = l["status"] in ("not_called", "pending") and l.get("in_window", True) is not False
        if is_open:
            open_lines += 1
            not_called += l["status"] == "not_called"
            if l["contact_id"] in card_of:
                open_cards.add(card_of[l["contact_id"]])
        if in_week(_date(l.get("first_listed_on"))):
            new_listed += 1

    queue_cards = held_cards = 0
    overdue_by = defaultdict(int)
    for c in client.select("cards", "card_key,claimed_by,claimed_at,callback_on,do_not_call", order="card_key"):
        if c["card_key"] not in open_cards:
            continue
        if not c.get("claimed_by"):
            queue_cards += not c.get("do_not_call")
            continue
        held_cards += 1
        callback = _date(c.get("callback_on"))
        claimed = _sydney_date(c.get("claimed_at"))
        if callback and callback < today and (claimed is None or callback >= claimed):
            overdue_by[c["claimed_by"]] += 1

    lost_all = sum(lost_by.values())
    team = dict(calls=len(calls), worked=sum(worked_by.values()), cards_taken=len(taken_all),
                won=won_all, won_credited=won_credited, won_without_call=won_all - won_credited, lost=lost_all,
                win_rate=_rate(won_all, lost_all), open=open_lines, not_called=not_called, queue_cards=queue_cards,
                held_cards=held_cards, new_listed=new_listed, callbacks_overdue=sum(overdue_by.values()))
    people = sorted((dict(name=s["full_name"], cards_taken=len(taken_by[s["id"]]), calls=calls_by[s["id"]],
                          worked=worked_by[s["id"]], won=won_by[s["id"]], lost=lost_by[s["id"]],
                          win_rate=_rate(won_by[s["id"]], lost_by[s["id"]]), callbacks_overdue=overdue_by[s["id"]])
                     for s in staff), key=lambda p: p["name"].lower())
    return Report(monday, sunday, team, people)


def _pct(rate) -> str:
    return "–" if rate is None else f"{round(rate * 100)}%"


def render(r: Report) -> tuple[str, str, str]:
    """(subject, plain text, HTML). Every value is escaped in the HTML."""
    e = htmllib.escape
    t = r.team
    period = f"{fmt_day(r.week_start)} – {fmt_day(r.week_end)}"
    inputs = f"{t['calls']} calls logged · {t['worked']} refreshers worked · {t['cards_taken']} cards taken"
    outputs = (f"{t['won']} won ({t['won_credited']} credited to staff, {t['won_without_call']} booked without a call)"
               f" · {t['lost']} lost · win rate {_pct(t['win_rate'])}")
    now = (f"{t['open']:,} refreshers open ({t['not_called']:,} not yet called) · {t['queue_cards']:,} cards in the Queue,"
           f" {t['held_cards']:,} held · {t['new_listed']:,} new refreshers added last week"
           f" · {t['callbacks_overdue']:,} call-backs overdue")
    head = ["Team member", "Cards taken", "Calls", "Refreshers worked", "Won", "Lost", "Win rate", "Call-backs overdue (now)"]
    rows = [[p["name"], p["cards_taken"], p["calls"], p["worked"], p["won"], p["lost"], _pct(p["win_rate"]),
             p["callbacks_overdue"]] for p in r.people]

    text = [f"Refresher calls: team report for {period}", "", "TEAM", f"Inputs:  {inputs}", f"Outputs: {outputs}",
            f"The list now: {now}", "", "BY TEAM MEMBER", " | ".join(head)]
    text += [" | ".join(str(v) for v in row) for row in rows]
    text += ["", f"Open the call list: {config.SITE_URL}"]

    cell = "border:1px solid #c8c8d4;padding:6px 10px;font-family:Arial,sans-serif;font-size:13px"
    table = (f'<table style="border-collapse:collapse"><tr>'
             + "".join(f'<th style="{cell};background:#ece8f7;text-align:left">{e(h)}</th>' for h in head) + "</tr>"
             + "".join("<tr>" + "".join(f'<td style="{cell};text-align:{"left" if i == 0 else "right"}">{e(str(v))}</td>'
                                        for i, v in enumerate(row)) + "</tr>" for row in rows)
             + "</table>")
    html = (f'<div style="font-family:Arial,sans-serif;font-size:14px">'
            f"<h2 style=\"font-weight:normal\">Refresher calls: team report, {e(period)}</h2>"
            f"<p><b>Inputs:</b> {e(inputs)}<br><b>Outputs:</b> {e(outputs)}<br><b>The list now:</b> {e(now)}</p>"
            f"<h3 style=\"font-weight:normal\">By team member</h3>{table}"
            f'<p><a href="{e(config.SITE_URL)}">Open the call list</a></p></div>')
    return f"Refresher calls: team report, {period}", "\n".join(text) + "\n", html


def managers(client) -> list[str]:
    return sorted(s["email"] for s in client.select("staff", "id,email,full_name,role,active")
                  if s.get("active") and s.get("role") == "manager")


def run_report(client, today: date, marker_path, sender, force: bool = False, only: str | None = None) -> str:
    """Send last week's report to every active manager, once per week. Returns a one-line summary.
    `force` ignores the marker; `only` sends to that one address and leaves the marker alone (for testing)."""
    monday = prior_week(today)[0].isoformat()
    marker = Path(marker_path)
    if not force and not only and marker.exists() and marker.read_text(encoding="utf-8").strip() == monday:
        return "Manager report: already sent this week"
    subject, text, html = render(collect(client, today))
    recipients = [only.strip()] if only else managers(client)
    sent, errors = 0, []
    for to in recipients:
        try:
            sender(to, subject, text, html)
            sent += 1
        except Exception as e:                       # one bad address must not stop the others
            errors.append(f"{to}: {type(e).__name__}")
    if not only and (sent or not recipients):
        marker.write_text(monday + "\n", encoding="utf-8")
    summary = f"Manager report: {sent} sent, {len(errors)} failed"
    if errors:
        summary += " (" + "; ".join(errors)[:300] + ")"
    return summary
