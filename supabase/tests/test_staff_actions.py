from datetime import timedelta
from types import SimpleNamespace

import pytest

from conftest import (add_staff, as_owner, as_service, as_user, call_log, card, claim, line, raises,
                      run_concurrently, save, seed_card)

JO, AL, MEL = "jo@kallibr.com.au", "al@kallibr.com.au", "mel@kallibr.com.au"


@pytest.fixture
def L(cur):
    s = SimpleNamespace()
    s.jo = add_staff(cur, JO); s.al = add_staff(cur, AL); s.mel = add_staff(cur, MEL, role="manager")
    ids = seed_card(cur, "B:900", students=((1, "Sam Lee"), (2, "Kim Tran")),
                    lines=((1, "Heights", "2024-06-10"), (1, "Confined Space", "2024-02-05"), (2, "Heights", "2025-01-10")))
    s.h, s.c, s.h2 = ids[(1, "Heights")], ids[(1, "Confined Space")], ids[(2, "Heights")]
    return s


def events(cur, card_key="B:900"):
    with as_owner(cur):
        cur.execute("select event, staff_id from card_events where card_key = %s order by id", (card_key,))
        return cur.fetchall()


def test_claim_is_exclusive(cur, L):
    as_user(cur, JO); cur.execute("select claim_card('B:900')"); assert cur.fetchone()[0] is True
    as_user(cur, AL); cur.execute("select claim_card('B:900')"); assert cur.fetchone()[0] is False
    assert card(cur, "B:900")["claimed_by"] == L.jo and events(cur) == [("claimed", L.jo)]


def test_simultaneous_claims_give_one_winner(db_url):
    # two separate connections, both inside open transactions; the second blocks until the first commits
    results = run_concurrently(db_url, [(JO, "select claim_card('B:901')"), (AL, "select claim_card('B:901')")])
    assert sorted(results) == [False, True]


def test_non_staff_cannot_use_actions(cur, L):
    as_user(cur, "stranger@kallibr.com.au")
    raises(cur, "select claim_card('B:900')", match="not staff")
    raises(cur, "select save_call_log('B:900', null, null, '[]'::jsonb)", match="not staff")


def test_only_owner_or_manager_releases(cur, L):
    claim(cur, JO)
    as_user(cur, AL)
    raises(cur, "select release_card('B:900')", match="card not claimed by you")
    assert card(cur, "B:900")["claimed_by"] == L.jo
    as_user(cur, MEL); cur.execute("select release_card('B:900')")
    assert card(cur, "B:900")["claimed_by"] is None and events(cur)[-1][0] == "released"
    claim(cur, JO); cur.execute("select release_card('B:900')")
    assert card(cur, "B:900")["claimed_by"] is None


def test_assign_is_manager_only(cur, L):
    as_user(cur, AL)
    raises(cur, "select assign_card('B:900', %s)", (L.al,), match="managers only")
    as_user(cur, MEL); cur.execute("select assign_card('B:900', %s)", (L.al,))
    assert card(cur, "B:900")["claimed_by"] == L.al
    assert events(cur)[-1] == ("assigned", L.al)
    cur.execute("select assign_card('B:900', null)")
    assert card(cur, "B:900")["claimed_by"] is None


def test_save_sets_each_line_separately(cur, L):
    claim(cur, JO)
    out = save(cur, JO, [(L.h, "will_book"), (L.c, "not_needed")], notes="spoke to Pat")
    assert out["skipped_line_ids"] == []
    assert line(cur, L.h)[:2] == ("pending", "will_book") and line(cur, L.c)[:2] == ("lost", "not_needed")
    assert line(cur, L.h2)[:2] == ("not_called", None)
    assert line(cur, L.h)[2] == L.jo
    assert call_log(cur, out["call_log_id"]).staff_id == L.jo
    assert call_log(cur, out["call_log_id"]).no_call is False


def test_an_update_with_no_call_sets_outcomes_and_is_marked(cur, L):
    """Owner's request, 20 Nov 2026: record an outcome from an email reply without logging a call."""
    claim(cur, JO)
    out = save(cur, JO, [(L.h, "not_needed")], notes="Emailed back: no longer needed", no_call=True)
    assert line(cur, L.h)[:3] == ("lost", "not_needed", L.jo)
    log = call_log(cur, out["call_log_id"])
    assert (log.no_call, log.notes) == (True, "Emailed back: no longer needed")


def test_the_old_page_still_logs_a_call(cur, L):
    """The page before 0009 sends five arguments; that must still save, as a call."""
    claim(cur, JO)
    cur.execute("select save_call_log(p_card_key => 'B:900', p_notes => null, p_callback_on => null, "
                "p_outcomes => %s::jsonb, p_dnc_card => false)", (f'[{{"line_id": {L.h}, "outcome": "no_answer"}}]',))
    assert call_log(cur, cur.fetchone()[0]["call_log_id"]).no_call is False


def test_save_requires_claim(cur, L):
    claim(cur, JO)
    as_user(cur, AL)
    raises(cur, "select save_call_log('B:900', null, null, %s::jsonb)", (f'[{{"line_id": {L.h}, "outcome": "no_answer"}}]',),
           match="card not claimed by you")
    assert line(cur, L.h)[:2] == ("not_called", None)


def test_manager_may_save_on_any_card(cur, L):
    claim(cur, JO)
    out = save(cur, MEL, [(L.h, "info_sent")])
    assert line(cur, L.h)[:2] == ("pending", "info_sent") and call_log(cur, out["call_log_id"]).staff_id == L.mel


