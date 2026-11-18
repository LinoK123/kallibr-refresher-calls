"""A small SQLite database shaped like the parts of axc_agent.db the rules read."""
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")

SCHEMA = """
create table course_refresher_groups(course_type_id integer, refresher_group text);
create table v_completions(contact_id integer, student text, organisation text, course_type_id integer,
                           course_name text, completed_on text, location text);
create table v_bookings(booking_id integer, contact_id integer, student text, organisation text, class_id integer,
                        course_type_id integer, course text, location text, start_date text, booking_status text,
                        booked_on text, counted integer);
create table bookings(statusid integer, contactid integer, pdataid integer, whobyid integer,
                      workshopbookingrequestedbyfullname text, bookedstatusenteredbyfullname text);
create table sync_log(synced_at text, table_name text, row_count integer);
"""
GROUPS = [(100889, "Heights"), (100890, "Confined Space"), (116646, "Confined Space"), (116646, "Heights")]


def make_db(path):
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA)
    con.executemany("insert into course_refresher_groups values (?, ?)", GROUPS)
    con.commit()
    return con


def comp(con, contact, ct, on, org="Acme Pty Ltd", name=None, loc="QLD", course="Course"):
    con.execute("insert into v_completions values (?, ?, ?, ?, ?, ?, ?)",
                (contact, name or f"Student {contact}", org, ct, course, on, loc))
    con.commit()


def _next_id(con):
    return con.execute("select coalesce(max(statusid), 0) + 1 from bookings").fetchone()[0]


def book(con, contact, ct, start, status="Booked", counted=1, booker=None, booker_name=None,
         entered_by="Admin Person", booked_on=None, org="Acme Pty Ltd", name=None, loc="QLD", course="Course"):
    bid = _next_id(con)
    class_id = 10_000 + bid
    con.execute("insert into v_bookings values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (bid, contact, name or f"Student {contact}", org, class_id, ct, course, loc, start, status,
                 booked_on, counted))
    con.execute("insert into bookings values (?, ?, ?, ?, ?, ?)",
                (bid, contact, class_id, booker, booker_name, entered_by))
    con.commit()
    return bid


def staff_entries(con, name, n=50):
    """n bookings entered by `name`, in the bookings table only, so they create no lines."""
    start = _next_id(con)
    con.executemany("insert into bookings values (?, ?, ?, ?, ?, ?)",
                    [(start + i, 0, 0, None, None, name) for i in range(n)])
    con.commit()


def set_synced(con, when: datetime):
    """Record a sync at `when`, stored as naive Sydney local time like axc_sync.py does."""
    if when.tzinfo is not None:
        when = when.astimezone(SYDNEY).replace(tzinfo=None)
    con.execute("insert into sync_log values (?, 'bookings', 1)", (when.isoformat(timespec="seconds"),))
    con.commit()
