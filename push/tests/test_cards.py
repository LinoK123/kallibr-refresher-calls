from datetime import date

import pytest

from fixture import book, comp, staff_entries
from rules import build_lines, place_students

TODAY = date(2026, 11, 18)


def test_booker_card(con):
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2024-06-10", booker=900, booker_name="Pat Booker")
    p = place_students(con, build_lines(con, TODAY))[1]
    assert (p.card_key, p.kind, p.target_contact_id, p.target_name, p.org_key) == ("B:900", "booker", 900, "Pat Booker", "acme pty ltd")


def test_self_booker_is_individual(con):
    comp(con, 1, 100889, "2024-06-10", name="Sam Lee"); book(con, 1, 100889, "2024-06-10", booker=1, booker_name="Sam Lee", name="Sam Lee")
    p = place_students(con, build_lines(con, TODAY))[1]
    assert (p.card_key, p.kind, p.target_contact_id, p.target_name) == ("S:1", "individual", 1, "Sam Lee")


def test_no_booking_groups_by_organisation(con):
    comp(con, 1, 100889, "2023-12-01", org=" Acme Pty Ltd ")
    p = place_students(con, build_lines(con, TODAY))[1]
    assert (p.card_key, p.kind, p.target_contact_id, p.target_name) == ("O:acme pty ltd", "organisation", None, "Acme Pty Ltd")


@pytest.mark.parametrize("org", ["Cash - Individual Participants", "", None])
def test_no_booking_no_real_org_is_individual(con, org):
    comp(con, 1, 100889, "2023-12-01", org=org)
    assert place_students(con, build_lines(con, TODAY))[1].card_key == "S:1"


def test_one_card_per_student_uses_most_recent_course(con):
    comp(con, 1, 100890, "2024-02-05"); book(con, 1, 100890, "2024-02-05", booker=900, booker_name="Pat Booker")
    comp(con, 1, 100889, "2024-03-07"); book(con, 1, 100889, "2024-03-07", booker=901, booker_name="Kim Other")
    assert place_students(con, build_lines(con, TODAY))[1].card_key == "B:901"


def test_booker_who_is_also_a_student_gets_one_card(con):
    comp(con, 900, 100889, "2024-06-10"); book(con, 900, 100889, "2024-06-10", booker=900, booker_name="Pat Booker")
    comp(con, 1, 100889, "2024-06-11");   book(con, 1, 100889, "2024-06-11", booker=900, booker_name="Pat Booker")
    placed = place_students(con, build_lines(con, TODAY))
    assert placed[900].card_key == placed[1].card_key == "B:900"


def test_staff_requester_falls_back_to_organisation(con):
    staff_entries(con, "Renee Staff", n=50)
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2024-06-10", booker=555, booker_name="Renee Staff")
    assert place_students(con, build_lines(con, TODAY))[1].card_key == "O:acme pty ltd"


def test_ignore_list_falls_back(con):
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2024-06-10", booker=900, booker_name="Pat Booker")
    assert place_students(con, build_lines(con, TODAY), ignore_ids=(900,))[1].card_key == "O:acme pty ltd"


def test_moved_booking_supplies_the_booker(con):
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2024-06-10", status="Moved", booker=900, booker_name="Pat Booker")
    assert place_students(con, build_lines(con, TODAY))[1].card_key == "B:900"


def test_cancelled_booking_does_not_supply_the_booker(con):
    comp(con, 1, 100889, "2024-06-10"); book(con, 1, 100889, "2024-06-10", status="Cancelled", counted=0, booker=900, booker_name="Pat Booker")
    assert place_students(con, build_lines(con, TODAY))[1].card_key == "O:acme pty ltd"
