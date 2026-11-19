from datetime import date, timedelta

import psycopg
import pytest

from conftest import add_staff, as_anon, as_owner, as_user, count, raises, seed_card

JO, AL = "jo@kallibr.com.au", "al@kallibr.com.au"


def set_line(cur, lid, **fields):
    with as_owner(cur):
        cols = ", ".join(f"{k} = %s" for k in fields)
        cur.execute(f"update lines set {cols} where id = %s", (*fields.values(), lid))


def today(cur):
    return count(cur, "select sydney_today()")


def v_card(cur, key):
    cur.execute("select students, open_lines, overdue_lines, earliest_due, locations, types, has_tentative, "
                "sibling_cards, claimed_by_name from v_cards where card_key = %s", (key,))
    return cur.fetchone()


def test_v_cards_counts_open_lines_only(cur):
    t = today(cur)
    ids = seed_card(cur, "B:900", students=((1, "Sam Lee"), (2, "Kim Tran"), (3, "Ali Khan")),
                    lines=((1, "Heights", "2024-06-10"), (2, "Confined Space", "2024-12-01"), (1, "Confined Space", "2024-02-05"),
                           (3, "Heights", "2024-07-01"), (3, "HSR", "2025-01-01")))
    set_line(cur, ids[(1, "Heights")], due_date=t - timedelta(days=10), location="QLD")
    set_line(cur, ids[(2, "Confined Space")], status="pending", outcome="will_book", due_date=t + timedelta(days=30), location="NSW")
    set_line(cur, ids[(1, "Confined Space")], status="lost", outcome="not_needed", location="VIC", tentative=True)
    set_line(cur, ids[(3, "Heights")], status="won", location="VIC")
    set_line(cur, ids[(3, "HSR")], in_window=False, location="VIC", due_date=t - timedelta(days=400))
    add_staff(cur, JO); as_user(cur, JO)
    students, open_lines, overdue, earliest, locations, types, tentative, siblings, _ = v_card(cur, "B:900")
    assert (students, open_lines, overdue, earliest) == (2, 2, 1, t - timedelta(days=10))
    assert set(locations) == {"NSW", "QLD"} and set(types) == {"Confined Space", "Heights"}
    assert tentative is False and siblings == 0


def test_v_cards_shows_owner_name_and_finished_cards(cur):
    jo = add_staff(cur, JO, full_name="Jo Smith")
    ids = seed_card(cur, "B:900")
    set_line(cur, ids[(1, "Heights")], status="lost", outcome="not_needed")
    with as_owner(cur):
        cur.execute("update cards set claimed_by = %s", (jo,))
    as_user(cur, JO)
    students, open_lines, overdue, earliest, locations, types, tentative, siblings, owner = v_card(cur, "B:900")
    assert (students, open_lines, overdue, earliest, list(locations), list(types), owner) == (0, 0, 0, None, [], [], "Jo Smith")


def test_v_cards_tentative_flag(cur):
    ids = seed_card(cur, "B:900")
    set_line(cur, ids[(1, "Heights")], tentative=True)
    add_staff(cur, JO); as_user(cur, JO)
    assert v_card(cur, "B:900")[6] is True


def test_v_cards_siblings_share_org_key(cur):
    seed_card(cur, "B:900", students=((1, "A"),), lines=((1, "Heights", "2024-06-10"),), org_name="Acme Pty Ltd")
    seed_card(cur, "B:901", students=((2, "B"),), lines=((2, "Heights", "2024-06-10"),), org_name="Acme Pty Ltd")
    done = seed_card(cur, "B:902", students=((3, "C"),), lines=((3, "Heights", "2024-06-10"),), org_name="Acme Pty Ltd")
    seed_card(cur, "B:903", students=((4, "D"),), lines=((4, "Heights", "2024-06-10"),), org_name="Other Co")
    set_line(cur, done[(3, "Heights")], status="won")
    add_staff(cur, JO); as_user(cur, JO)
    assert [v_card(cur, k)[7] for k in ("B:900", "B:901", "B:902", "B:903")] == [1, 1, 2, 0]


