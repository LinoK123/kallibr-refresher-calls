from datetime import date

import config
import manager_report as mr

MON = date(2026, 11, 23)       # the report runs on this Monday; it covers Mon 16 - Sun 22 Nov


class FakeClient:
    """A small week of activity. Filters are ignored: the report filters for itself."""

    def __init__(self):
        self.tables = {
            "staff": [
                {"id": "u1", "email": "jo@kallibr.com.au", "full_name": "Jo Smith", "role": "staff", "active": True},
                {"id": "u2", "email": "al@kallibr.com.au", "full_name": "Al <Brown> & Co", "role": "staff", "active": True},
                {"id": "u3", "email": "quiet@kallibr.com.au", "full_name": "Quiet Person", "role": "staff", "active": True},
                {"id": "m1", "email": "mel@kallibr.com.au", "full_name": "Mel Manager", "role": "manager", "active": True},
                {"id": "m2", "email": "gone@kallibr.com.au", "full_name": "Gone Manager", "role": "manager", "active": False},
            ],
            "call_logs": [
                {"id": 1, "staff_id": "u1", "called_at": "2026-11-16T00:30:00+00:00"},   # Mon 16 Nov 11:30 Sydney: in
                {"id": 2, "staff_id": "u1", "called_at": "2026-11-22T12:30:00+00:00"},   # Sun 22 Nov 11:30 pm Sydney: in
                {"id": 3, "staff_id": "u2", "called_at": "2026-11-22T13:30:00+00:00"},   # Mon 23 Nov 12:30 am Sydney: out
                {"id": 4, "staff_id": "u2", "called_at": "2026-11-15T12:00:00+00:00"},   # Sun 15 Nov 11 pm Sydney: out
                {"id": 5, "staff_id": "u2", "called_at": "2026-11-18T01:00:00+00:00"},   # in
            ],
            "line_outcomes": [
                {"call_log_id": 1, "outcome": "will_book"}, {"call_log_id": 1, "outcome": "no_answer"},
                {"call_log_id": 1, "outcome": "not_needed"}, {"call_log_id": 2, "outcome": "went_elsewhere"},
                {"call_log_id": 3, "outcome": "will_book"},
                {"call_log_id": 5, "outcome": "info_sent"}, {"call_log_id": 5, "outcome": "do_not_call"},
            ],
            "card_events": [
                {"card_key": "B:1", "staff_id": "u1", "event": "claimed", "at": "2026-11-17T01:00:00+00:00"},
                {"card_key": "B:1", "staff_id": "u1", "event": "claimed", "at": "2026-11-18T01:00:00+00:00"},   # same card again
                {"card_key": "B:2", "staff_id": "u2", "event": "assigned", "at": "2026-11-19T01:00:00+00:00"},
                {"card_key": "B:9", "staff_id": "u1", "event": "claimed", "at": "2026-11-10T01:00:00+00:00"},   # the week before
                {"card_key": "B:1", "staff_id": "u1", "event": "released", "at": "2026-11-19T01:00:00+00:00"},  # not a take
            ],
            "lines": [
                line(1, "not_called", first_listed_on="2026-11-17"), line(2, "pending"),
                line(3, "not_called", first_listed_on="2026-11-20"), line(4, "not_called"),
                line(5, "lost"),
                line(6, "won", won_by="u1", won_at="2026-11-20", won_without_call=False),
                line(7, "won", won_by=None, won_at="2026-11-21", won_without_call=True),
                line(8, "won", won_by="u2", won_at="2026-11-23", won_without_call=False),   # this week, not last
                line(9, "not_called", in_window=False),
            ],
            "students": [{"contact_id": c, "card_key": k} for c, k in
                         [(1, "B:1"), (2, "B:2"), (3, "B:3"), (4, "B:3"), (5, "B:4"), (6, "B:5"), (7, "B:5"), (8, "B:2"), (9, "B:3")]],
            "cards": [
                {"card_key": "B:1", "claimed_by": "u1", "claimed_at": "2026-11-17T01:00:00+00:00", "callback_on": "2026-11-20", "do_not_call": False},
                {"card_key": "B:2", "claimed_by": "u2", "claimed_at": "2026-11-19T01:00:00+00:00", "callback_on": None, "do_not_call": False},
                {"card_key": "B:3", "claimed_by": None, "claimed_at": None, "callback_on": None, "do_not_call": False},
                {"card_key": "B:4", "claimed_by": None, "claimed_at": None, "callback_on": None, "do_not_call": True},
                {"card_key": "B:5", "claimed_by": "u1", "claimed_at": "2026-11-17T01:00:00+00:00", "callback_on": "2026-11-18", "do_not_call": False},
            ],
        }

    def select(self, table, columns, **filters):
        return [dict(r) for r in self.tables[table]]


