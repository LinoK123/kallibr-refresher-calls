"""Pure refresher rules (spec sections 5.2, 5.3, 5.5). Reads the local SQLite database only."""
import calendar
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import config


def add_months(d: date, months: int) -> date:
    """d plus a number of months, clamped to the end of the target month."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def type_map(con: sqlite3.Connection) -> dict[int, set[str]]:
    """course_type_id -> refresher types. Joined by ID only, never by course name."""
    out: dict[int, set[str]] = defaultdict(set)
    for ct, group in con.execute("select course_type_id, refresher_group from course_refresher_groups"):
        if ct is not None and group in config.INTERVAL_MONTHS:
            out[int(ct)].add(group)
    for ct in config.HSR_COURSE_TYPE_IDS:
        out[ct].add("HSR")
    return dict(out)


def _d(text):
    return date.fromisoformat(str(text)[:10]) if text else None


@dataclass(frozen=True)
class Line:
    contact_id: int
    refresher_type: str
    last_done: date
    due_date: date
    course_type_id: int
    course_name: str
    location: str | None
    attendance_confirmed: bool
    student_name: str
    org_name: str | None


@dataclass(frozen=True)
class _Booking:
    booking_id: int
    contact_id: int
    student: str
    organisation: str | None
    course_type_id: int
    course: str
    location: str | None
    start_date: date
    status: str
    booked_on: date | None
    counted: bool


def _bookings(con, types) -> list[_Booking]:
    """Bookings on refresher courses, one per booking ID."""
    seen, out = set(), []
    rows = con.execute("select booking_id, contact_id, student, organisation, course_type_id, course, location, "
                       "start_date, booking_status, booked_on, counted from v_bookings")
    for bid, cid, student, org, ct, course, loc, start, status, booked_on, counted in rows:
        if cid is None or ct is None or int(ct) not in types or not start or bid in seen:
            continue
        seen.add(bid)
        out.append(_Booking(bid, int(cid), student, org, int(ct), course, loc, _d(start), status,
                            _d(booked_on), counted == 1))
    return out


def _by_contact_type(bookings, types):
    by = defaultdict(list)
    for b in bookings:
        for t in types[b.course_type_id]:
            by[(b.contact_id, t)].append(b)
    return by


def build_lines(con: sqlite3.Connection, today: date) -> list[Line]:
    """Every student due a refresher (spec 5.2), one Line per student and type."""
    types = type_map(con)
    hsr = set(config.HSR_COURSE_TYPE_IDS)
    # (contact, type) -> [(date, is_completion, course_type_id, course_name, location, student, org)]
    events = defaultdict(list)
    rows = con.execute("select contact_id, student, organisation, course_type_id, course_name, completed_on, "
                       "location from v_completions")
    for cid, student, org, ct, course, on, loc in rows:
        if cid is None or ct is None or int(ct) not in types or not on:
            continue
        for t in types[int(ct)]:
            events[(int(cid), t)].append((_d(on), True, int(ct), course, loc, student, org))
    bookings = _bookings(con, types)
    for b in bookings:
        if b.counted and b.course_type_id in hsr and b.start_date < today:
            events[(b.contact_id, "HSR")].append((b.start_date, False, b.course_type_id, b.course, b.location,
                                                  b.student, b.organisation))
    by_type = _by_contact_type(bookings, types)

    earliest = add_months(today, -12 * config.LOOKBACK_YEARS)
    horizon = add_months(today, config.LOOKAHEAD_MONTHS)
    lines = []
    for (cid, t), evs in events.items():
        last = max(e[0] for e in evs)
        # a completion on the last-done date wins over a booking-only event on the same date
        ev = sorted((e for e in evs if e[0] == last), key=lambda e: (not e[1], e[2], e[3] or ""))[0]
        due = add_months(last, config.INTERVAL_MONTHS[t])
        if last < earliest or due > horizon:
            continue
        theirs = by_type.get((cid, t), [])
        if any(b.start_date >= today and b.status in config.FUTURE_BOOKING_STATUSES for b in theirs):
            continue
        if any(b.counted and b.start_date > last for b in theirs):
            continue
        lines.append(Line(cid, t, last, due, ev[2], ev[3], ev[4], ev[1], ev[5], ev[6]))
    lines.sort(key=lambda l: (l.contact_id, l.refresher_type))
    return lines
