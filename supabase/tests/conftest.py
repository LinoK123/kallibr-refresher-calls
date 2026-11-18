"""Database tests run against the TEST Supabase project only.

Connection string: env REFRESHER_TEST_DB_URL, else Windows Credential Manager
(kallibr-refresher-test / db_url, stored by set_test_db_url.py).
Each test runs in one transaction that is rolled back afterwards.
"""
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import namedtuple_row

ROOT = Path(__file__).resolve().parent.parent          # supabase/
INTERVAL = {"Confined Space": 24, "Heights": 24, "HSR": 12}
KIND = {"B": "booker", "O": "organisation", "S": "individual"}


def _db_url():
    url = os.environ.get("REFRESHER_TEST_DB_URL")
    if not url:
        try:
            import keyring
            url = keyring.get_password("kallibr-refresher-test", "db_url")
        except Exception:
            url = None
    if not url:
        pytest.skip("No test database: run  py supabase/tests/set_test_db_url.py")
    return url


@pytest.fixture(scope="session")
def db_url():
    url = _db_url()
    with psycopg.connect(url, autocommit=True) as c:
        c.execute((ROOT / "reset.sql").read_text(encoding="utf-8"))
        for f in sorted((ROOT / "migrations").glob("*.sql")):
            c.execute(f.read_text(encoding="utf-8"))
    return url


@pytest.fixture(scope="session")
def conn(db_url):
    c = psycopg.connect(db_url)
    yield c
    c.close()


@pytest.fixture
def cur(conn):
    with conn.cursor() as c:
        yield c
    conn.rollback()


# ---------- roles ----------

def _claims(cur, claims):
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))


def as_user(cur, email):
    cur.execute("reset role")
    _claims(cur, {"sub": "00000000-0000-0000-0000-000000000001", "email": email, "role": "authenticated"})
    cur.execute("set local role authenticated")


def as_anon(cur):
    cur.execute("reset role")
    _claims(cur, {"role": "anon"})
    cur.execute("set local role anon")


def as_service(cur):
    cur.execute("reset role")
    _claims(cur, {"role": "service_role"})
    cur.execute("set local role service_role")


@contextmanager
def as_owner(cur):
    """Run setup as the table owner, then return to whatever role the test was using."""
    cur.execute("select current_user")
    prev = cur.fetchone()[0]
    cur.execute("reset role")
    try:
        yield
    finally:
        if prev in ("authenticated", "anon", "service_role"):
            cur.execute(f"set local role {prev}")


# ---------- seed helpers ----------

def add_staff(cur, email, role="staff", active=True, full_name=None):
    with as_owner(cur):
        cur.execute("insert into staff (email, full_name, role, active) values (lower(%s), %s, %s, %s) returning id",
                    (email, full_name or email.split("@")[0].title(), role, active))
        return cur.fetchone()[0]


def seed_card(cur, card_key="B:900", students=((1, "Sam Lee"),), lines=((1, "Heights", "2024-06-10"),),
              target_name="Pat Booker", org_name="Acme Pty Ltd"):
    """One card with its students and lines. Returns line IDs keyed by (contact_id, type)."""
    kind = KIND[card_key[0]]
    target = int(card_key[2:]) if kind != "organisation" else None
    ids = {}
    with as_owner(cur):
        cur.execute("insert into cards (card_key, kind, target_contact_id, target_name, org_name, org_key) "
                    "values (%s, %s, %s, %s, %s, lower(%s)) on conflict do nothing",
                    (card_key, kind, target, target_name, org_name, org_name))
        for cid, name in students:
            cur.execute("insert into students (contact_id, full_name, org_name, card_key) values (%s, %s, %s, %s)",
                        (cid, name, org_name, card_key))
        for cid, rtype, last_done in lines:
            cur.execute("insert into lines (contact_id, refresher_type, last_done, due_date, first_listed_on) "
                        "values (%s, %s, %s::date, (%s::date + make_interval(months => %s))::date, current_date) "
                        "returning id", (cid, rtype, last_done, last_done, INTERVAL[rtype]))
            ids[(cid, rtype)] = cur.fetchone()[0]
    return ids


