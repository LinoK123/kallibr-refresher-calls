import psycopg
import pytest

from conftest import add_staff, as_anon, as_user, seed_card

READABLE = ["staff", "cards", "students", "lines", "course_history", "call_logs", "line_outcomes", "card_events", "sync_runs"]


@pytest.mark.parametrize("table", READABLE)
def test_signed_out_reads_nothing(cur, table):
    seed_card(cur); as_anon(cur)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(f"select * from {table}")


@pytest.mark.parametrize("table", ["students", "lines", "cards", "call_logs"])
def test_signed_in_non_staff_sees_no_rows(cur, table):
    seed_card(cur); as_user(cur, "stranger@kallibr.com.au")
    cur.execute(f"select count(*) from {table}"); assert cur.fetchone()[0] == 0


def test_inactive_staff_sees_no_rows(cur):
    seed_card(cur); add_staff(cur, "gone@kallibr.com.au", active=False); as_user(cur, "gone@kallibr.com.au")
    cur.execute("select count(*) from students"); assert cur.fetchone()[0] == 0


def test_active_staff_reads_with_any_email_case(cur):
    seed_card(cur); add_staff(cur, "jo@kallibr.com.au"); as_user(cur, "Jo@Kallibr.com.au")
    cur.execute("select count(*) from students"); assert cur.fetchone()[0] == 1


@pytest.mark.parametrize("sql", [
    "update lines set status = 'won'",
    "insert into call_logs (card_key, staff_id) select 'B:900', id from staff limit 1",
    "delete from call_logs",
    "update cards set claimed_by = null",
    "select * from stage_students",
])
def test_staff_cannot_write_tables_directly(cur, sql):
    seed_card(cur); add_staff(cur, "jo@kallibr.com.au"); as_user(cur, "jo@kallibr.com.au")
    cur.execute("savepoint s")
    try:
        cur.execute(sql); changed = cur.rowcount
    except psycopg.errors.InsufficientPrivilege:
        changed = 0
    assert changed == 0


def test_outcome_status(cur):
    cur.execute("select outcome_status('will_book'), outcome_status('left_company')")
    assert cur.fetchone() == ("pending", "lost")
    with pytest.raises(psycopg.Error):
        cur.execute("select outcome_status('won')")
