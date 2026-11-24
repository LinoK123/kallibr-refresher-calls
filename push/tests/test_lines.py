from datetime import date

from fixture import book, comp
from rules import add_months, build_lines

TODAY = date(2026, 11, 18)


def test_add_months_clamps():
    assert add_months(date(2024, 2, 29), 24) == date(2026, 2, 28)


def test_basic_heights_line(con):
    comp(con, 1, 100889, "2024-06-10", name="Sam Lee", course="WORK SAFELY AT HEIGHTS", loc="NSW")
    [l] = build_lines(con, TODAY)
    assert (l.contact_id, l.refresher_type, l.last_done, l.due_date) == (1, "Heights", date(2024, 6, 10), date(2026, 6, 10))
    assert (l.student_name, l.org_name, l.location, l.attendance_confirmed) == ("Sam Lee", "Acme Pty Ltd", "NSW", True)


def test_window_edges(con):
    comp(con, 1, 100889, "2023-11-18")   # exactly 3 years ago: in
    comp(con, 2, 100889, "2023-11-17")   # one day older: out
    comp(con, 3, 100889, "2025-03-18")   # due 2027-03-18 = today + 4 months: in
    comp(con, 4, 100889, "2025-03-19")   # due a day later: out
    assert sorted(l.contact_id for l in build_lines(con, TODAY)) == [1, 3]


def test_latest_completion_decides(con):
    comp(con, 1, 100889, "2024-01-10"); comp(con, 1, 100889, "2025-06-01")
    assert build_lines(con, TODAY) == []


def test_cluster_course_gives_two_lines(con):
    comp(con, 1, 116646, "2024-05-01")
    assert sorted(l.refresher_type for l in build_lines(con, TODAY)) == ["Confined Space", "Heights"]


def test_future_booking_excludes(con):
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2026-12-01", status="Tentative", counted=0)
    comp(con, 2, 100889, "2024-06-10"); book(con, 2, 100889, "2026-12-01", status="Cancelled", counted=0)
    assert [l.contact_id for l in build_lines(con, TODAY)] == [2]


def test_already_rebooked_excludes(con):
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2026-03-01", status="Moved")
    assert build_lines(con, TODAY) == []


def test_hsr_from_booking_is_unconfirmed(con):
    book(con, 2, 100882, "2025-08-04", course="HEALTH AND SAFETY REPRESENTATIVE")
    [l] = build_lines(con, TODAY)
    assert (l.refresher_type, l.due_date, l.attendance_confirmed) == ("HSR", date(2026, 8, 4), False)


def test_hsr_completion_is_confirmed(con):
    book(con, 2, 100882, "2025-08-04"); comp(con, 2, 100882, "2025-08-04")
    assert build_lines(con, TODAY)[0].attendance_confirmed is True


def test_hsr_ignores_cancelled_and_future_classes(con):
    book(con, 2, 100882, "2025-08-04", counted=0)
    book(con, 3, 100882, "2026-11-18")           # starts today: has not "already started"
    assert build_lines(con, TODAY) == []


# Kallibr staff are not students (design 2026-11-23-staff-not-students)

def test_staff_org_student_left_out(con):
    comp(con, 1, 100889, "2024-06-10", org="Kallibr Training")
    comp(con, 2, 100889, "2024-06-10", org="GL Training")
    comp(con, 3, 100889, "2024-06-10", org="Acme Pty Ltd")
    assert [l.contact_id for l in build_lines(con, TODAY)] == [3]


def test_staff_org_case_and_spaces(con):
    comp(con, 1, 100889, "2024-06-10", org="  kallibr training ")
    assert build_lines(con, TODAY) == []


def test_kallibr_mid_name_is_a_customer(con):
    comp(con, 1, 100889, "2024-06-10", org="Acme c/o Kallibr")
    assert [l.contact_id for l in build_lines(con, TODAY)] == [1]


def test_ex_staff_back_on_list_under_new_company(con):
    comp(con, 1, 100889, "2023-06-01", org="Kallibr Training")    # older staff course, out of the 3-year window
    comp(con, 1, 100890, "2024-06-10", org="Acme Pty Ltd")
    [l] = build_lines(con, TODAY)
    assert (l.refresher_type, l.org_name) == ("Confined Space", "Acme Pty Ltd")


def test_newer_staff_course_not_yet_due_drops_student(con):
    comp(con, 1, 100890, "2024-06-10", org="Acme Pty Ltd")        # due June 2026
    comp(con, 1, 100889, "2026-01-15", org="Kallibr Training")    # due 2028: not on the list itself
    assert build_lines(con, TODAY) == []


def test_same_day_staff_event_counts(con):
    comp(con, 1, 100890, "2024-06-10", org="Acme Pty Ltd")
    comp(con, 1, 100889, "2024-06-10", org="Kallibr Training")
    assert build_lines(con, TODAY) == []


def test_ignore_ids_left_out(con):
    comp(con, 1, 100889, "2024-06-10")
    comp(con, 2, 100889, "2024-06-10")
    assert [l.contact_id for l in build_lines(con, TODAY, ignore_ids=(1,))] == [2]
