from datetime import date

import psycopg
import pytest

from conftest import (add_staff, apply, as_owner, as_service, as_user, card, ck, claim, count, hi, line, line_id,
                      ln, raises, save, st, stage, won)

JO, AL, MEL = "jo@kallibr.com.au", "al@kallibr.com.au", "mel@kallibr.com.au"
S = [st(1), st(2)]
L = [ln(1, "Heights", "2024-06-10"), ln(1, "Confined Space", "2024-02-05"), ln(2, "Heights", "2025-01-10")]
TABLES = ("cards", "students", "lines")


def counts(cur):
    return tuple(count(cur, f"select count(*) from {t}") for t in TABLES)


def staging_rows(cur):
    return sum(count(cur, f"select count(*) from {t}") for t in ("stage_students", "stage_lines", "stage_checks", "stage_history"))


def call_at(cur, staff_id, when, card_key="B:900"):
    """A call logged at a given moment (timestamptz literal)."""
    with as_owner(cur):
        cur.execute("insert into call_logs (card_key, staff_id, called_at) values (%s, %s, %s::timestamptz)",
                    (card_key, staff_id, when))


def test_first_push_creates_cards_students_lines(cur):
    as_service(cur)
    run = stage(cur, students=S, lines=L)
    out = apply(cur, run)
    assert counts(cur) == (1, 2, 3)
    assert count(cur, "select count(*) from lines where status = 'not_called' and in_window") == 3
    assert out["lines_new"] == 3
    assert count(cur, "select result from sync_runs where id = %s", (run,)) == "ok"
    assert staging_rows(cur) == 0


def test_running_twice_changes_nothing(cur):
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    out = apply(cur, stage(cur, students=S, lines=L))
    assert out["lines_new"] == 0 and counts(cur) == (1, 2, 3)


def test_incomplete_staging_raises_and_changes_nothing(cur):   # Review Focus 2
    as_service(cur)
    run = stage(cur, students=S, lines=L)
    cur.execute("delete from stage_lines where run_id=%s and contact_id=1", (run,))
    raises(cur, "select apply_push(%s)", (run,), match="staging incomplete")
    assert count(cur, "select count(*) from lines") == 0 and count(cur, "select count(*) from cards") == 0


def test_run_must_be_running(cur):
    as_service(cur)
    run = stage(cur, students=S, lines=L)
    apply(cur, run)
    raises(cur, "select apply_push(%s)", (run,), match="run not found or not running")
    raises(cur, "select apply_push(-1)", match="run not found or not running")


def test_older_running_run_is_superseded(cur):
    as_service(cur)
    old = stage(cur, students=S, lines=L)
    new = stage(cur, students=S, lines=L)
    apply(cur, new)
    with as_owner(cur):
        cur.execute("select result, message from sync_runs where id = %s", (old,))
        assert cur.fetchone() == ("failed", "superseded")
    assert staging_rows(cur) == 0


def test_student_with_calls_stays_on_their_card(cur):
    add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    claim(cur, JO); save(cur, JO, [(line_id(cur, 1), "no_answer")])
    as_service(cur)
    apply(cur, stage(cur, students=[st(1, "B:901", target_name="Kim Other")], lines=[L[0]]))
    assert count(cur, "select card_key from students where contact_id = 1") == "B:900"


def test_student_without_calls_moves(cur):
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    apply(cur, stage(cur, students=[st(1, "B:901", target_name="Kim Other")], lines=[L[0]]))
    assert count(cur, "select card_key from students where contact_id = 1") == "B:901"
    assert count(cur, "select target_name from cards where card_key = 'B:901'") == "Kim Other"


def test_existing_card_details_update_but_claim_is_kept(cur):
    add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    claim(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=[st(1, target_name="Pat Booker-Smith"), st(2)], lines=L))
    assert count(cur, "select target_name from cards where card_key = 'B:900'") == "Pat Booker-Smith"
    assert card(cur, "B:900")["claimed_by"] is not None


def test_new_line_on_do_not_call_card_is_lost(cur):
    add_staff(cur, JO); add_staff(cur, MEL, role="manager"); as_service(cur)
    apply(cur, stage(cur, students=[st(1)], lines=[L[0]]))
    claim(cur, JO); save(cur, JO, [(line_id(cur, 1), "do_not_call")], dnc_card=True)
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=[L[0], L[2]]))
    new = line_id(cur, 2)
    assert line(cur, new)[:3] == ("lost", "do_not_call", None)
    assert count(cur, "select count(*) from line_outcomes where line_id = %s", (new,)) == 0
    as_user(cur, MEL); cur.execute("select clear_do_not_call('B:900')")
    assert line(cur, new)[:2] == ("not_called", None)


