"""Pure refresher rules (spec sections 5.2, 5.3, 5.5). Reads the local SQLite database only."""
import calendar
import sqlite3
from collections import Counter, defaultdict
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


@dataclass(frozen=True)
class Placement:
    contact_id: int
    card_key: str
    kind: str                       # booker | organisation | individual
    target_contact_id: int | None
    target_name: str
    org_name: str | None            # the card's organisation (same for every student on the card)
    org_key: str | None


def _org(org_name):
    """(display name, key) for a real organisation, or (None, None) for blank / cash individuals."""
    name = (org_name or "").strip()
    if not name or name.lower().startswith(config.INDIVIDUAL_ORG_PREFIX.lower()):
        return None, None
    return name, name.lower()


def _norm(name):
    return " ".join((name or "").split()).lower()


def _staff_names(con) -> set[str]:
    rows = con.execute("select bookedstatusenteredbyfullname, count(*) from bookings "
                       "where bookedstatusenteredbyfullname is not null group by 1")
    return {_norm(n) for n, k in rows if k >= config.STAFF_ENTERED_MIN and _norm(n)}


def _requesters(con) -> dict[int, tuple[int, str]]:
    """booking ID -> (requester contact ID, requester name), where a requester is recorded."""
    out = {}
    for sid, who, name in con.execute("select statusid, whobyid, workshopbookingrequestedbyfullname from bookings"):
        if sid is not None and who is not None and sid not in out:
            out[sid] = (int(who), (name or "").strip())
    return out


def _current_bookers(con, today: date, staff: set[str], ignore: set[int]):
    """Who books for each company now: requesters of real bookings (any course) made in the last
    CURRENT_BOOKER_MONTHS, judged on the booked date (or the class date when there is none).
    Returns (counts by (org_key, state), counts by org_key, active (org_key, who) pairs,
    latest booking date by (scope, who), latest name by who)."""
    since = add_months(today, -config.CURRENT_BOOKER_MONTHS)
    requesters = _requesters(con)
    by_state, by_org = defaultdict(Counter), defaultdict(Counter)
    latest, names, name_at, active, seen = {}, {}, {}, set(), set()
    rows = con.execute("select booking_id, contact_id, organisation, location, start_date, booked_on, counted from v_bookings")
    for bid, cid, org, loc, start, booked_on, counted in rows:
        if counted != 1 or bid in seen:
            continue
        seen.add(bid)
        when = _d(booked_on) or _d(start)
        _, org_key = _org(org)
        req = requesters.get(bid)
        if when is None or when < since or not org_key or req is None:
            continue
        who, name = req
        if who == cid or who in ignore or (_norm(name) and _norm(name) in staff):
            continue
        active.add((org_key, who))
        by_state[(org_key, loc)][who] += 1
        by_org[org_key][who] += 1
        for scope in ((org_key, loc), (org_key, None)):
            if (scope, who) not in latest or when > latest[(scope, who)]:
                latest[(scope, who)] = when
        if who not in name_at or when >= name_at[who]:
            name_at[who], names[who] = when, name
    return by_state, by_org, active, latest, names


