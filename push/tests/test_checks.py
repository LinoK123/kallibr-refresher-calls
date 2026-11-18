from datetime import date

import pytest

from fixture import book, comp
from rules import check_lines, course_history

TODAY = date(2026, 11, 18)
K = (1, "Heights", date(2024, 6, 10))


def test_real_later_booking_wins(con):
    book(con, 1, 100889, "2026-12-01", booked_on="2026-11-20", course="WORK SAFELY AT HEIGHTS_Refresher")
    [c] = check_lines(con, [K], TODAY)
    assert (c.won, c.booked_on, c.class_date, c.course_name, c.tentative, c.in_window) == \
           (True, date(2026, 11, 20), date(2026, 12, 1), "WORK SAFELY AT HEIGHTS_Refresher", False, True)


def test_moved_booking_still_wins(con):
    book(con, 1, 100889, "2026-12-01", status="Moved")
    assert check_lines(con, [K], TODAY)[0].won is True


@pytest.mark.parametrize("kw", [dict(status="Cancelled", counted=0), dict(status="Booked", counted=0)])
def test_cancelled_booking_or_class_does_not_win(con, kw):
    book(con, 1, 100889, "2026-12-01", **kw)
    assert check_lines(con, [K], TODAY)[0].won is False


def test_other_type_does_not_win_but_cluster_does(con):
    book(con, 1, 100890, "2026-12-01")
    assert check_lines(con, [K], TODAY)[0].won is False
    book(con, 1, 116646, "2026-12-08")
    assert check_lines(con, [K], TODAY)[0].won is True


def test_booking_on_the_last_done_date_does_not_win(con):
    book(con, 1, 100889, "2024-06-10")
    assert check_lines(con, [K], TODAY)[0].won is False


def test_tentative_flags_without_winning(con):
    book(con, 1, 100889, "2026-12-01", status="Waitlisted", counted=0)
    c = check_lines(con, [K], TODAY)[0]
    assert (c.won, c.tentative) == (False, True)


def test_earliest_class_is_reported(con):
    book(con, 1, 100889, "2027-02-01", booked_on="2026-11-19"); book(con, 1, 100889, "2026-12-01", booked_on="2026-11-25")
    assert check_lines(con, [K], TODAY)[0].class_date == date(2026, 12, 1)


def test_out_of_window(con):
    assert check_lines(con, [(1, "Heights", date(2023, 11, 17))], TODAY)[0].in_window is False


def test_course_history(con):
    comp(con, 1, 100889, "2024-06-10", course="WORK SAFELY AT HEIGHTS"); comp(con, 2, 100889, "2024-06-10")
    assert course_history(con, {1}) == [(1, "WORK SAFELY AT HEIGHTS", date(2024, 6, 10))]