def test_line_from_another_card_is_rejected(cur, L):
    other = seed_card(cur, "B:901", students=((3, "Ali Khan"),), lines=((3, "Heights", "2024-07-01"),))
    claim(cur, JO)
    as_user(cur, JO)
    raises(cur, "select save_call_log('B:900', null, null, %s::jsonb)",
           (f'[{{"line_id": {other[(3, "Heights")]}, "outcome": "no_answer"}}]',), match="line not on this card")
    with as_owner(cur):
        cur.execute("select count(*) from call_logs"); assert cur.fetchone()[0] == 0


def test_empty_outcomes_are_rejected(cur, L):
    claim(cur, JO)
    raises(cur, "select save_call_log('B:900', 'x', null, '[]'::jsonb)", match="outcome")


def test_call_back_needs_a_date_not_in_the_past(cur, L):
    claim(cur, JO)
    cur.execute("select sydney_today()"); today = cur.fetchone()[0]
    payload = f'[{{"line_id": {L.h}, "outcome": "call_back"}}]'
    raises(cur, "select save_call_log('B:900', null, null, %s::jsonb)", (payload,), match="call-back date required")
    raises(cur, "select save_call_log('B:900', null, %s, %s::jsonb)", (today - timedelta(days=1), payload),
           match="call-back date required")
    save(cur, JO, [(L.h, "call_back")], callback_on=today)
    assert card(cur, "B:900")["callback_on"] == today and line(cur, L.h)[:2] == ("pending", "call_back")


def test_won_line_is_skipped_not_overwritten(cur, L):          # Review Focus 1
    claim(cur, JO); as_service(cur); cur.execute("update lines set status='won', won_at=current_date where id=%s", (L.h,))
    out = save(cur, JO, [(L.h, "not_needed"), (L.c, "will_book")])
    assert out["skipped_line_ids"] == [L.h]
    assert line(cur, L.h)[0] == "won" and line(cur, L.c)[0] == "pending"
    with as_owner(cur):
        cur.execute("select line_id from line_outcomes where call_log_id = %s", (out["call_log_id"],))
        assert [r[0] for r in cur.fetchall()] == [L.c]


def test_notes_are_stored_verbatim(cur, L):                     # Review Focus 4
    claim(cur, JO); out = save(cur, JO, [(L.h, "no_answer")], notes="<script>alert(1)</script> O'Brien & Sons")
    assert call_log(cur, out["call_log_id"]).notes == "<script>alert(1)</script> O'Brien & Sons"


def test_do_not_call_one_line_only(cur, L):
    claim(cur, JO); save(cur, JO, [(L.h, "do_not_call")])
    assert line(cur, L.h)[:2] == ("lost", "do_not_call") and line(cur, L.c)[:2] == ("not_called", None)
    assert card(cur, "B:900")["do_not_call"] is False


def test_do_not_call_whole_card(cur, L):
    claim(cur, JO); save(cur, JO, [(L.h, "do_not_call")], dnc_card=True)
    assert [line(cur, x)[:2] for x in (L.h, L.c, L.h2)] == [("lost", "do_not_call")] * 3
    assert card(cur, "B:900") == dict(do_not_call=True, claimed_by=None, callback_on=None)
    as_user(cur, AL); cur.execute("select claim_card('B:900')"); assert cur.fetchone()[0] is False


def test_clear_do_not_call_is_manager_only_and_restores(cur, L):
    claim(cur, JO); save(cur, JO, [(L.h, "do_not_call")], dnc_card=True)
    as_user(cur, JO)
    raises(cur, "select clear_do_not_call('B:900')", match="managers only")
    as_user(cur, MEL); cur.execute("select clear_do_not_call('B:900')")
    assert [line(cur, x)[:2] for x in (L.h, L.c, L.h2)] == [("not_called", None)] * 3
    assert card(cur, "B:900")["do_not_call"] is False


def test_upsert_staff_is_manager_only(cur, L):
    as_user(cur, JO)
    raises(cur, "select upsert_staff('new@kallibr.com.au', 'New', 'staff', true)", match="managers only")
    as_user(cur, MEL)
    cur.execute("select upsert_staff('New@Kallibr.com.au', 'New Person', 'staff', true)"); new_id = cur.fetchone()[0]
    cur.execute("select upsert_staff('new@kallibr.com.au', 'New Person', 'manager', true)")
    assert cur.fetchone()[0] == new_id
    with as_owner(cur):
        cur.execute("select email, role from staff where id = %s", (new_id,))
        assert cur.fetchone() == ("new@kallibr.com.au", "manager")


def test_manager_cannot_lock_themselves_out(cur, L):
    as_user(cur, MEL)
    raises(cur, "select upsert_staff(%s, 'Mel', 'manager', false)", (MEL,), match="your own")
    raises(cur, "select upsert_staff(%s, 'Mel', 'staff', true)", (MEL,), match="your own")


def test_deactivating_staff_releases_cards_and_blocks_reads(cur, L):   # Review Focus 5
    claim(cur, JO); as_user(cur, MEL); cur.execute("select upsert_staff(%s, 'Jo', 'staff', false)", (JO,))
    assert card(cur, "B:900")["claimed_by"] is None
    assert events(cur)[-1] == ("released", L.jo)
    as_user(cur, JO); cur.execute("select count(*) from students"); assert cur.fetchone()[0] == 0
    raises(cur, "select claim_card('B:900')", match="not staff")