def place_students(con: sqlite3.Connection, lines: list[Line],
                   ignore_ids: tuple[int, ...] = (), today: date | None = None) -> dict[int, Placement]:
    """Choose one card per student (spec 5.3). Keyed by student contact ID.

    With `today`, a student whose booker has gone quiet for their company (or who has no booker)
    goes to the company's current booker for their state (current-booker design, 18 Nov 2026)."""
    latest: dict[int, Line] = {}
    for l in lines:
        cur = latest.get(l.contact_id)
        if cur is None or (l.last_done, l.refresher_type) > (cur.last_done, cur.refresher_type):
            latest[l.contact_id] = l

    types = type_map(con)
    real = defaultdict(list)          # (contact, course_type_id, start_date) -> booking IDs
    for b in _bookings(con, types):
        if b.counted:
            real[(b.contact_id, b.course_type_id, b.start_date)].append(b.booking_id)
    requesters = _requesters(con)
    staff = _staff_names(con)
    ignore = set(ignore_ids)

    def booker_for(l: Line):
        for bid in sorted(real.get((l.contact_id, l.course_type_id, l.last_done), []), reverse=True):
            req = requesters.get(bid)
            if req is None:
                continue
            who, name = req
            if who in ignore or (_norm(name) and _norm(name) in staff):
                continue
            return who, name
        return None

    placed: dict[int, Placement] = {}
    for cid, l in latest.items():
        org_name, org_key = _org(l.org_name)
        req = booker_for(l)
        if req and req[0] != cid:
            who, name = req
            placed[cid] = Placement(cid, f"B:{who}", "booker", who, name, org_name, org_key)
        elif req is None and org_key:
            placed[cid] = Placement(cid, f"O:{org_key}", "organisation", None, org_name, org_name, org_key)
        else:
            placed[cid] = Placement(cid, f"S:{cid}", "individual", cid, l.student_name, org_name, org_key)

    # Current booking contact: replace a quiet booker (or an organisation card) with whoever books
    # for the company now in the student's state, else the company's busiest current booker.
    if today is not None:
        by_state, by_org, active, latest_when, names = _current_bookers(con, today, staff, ignore)

        def pick(counter, scope):
            if not counter:
                return None
            return min(counter, key=lambda w: (-counter[w], -latest_when[(scope, w)].toordinal(), w))

        for cid, p in list(placed.items()):
            if p.kind == "individual" or not p.org_key:
                continue
            if p.kind == "booker" and (p.org_key, p.target_contact_id) in active:
                continue
            state = latest[cid].location
            who = pick(by_state.get((p.org_key, state)), (p.org_key, state))
            if who is None:
                who = pick(by_org.get(p.org_key), (p.org_key, None))
            if who is not None:
                placed[cid] = Placement(cid, f"B:{who}", "booker", who, names.get(who) or f"Contact {who}",
                                        p.org_name, p.org_key)

    # One person, one card: a student who also books for others goes on their own booker card.
    bookers = {p.target_contact_id for p in placed.values() if p.kind == "booker"}
    for cid in bookers & placed.keys():
        p = placed[cid]
        if p.card_key != f"B:{cid}":
            placed[cid] = Placement(cid, f"B:{cid}", "booker", cid, p.target_name, p.org_name, p.org_key)

    # Card-level fields must agree for every student on a card: take them from the student
    # with the most recent course (then lowest contact ID), using the booker's own name where known.
    by_card = defaultdict(list)
    for p in placed.values():
        by_card[p.card_key].append(p)
    for key, ps in by_card.items():
        ps.sort(key=lambda p: (-latest[p.contact_id].last_done.toordinal(), p.contact_id))
        lead = next((p for p in ps if p.kind == "booker" and p.contact_id != p.target_contact_id), ps[0])
        for p in ps:
            placed[p.contact_id] = Placement(p.contact_id, key, lead.kind, lead.target_contact_id,
                                             lead.target_name, lead.org_name, lead.org_key)
    return placed


@dataclass(frozen=True)
class LineCheck:
    contact_id: int
    refresher_type: str
    last_done: date
    in_window: bool
    won: bool
    booked_on: date | None
    class_date: date | None
    course_name: str | None
    tentative: bool


def check_lines(con: sqlite3.Connection, keys: list[tuple[int, str, date]], today: date) -> list[LineCheck]:
    """Win, tentative and window state for each line key (spec 5.5), in the order given."""
    types = type_map(con)
    by_type = _by_contact_type(_bookings(con, types), types)
    earliest = add_months(today, -12 * config.LOOKBACK_YEARS)
    out = []
    for cid, t, last in keys:
        theirs = by_type.get((cid, t), [])
        real = sorted((b for b in theirs if b.counted and b.start_date > last),
                      key=lambda b: (b.start_date, b.booking_id))
        tentative = any(b.status in config.TENTATIVE_STATUSES and b.start_date >= today and b.start_date > last
                        for b in theirs)
        first = real[0] if real else None
        out.append(LineCheck(cid, t, last, last >= earliest, first is not None,
                             first.booked_on if first else None, first.start_date if first else None,
                             first.course if first else None, tentative))
    return out


def course_history(con: sqlite3.Connection, contact_ids: set[int]) -> list[tuple[int, str, date]]:
    """Every Kallibr course each student completed: (contact_id, course_name, completed_on), distinct."""
    rows = set()
    for cid, course, on in con.execute("select contact_id, course_name, completed_on from v_completions"):
        if cid is not None and int(cid) in contact_ids and course and on:
            rows.add((int(cid), course, _d(on)))
    return sorted(rows)