def test_win_credits_last_caller_before_booking(cur):
    jo, al = add_staff(cur, JO), add_staff(cur, AL); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    call_at(cur, jo, "2026-11-17 10:00 Australia/Sydney"); call_at(cur, al, "2026-11-21 10:00 Australia/Sydney")
    out = apply(cur, stage(cur, students=S, lines=L,
                           checks=[ck(1, won=True, booked_on="2026-11-20", class_date="2026-12-01", course_name="Heights Refresher")]))
    h = line_id(cur, 1)
    assert won(cur, h) == dict(status="won", won_by=jo, won_without_call=False, won_booked_on=date(2026, 11, 20))
    assert out["wins"] == 1
    assert count(cur, "select wins from sync_runs where result = 'ok' order by id desc limit 1") == 1


def test_win_credit_counts_a_call_on_the_booking_day(cur):
    jo = add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    call_at(cur, jo, "2026-11-20 16:00 Australia/Sydney")
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True, booked_on="2026-11-20")]))
    assert won(cur, line_id(cur, 1))["won_by"] == jo


def test_win_without_any_earlier_call(cur):
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True, booked_on="2026-11-20")]))
    w = won(cur, line_id(cur, 1))
    assert (w["status"], w["won_by"], w["won_without_call"]) == ("won", None, True)


def test_win_with_no_booked_on_uses_today(cur):
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True)]))
    assert won(cur, line_id(cur, 1))["won_booked_on"] == count(cur, "select sydney_today()")


def test_win_credit_uses_sydney_date(cur):                 # Review Focus 3
    jo = add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    # call logged at 2026-11-19 22:30 UTC = 20 Nov 09:30 Sydney; booked_on 2026-11-19 → not credited
    call_at(cur, jo, "2026-11-19 22:30+00")
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True, booked_on="2026-11-19")]))
    assert won(cur, line_id(cur, 1))["won_without_call"] is True


def test_reversal_restores_previous_status(cur):
    add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    h = line_id(cur, 1)
    claim(cur, JO); save(cur, JO, [(h, "will_book")]); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True, booked_on="2026-11-20")]))
    assert line(cur, h)[0] == "won"
    out = apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=False)]))
    assert line(cur, h)[:2] == ("pending", "will_book") and out["reversals"] == 1
    assert count(cur, "select num_nonnulls(won_at, won_booked_on, won_class_date, won_course, won_by, won_without_call, "
                      "status_before_won, outcome_before_won) from lines where id = %s", (h,)) == 0


def test_still_won_while_any_real_booking_remains(cur):
    jo = add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    call_at(cur, jo, "2026-11-17 10:00 Australia/Sydney")
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True, booked_on="2026-11-20", class_date="2026-12-01")]))
    out = apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, won=True, booked_on="2026-11-20", class_date="2027-01-12")]))
    h = line_id(cur, 1)
    assert won(cur, h)["status"] == "won" and won(cur, h)["won_by"] == jo and out["wins"] == 0
    assert count(cur, "select won_class_date from lines where id = %s", (h,)) == date(2027, 1, 12)


def test_line_without_a_check_is_untouched(cur):
    add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    h = line_id(cur, 1)
    claim(cur, JO); save(cur, JO, [(h, "info_sent")]); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(2, last_done="2025-01-10", in_window=False)]))
    assert line(cur, h)[:2] == ("pending", "info_sent")
    assert count(cur, "select in_window from lines where id = %s", (h,)) is True


def test_out_of_window_and_tentative_flags(cur):
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    apply(cur, stage(cur, students=S, lines=L, checks=[ck(1, in_window=False), ck(2, last_done="2025-01-10", tentative=True)]))
    assert count(cur, "select in_window from lines where id = %s", (line_id(cur, 1),)) is False
    assert count(cur, "select tentative from lines where id = %s", (line_id(cur, 2),)) is True
    assert line(cur, line_id(cur, 1))[0] == "not_called"