def test_v_cards_hidden_from_non_staff(cur):
    seed_card(cur)
    as_user(cur, "stranger@kallibr.com.au")
    cur.execute("select count(*) from v_cards"); assert cur.fetchone()[0] == 0
    as_anon(cur)
    raises(cur, "select * from v_cards")


def seed_stats(cur):
    """JO: 2 claimed events, 3 calls, lines pending 1 / lost 1 / won 1."""
    jo = add_staff(cur, JO, full_name="Jo Smith"); al = add_staff(cur, AL, full_name="Al Brown")
    add_staff(cur, "gone@kallibr.com.au", active=False)
    ids = seed_card(cur, "B:900", students=((1, "A"), (2, "B"), (3, "C")),
                    lines=((1, "Heights", "2024-06-10"), (2, "Heights", "2024-06-10"), (3, "Heights", "2024-06-10")))
    seed_card(cur, "B:901", students=((4, "D"),), lines=((4, "Heights", "2024-06-10"),))
    with as_owner(cur):
        cur.execute("insert into card_events (card_key, staff_id, event) values ('B:900', %s, 'claimed'), "
                    "('B:901', %s, 'claimed'), ('B:900', %s, 'released')", (jo, jo, jo))
        for _ in range(3):
            cur.execute("insert into call_logs (card_key, staff_id) values ('B:900', %s)", (jo,))
        cur.execute("update cards set claimed_by = %s where card_key = 'B:901'", (jo,))   # B:901 still theirs
    set_line(cur, ids[(1, "Heights")], status="pending", outcome="will_book", last_outcome_by=jo, last_outcome_at="now()")
    set_line(cur, ids[(2, "Heights")], status="lost", outcome="not_needed", last_outcome_by=jo, last_outcome_at="now()")
    with as_owner(cur):
        cur.execute("update lines set status='won', won_by=%s, won_at=sydney_today(), won_without_call=false "
                    "where id = %s", (jo, ids[(3, "Heights")]))
    return jo, al


def test_team_stats_counts_and_period(cur):
    jo, al = seed_stats(cur)
    as_user(cur, AL)
    cur.execute("select staff_id, full_name, cards_taken, calls_logged, pending, won, lost, win_rate from team_stats()")
    rows = {r[0]: r[1:] for r in cur.fetchall()}
    assert rows[jo] == ("Jo Smith", 2, 3, 1, 1, 1, pytest.approx(0.5))
    cur.execute("select cards_taken, calls_logged, pending, won, lost, win_rate from team_stats(sydney_today() + 1) "
                "where staff_id = %s", (jo,))
    assert cur.fetchone() == (0, 0, 0, 0, 0, None)
    cur.execute("select cards_taken, calls_logged from team_stats(sydney_today()) where staff_id = %s", (jo,))
    assert cur.fetchone() == (2, 3)


def test_team_stats_counts_assignments_to_them(cur):
    jo, al = seed_stats(cur)
    with as_owner(cur):
        cur.execute("insert into card_events (card_key, staff_id, event) values ('B:901', %s, 'assigned')", (al,))
        cur.execute("update cards set claimed_by = %s where card_key = 'B:901'", (al,))
    as_user(cur, AL)
    cur.execute("select cards_taken from team_stats() where staff_id = %s", (al,))
    assert cur.fetchone()[0] == 1


def test_team_stats_skips_a_card_released_without_a_call(cur):
    """Owner's request, 19 Nov 2026: a take released with no call logged (a mis-click) is not a card taken."""
    jo, al = seed_stats(cur)
    seed_card(cur, "B:902", students=((5, "E"),), lines=((5, "Heights", "2024-06-10"),))
    with as_owner(cur):
        cur.execute("insert into card_events (card_key, staff_id, event) values ('B:902', %s, 'claimed'), "
                    "('B:902', %s, 'released')", (jo, jo))
    as_user(cur, AL)
    cur.execute("select cards_taken from team_stats() where staff_id = %s", (jo,))
    assert cur.fetchone()[0] == 2        # B:900 (called on, then released) and B:901 (still theirs); not B:902