def line(contact, status, in_window=True, first_listed_on="2026-10-01", won_by=None, won_at=None, won_without_call=None):
    return {"id": contact, "contact_id": contact, "status": status, "in_window": in_window, "first_listed_on": first_listed_on,
            "won_by": won_by, "won_at": won_at, "won_without_call": won_without_call}


class Sender:
    def __init__(self, fail_for=()):
        self.sent, self.fail_for = [], set(fail_for)

    def __call__(self, to, subject, text, html):
        if to in self.fail_for:
            raise OSError("SMTP said no")
        self.sent.append((to, subject, text, html))


def test_prior_week_is_the_monday_to_sunday_before_this_week():
    assert mr.prior_week(MON) == (date(2026, 11, 16), date(2026, 11, 22))
    assert mr.prior_week(date(2026, 11, 25)) == (date(2026, 11, 16), date(2026, 11, 22))   # a late run still reports last week


def test_collect_counts_inputs_outputs_and_the_list_now():
    r = mr.collect(FakeClient(), MON)
    assert (r.week_start, r.week_end) == (date(2026, 11, 16), date(2026, 11, 22))
    t = r.team
    assert (t["calls"], t["worked"], t["cards_taken"]) == (3, 6, 2)
    assert (t["won"], t["won_credited"], t["won_without_call"], t["lost"]) == (2, 1, 1, 3)
    assert t["win_rate"] == 0.4
    assert (t["open"], t["not_called"], t["queue_cards"], t["held_cards"], t["new_listed"], t["callbacks_overdue"]) == (4, 3, 1, 2, 2, 1)
    people = {p["name"]: p for p in r.people}
    assert list(people) == ["Al <Brown> & Co", "Jo Smith", "Mel Manager", "Quiet Person"]          # active only, by name
    assert {k: people["Jo Smith"][k] for k in ("cards_taken", "calls", "worked", "won", "lost", "callbacks_overdue")} == \
           dict(cards_taken=1, calls=2, worked=4, won=1, lost=2, callbacks_overdue=1)
    assert round(people["Jo Smith"]["win_rate"], 3) == 0.333
    assert (people["Al <Brown> & Co"]["calls"], people["Al <Brown> & Co"]["worked"], people["Al <Brown> & Co"]["lost"],
            people["Al <Brown> & Co"]["win_rate"]) == (1, 2, 1, 0.0)
    assert {k: people["Quiet Person"][k] for k in ("cards_taken", "calls", "worked", "won", "lost", "win_rate")} == \
           dict(cards_taken=0, calls=0, worked=0, won=0, lost=0, win_rate=None)


def test_render_escapes_names_and_links_to_the_site():
    subject, text, html = mr.render(mr.collect(FakeClient(), MON))
    assert subject == "Refresher calls: team report, Mon 16 Nov – Sun 22 Nov"
    assert "Al <Brown> & Co" in text and "Al &lt;Brown&gt; &amp; Co" in html and "<Brown>" not in html
    assert "Quiet Person" in html and "–" in text                                  # no activity still listed, rate shown as –
    assert config.SITE_URL in text and config.SITE_URL in html
    assert "booked without a call" in text and "40%" in text


def test_sends_to_active_managers_once_a_week(tmp_path):
    marker, sender = tmp_path / "report.txt", Sender()
    first = mr.run_report(FakeClient(), MON, marker, sender)
    assert [s[0] for s in sender.sent] == ["mel@kallibr.com.au"] and "1 sent" in first
    assert marker.read_text().strip() == "2026-11-16"
    second = mr.run_report(FakeClient(), date(2026, 11, 24), marker, sender)
    assert len(sender.sent) == 1 and "already sent" in second


def test_a_missed_monday_sends_later_that_week(tmp_path):
    marker, sender = tmp_path / "report.txt", Sender()
    marker.write_text("2026-11-09")
    mr.run_report(FakeClient(), date(2026, 11, 25), marker, sender)
    assert len(sender.sent) == 1 and marker.read_text().strip() == "2026-11-16"


def test_force_and_only(tmp_path):
    marker, sender = tmp_path / "report.txt", Sender()
    marker.write_text("2026-11-16")
    summary = mr.run_report(FakeClient(), MON, marker, sender, force=True, only="lino@kallibr.com.au")
    assert [s[0] for s in sender.sent] == ["lino@kallibr.com.au"] and "1 sent" in summary
    assert marker.read_text().strip() == "2026-11-16"


def test_a_failed_recipient_is_reported(tmp_path):
    summary = mr.run_report(FakeClient(), MON, tmp_path / "report.txt", Sender(fail_for={"mel@kallibr.com.au"}))
    assert "0 sent" in summary and "1 failed" in summary
    assert not (tmp_path / "report.txt").exists()          # nothing went out: try again on the next run