def test_auto_release_after_14_days(cur):
    jo = add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=[st(1, "B:900"), st(2, "B:901"), st(3, "B:902")],
                     lines=[ln(1), ln(2), ln(3)]))
    with as_owner(cur):
        cur.execute("update cards set claimed_by = %s, claimed_at = now() - interval '20 days'", (jo,))
        cur.execute("update cards set last_activity_at = now() - interval '15 days' where card_key in ('B:900', 'B:901')")
        cur.execute("update cards set callback_on = sydney_today() + 1 where card_key = 'B:901'")
        cur.execute("update cards set last_activity_at = now() - interval '13 days' where card_key = 'B:902'")
    out = apply(cur, stage(cur))
    assert [card(cur, k)["claimed_by"] for k in ("B:900", "B:901", "B:902")] == [None, jo, jo]
    assert out["released"] == 1
    assert count(cur, "select count(*) from card_events where card_key = 'B:900' and event = 'auto_released' "
                      "and staff_id = %s", (jo,)) == 1


def test_call_history_is_never_deleted(cur):
    add_staff(cur, JO); as_service(cur)
    apply(cur, stage(cur, students=S, lines=L))
    claim(cur, JO); save(cur, JO, [(line_id(cur, 1), "no_answer"), (line_id(cur, 2), "will_book")], notes="hi")
    as_service(cur)
    before = (count(cur, "select count(*) from call_logs"), count(cur, "select count(*) from line_outcomes"))
    apply(cur, stage(cur, students=[st(2)], lines=[L[2]]))
    apply(cur, stage(cur))
    assert (count(cur, "select count(*) from call_logs"), count(cur, "select count(*) from line_outcomes")) == before
    assert count(cur, "select count(*) from lines") == 3


def test_course_history_is_replaced_per_student(cur):
    as_service(cur)
    apply(cur, stage(cur, students=S, lines=L,
                     history=[hi(1, "A", "2024-01-01"), hi(1, "B", "2024-02-01"), hi(2, "C", "2024-03-01")]))
    apply(cur, stage(cur, students=[st(1)], lines=[L[0]], history=[hi(1, "A", "2024-01-01"), hi(1, "D", "2025-01-01")]))
    with as_owner(cur):
        cur.execute("select contact_id, course_name from course_history order by 1, 2")
        assert cur.fetchall() == [(1, "A"), (1, "D"), (2, "C")]


def test_only_service_role_may_run(cur):
    add_staff(cur, JO)
    as_user(cur, JO)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("select apply_push(1)")


def _stage_full_size(cur):
    """A run of 3,600 students and 4,000 lines (with checks), like a real night."""
    with as_owner(cur):
        cur.execute("insert into sync_runs (result, students_pushed, lines_pushed, checks_pushed, history_pushed) "
                    "values ('running', 3600, 4000, 4000, 0) returning id")
        run = cur.fetchone()[0]
        cur.execute("insert into stage_students select %s, g, 'S' || g, 'Org ' || (g %% 300), 'B:' || (100000 + g %% 600), "
                    "'booker', 100000 + g %% 600, 'Booker ' || (g %% 600), 'Org ' || (g %% 300), 'org ' || (g %% 300) "
                    "from generate_series(1, 3600) g", (run,))
        cur.execute("insert into stage_lines select %s, g, 'Heights', date '2024-06-10', date '2026-06-10', 'Course', 'QLD', true "
                    "from generate_series(1, 3600) g "
                    "union all select %s, g, 'Confined Space', date '2024-06-10', date '2026-06-10', 'Course', 'NSW', true "
                    "from generate_series(1, 400) g", (run, run))
        cur.execute("insert into stage_checks select %s, contact_id, refresher_type, last_done, true, false, null, null, null, false "
                    "from stage_lines where run_id = %s", (run, run))
    return run


def test_full_size_push_finishes_inside_the_api_time_limit(cur):
    """About 4,000 lines in one run, under the 8s statement limit Supabase's API applies.

    The staging tables are emptied every night, so their statistics say "pages on disk, zero rows";
    plans built on that timed out on the test project (31s). Recreate that state, then push.
    """
    as_service(cur)
    first = _stage_full_size(cur)
    with as_owner(cur):
        cur.execute("select apply_push(%s)", (first,))
        cur.execute("delete from lines; delete from students; delete from cards")
        cur.execute("analyze cards, students, lines, stage_students, stage_lines, stage_checks, stage_history")
    run = _stage_full_size(cur)
    as_service(cur)
    cur.execute("set local statement_timeout = '8s'")
    out = apply(cur, run)
    assert out["lines_new"] == 4000