# ---------- staff action helpers (Task 5) ----------

def raises(cur, sql, params=(), match=None):
    """Assert `sql` fails, then carry on in the same transaction."""
    cur.execute("savepoint raises_sp")
    with pytest.raises(psycopg.Error, match=match):
        cur.execute(sql, params)
    cur.execute("rollback to savepoint raises_sp")


def claim(cur, email, card_key="B:900"):
    as_user(cur, email)
    cur.execute("select claim_card(%s)", (card_key,))
    assert cur.fetchone()[0] is True


def save(cur, email, outcomes, notes=None, callback_on=None, dnc_card=False, card_key="B:900"):
    as_user(cur, email)
    payload = json.dumps([{"line_id": lid, "outcome": o} for lid, o in outcomes])
    cur.execute("select save_call_log(%s, %s, %s, %s::jsonb, %s)", (card_key, notes, callback_on, payload, dnc_card))
    return cur.fetchone()[0]


def line(cur, line_id):
    """(status, outcome, last_outcome_by, won_by, won_without_call) read as the owner."""
    with as_owner(cur):
        cur.execute("select status, outcome, last_outcome_by, won_by, won_without_call from lines where id = %s",
                    (line_id,))
        return cur.fetchone()


def card(cur, card_key):
    with as_owner(cur):
        cur.execute("select do_not_call, claimed_by, callback_on from cards where card_key = %s", (card_key,))
        dnc, by, cb = cur.fetchone()
    return dict(do_not_call=dnc, claimed_by=by, callback_on=cb)


def call_log(cur, call_log_id):
    with as_owner(cur):
        with cur.connection.cursor(row_factory=namedtuple_row) as c:
            c.execute("select * from call_logs where id = %s", (call_log_id,))
            return c.fetchone()


def run_concurrently(db_url, calls, card_key="B:901"):
    """Run two statements as two staff on two connections, the second while the first's
    transaction is still open. Uses committed rows (its own card and staff), removed afterwards."""
    (e1, sql1), (e2, sql2) = calls
    setup = psycopg.connect(db_url, autocommit=True)
    emails = list(dict.fromkeys([e1.lower(), e2.lower()]))
    try:
        for e in emails:
            setup.execute("insert into staff (email, full_name, role) values (%s, %s, 'staff')", (e, e))
        setup.execute("insert into cards (card_key, kind, target_contact_id, target_name) "
                      "values (%s, 'booker', 901, 'Concurrent Booker')", (card_key,))
        c1, c2 = psycopg.connect(db_url), psycopg.connect(db_url)
        try:
            def prep(c, email):
                c.execute("select set_config('request.jwt.claims', %s, true)",
                          (json.dumps({"email": email, "role": "authenticated"}),))
                c.execute("set local role authenticated")

            prep(c1, e1)
            r1 = c1.execute(sql1).fetchone()[0]          # holds the row lock; not committed yet
            out = {}

            def second():
                try:
                    prep(c2, e2)
                    out["r2"] = c2.execute(sql2).fetchone()[0]
                    c2.commit()
                except Exception as exc:                  # surfaced below
                    out["err"] = exc

            t = threading.Thread(target=second)
            t.start()
            t.join(timeout=3)
            assert t.is_alive(), "second claim should wait for the first transaction"
            c1.commit()
            t.join(timeout=30)
            if "err" in out:
                raise out["err"]
            return [r1, out["r2"]]
        finally:
            c1.close(); c2.close()
    finally:
        setup.execute("delete from card_events where card_key = %s", (card_key,))
        setup.execute("delete from cards where card_key = %s", (card_key,))
        setup.execute("delete from staff where email = any(%s)", (emails,))
        setup.close()