def test_team_stats_does_not_count_an_update_with_no_call_as_a_call(cur):
    """Owner's request, 20 Nov 2026: an update with no call isn't a call, but it is work on the card."""
    jo, al = seed_stats(cur)
    seed_card(cur, "B:902", students=((5, "E"),), lines=((5, "Heights", "2024-06-10"),))
    with as_owner(cur):
        cur.execute("insert into card_events (card_key, staff_id, event, at) values "
                    "('B:902', %s, 'claimed', now() - interval '1 minute')", (jo,))
        cur.execute("insert into call_logs (card_key, staff_id, no_call) values ('B:902', %s, true)", (jo,))
        cur.execute("insert into card_events (card_key, staff_id, event) values ('B:902', %s, 'released')", (jo,))
    as_user(cur, AL)
    cur.execute("select cards_taken, calls_logged from team_stats() where staff_id = %s", (jo,))
    assert cur.fetchone() == (3, 3)          # B:902 counts as taken; still 3 calls


def test_team_stats_lists_staff_with_no_activity(cur):
    jo, al = seed_stats(cur)
    as_user(cur, JO)
    cur.execute("select staff_id, cards_taken, calls_logged, pending, won, lost, win_rate from team_stats()")
    rows = {r[0]: r[1:] for r in cur.fetchall()}
    assert rows[al] == (0, 0, 0, 0, 0, None)
    assert len(rows) == 2                                # the inactive member is not listed


def add_cohort_lines(cur, rows):
    """rows: (contact_id, type, last_done, status, won_without_call, location)."""
    jo = add_staff(cur, JO)
    students = tuple((r[0], f"S{r[0]}") for r in rows)
    ids = seed_card(cur, "B:900", students=students, lines=tuple((r[0], r[1], r[2]) for r in rows))
    for cid, rtype, _, status, wwc, loc in rows:
        set_line(cur, ids[(cid, rtype)], status=status, location=loc,
                 won_by=(jo if status == "won" and not wwc else None),
                 won_without_call=(wwc if status == "won" else None))
    return ids


COHORT = [(1, "Heights", "2025-01-03", "not_called", None, "QLD"),
          (2, "Heights", "2025-01-10", "pending", None, "NSW"),
          (3, "Confined Space", "2025-01-15", "lost", None, "NSW"),
          (4, "Heights", "2025-01-20", "won", False, "QLD"),
          (5, "Heights", "2025-01-31", "won", True, "NSW"),
          (6, "Heights", "2025-02-01", "not_called", None, "QLD")]


def test_cohort_segments(cur):
    add_cohort_lines(cur, COHORT)
    as_user(cur, JO)
    cur.execute("select month, segment, n from cohort_counts() order by 1, 2")
    assert cur.fetchall() == [(date(2025,1,1),'booked_without_call',1), (date(2025,1,1),'lost',1), (date(2025,1,1),'not_called',1),
                              (date(2025,1,1),'pending',1), (date(2025,1,1),'won',1), (date(2025,2,1),'not_called',1)]


def test_cohort_includes_out_of_window_lines(cur):
    ids = add_cohort_lines(cur, COHORT)
    set_line(cur, ids[(6, "Heights")], in_window=False)
    as_user(cur, JO)
    cur.execute("select n from cohort_counts() where month = '2025-02-01'")
    assert cur.fetchone()[0] == 1


def test_cohort_filters(cur):
    add_cohort_lines(cur, COHORT)
    as_user(cur, JO)
    cur.execute("select sum(n) from cohort_counts('Heights')"); assert cur.fetchone()[0] == 5
    cur.execute("select sum(n) from cohort_counts(null, 'NSW')"); assert cur.fetchone()[0] == 3
    cur.execute("select segment, n from cohort_counts('Heights', 'NSW') order by 1")
    assert cur.fetchall() == [("booked_without_call", 1), ("pending", 1)]


@pytest.mark.parametrize("sql", ["select * from team_stats()", "select * from cohort_counts()"])
def test_reporting_refused_for_non_staff(cur, sql):
    seed_card(cur)
    as_user(cur, "stranger@kallibr.com.au")
    raises(cur, sql, match="not staff")
    as_anon(cur)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql)