def test_read_addresses_ignores_notes_blanks_and_case(tmp_path):
    f = tmp_path / "leave_out.txt"
    f.write_text("﻿# not on the stats table\nJO@kallibr.com.au   # manager, doesn't call\n\n al@kallibr.com.au \n",
                 encoding="utf-8")
    assert mr.read_addresses(f) == {"jo@kallibr.com.au", "al@kallibr.com.au"}
    assert mr.read_addresses(tmp_path / "missing.txt") == set() and mr.read_addresses(None) == set()


def test_listed_people_are_left_out_of_the_table_but_not_the_totals():
    r = mr.collect(FakeClient(), MON, leave_out={"jo@kallibr.com.au"})
    assert [p["name"] for p in r.people] == ["Al <Brown> & Co", "Mel Manager", "Quiet Person"]
    assert (r.team["calls"], r.team["won_credited"]) == (3, 1)                  # Jo's calls and win still count


def test_run_report_uses_the_leave_out_list_and_still_sends_to_every_manager(tmp_path):
    f, sender = tmp_path / "leave_out.txt", Sender()
    f.write_text("mel@kallibr.com.au\n", encoding="utf-8")
    mr.run_report(FakeClient(), MON, tmp_path / "report.txt", sender, leave_out_path=f)
    assert [s[0] for s in sender.sent] == ["mel@kallibr.com.au"]                 # off the table, still emailed
    assert "Mel Manager" not in sender.sent[0][2] and "Mel Manager" not in sender.sent[0][3]


def test_a_card_released_without_a_call_is_not_counted_as_taken():
    """Owner's request, 19 Nov 2026: a take released with no call logged (a mis-click) is not a card taken."""
    fc = FakeClient()
    fc.tables["card_events"] += [
        {"card_key": "B:7", "staff_id": "u2", "event": "claimed", "at": "2026-11-20T01:00:00+00:00"},
        {"card_key": "B:7", "staff_id": "u2", "event": "released", "at": "2026-11-20T01:01:00+00:00"},   # no call: a mis-click
        {"card_key": "B:8", "staff_id": "u2", "event": "claimed", "at": "2026-11-17T22:00:00+00:00"},
        {"card_key": "B:8", "staff_id": "u2", "event": "released", "at": "2026-11-18T05:00:00+00:00"},   # called first: counts
        {"card_key": "B:6", "staff_id": "u2", "event": "claimed", "at": "2026-11-17T22:00:00+00:00"},
        {"card_key": "B:6", "staff_id": "u2", "event": "released", "at": "2026-11-18T05:00:00+00:00"},   # only an earlier call
    ]
    fc.tables["call_logs"] += [
        {"id": 6, "staff_id": "u2", "card_key": "B:8", "called_at": "2026-11-18T02:00:00+00:00"},
        {"id": 7, "staff_id": "u2", "card_key": "B:6", "called_at": "2026-11-17T21:00:00+00:00"},       # before the take
    ]
    r = mr.collect(fc, MON)
    assert {p["name"]: p["cards_taken"] for p in r.people}["Al <Brown> & Co"] == 2      # B:2 (held) and B:8 (called)
    assert r.team["cards_taken"] == 3                                                   # B:1, B:2, B:8


def test_done_in_house_counts_as_lost():
    fc = FakeClient()
    fc.tables["line_outcomes"].append({"call_log_id": 5, "outcome": "done_in_house"})
    r = mr.collect(fc, MON)
    assert {p["name"]: p["lost"] for p in r.people}["Al <Brown> & Co"] == 2 and r.team["lost"] == 4


def test_an_update_with_no_call_counts_its_outcomes_but_not_as_a_call():
    """Owner's request, 20 Nov 2026: an outcome recorded from an email reply is not a call."""
    fc = FakeClient()
    fc.tables["card_events"].append(
        {"card_key": "B:3", "staff_id": "u3", "event": "claimed", "at": "2026-11-18T22:00:00+00:00"})
    fc.tables["call_logs"].append(
        {"id": 8, "staff_id": "u3", "card_key": "B:3", "no_call": True, "called_at": "2026-11-19T01:00:00+00:00"})
    fc.tables["line_outcomes"].append({"call_log_id": 8, "outcome": "not_needed"})
    r = mr.collect(fc, MON)
    quiet = {p["name"]: p for p in r.people}["Quiet Person"]
    assert (quiet["calls"], quiet["worked"], quiet["lost"], quiet["cards_taken"]) == (0, 1, 1, 1)
    assert (r.team["calls"], r.team["worked"], r.team["lost"]) == (3, 7, 4)
