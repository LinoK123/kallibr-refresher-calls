"""Database tests run against the TEST Supabase project only.

Connection string: env REFRESHER_TEST_DB_URL, else Windows Credential Manager
(kallibr-refresher-test / db_url, stored by set_test_db_url.py).
Each test runs in one transaction that is rolled back afterwards.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest

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
