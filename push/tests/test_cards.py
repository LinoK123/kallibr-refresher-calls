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


# ---- Current booking contact (docs/superpowers/specs/2026-11-18-current-booker-design.md) ----

def place(con, **kw):
    return place_students(con, build_lines(con, TODAY), today=TODAY, **kw)


def due(con, student, booker=None, booker_name=None, loc="QLD", org="Acme Pty Ltd", on="2024-06-10"):
    """A student due a Heights refresher whose last course was booked (or not) by `booker`."""
    comp(con, student, 100889, on, org=org, loc=loc)
    if booker:
        book(con, student, 100889, on, booker=booker, booker_name=booker_name, org=org, loc=loc, booked_on=on)


def recent(con, student, booker, booker_name, loc="QLD", org="Acme Pty Ltd", booked_on="2026-10-01", start="2026-10-20"):
    """A recent booking of any course (555 is not a refresher course) made by `booker` for the company."""
    book(con, student, 555, start, booker=booker, booker_name=booker_name, booked_on=booked_on, org=org, loc=loc)


def test_quiet_booker_is_replaced_by_the_current_booker_for_the_state(con):
    due(con, 1, 900, "Kim Spicer"); recent(con, 50, 901, "Therese Stapleton")
    p = place(con)[1]
    assert (p.card_key, p.kind, p.target_contact_id, p.target_name, p.org_key) == \
           ("B:901", "booker", 901, "Therese Stapleton", "acme pty ltd")


def test_active_booker_keeps_their_students(con):
    due(con, 1, 900, "Kim Spicer"); recent(con, 50, 900, "Kim Spicer")
    recent(con, 51, 901, "Therese Stapleton"); recent(con, 52, 901, "Therese Stapleton")
    assert place(con)[1].card_key == "B:900"


def test_states_booked_by_different_people_become_separate_cards(con):
    due(con, 1, 900, "Kim Spicer", loc="NSW"); due(con, 2, 900, "Kim Spicer", loc="QLD")
    recent(con, 50, 902, "Kavita Dsilva", loc="NSW"); recent(con, 51, 901, "Therese Stapleton", loc="QLD")
    placed = place(con)
    assert (placed[1].card_key, placed[2].card_key) == ("B:902", "B:901")


def test_a_state_with_no_recent_bookings_uses_the_companys_busiest_booker(con):
    due(con, 1, 900, "Kim Spicer", loc="VIC")
    recent(con, 50, 901, "Therese Stapleton", loc="QLD"); recent(con, 51, 901, "Therese Stapleton", loc="QLD")
    recent(con, 52, 902, "Kavita Dsilva", loc="NSW")
    assert place(con)[1].card_key == "B:901"


def test_company_with_no_bookings_for_a_year_keeps_the_first_pass_card(con):
    due(con, 1, 900, "Kim Spicer"); due(con, 2)
    recent(con, 50, 901, "Therese Stapleton", booked_on="2025-10-01", start="2025-10-20")   # 13 months ago
    placed = place(con)
    assert (placed[1].card_key, placed[2].card_key) == ("B:900", "O:acme pty ltd")


def test_organisation_card_students_go_to_the_current_booker(con):
    due(con, 1); recent(con, 50, 901, "Therese Stapleton")
    assert place(con)[1].card_key == "B:901"


def test_self_booker_keeps_their_own_card(con):
    due(con, 1, 1, "Sam Lee"); recent(con, 50, 901, "Therese Stapleton")
    assert place(con)[1].card_key == "S:1"


def test_kallibr_staff_never_become_the_current_booker(con):
    staff_entries(con, "Renee Staff", n=50)
    due(con, 1, 900, "Kim Spicer"); recent(con, 50, 555, "Renee Staff")
    assert place(con)[1].card_key == "B:900"


def test_most_bookings_wins(con):
    due(con, 1, 900, "Kim Spicer")
    recent(con, 50, 901, "Anna", booked_on="2026-10-01"); recent(con, 51, 901, "Anna", booked_on="2026-09-01")
    recent(con, 52, 902, "Ben", booked_on="2026-11-01")
    assert place(con)[1].card_key == "B:901"


def test_a_tie_goes_to_the_latest_booking(con):
    due(con, 1, 900, "Kim Spicer")
    recent(con, 50, 901, "Anna", booked_on="2026-09-01"); recent(con, 51, 902, "Ben", booked_on="2026-11-01")
    assert place(con)[1].card_key == "B:902"


def test_the_12_month_window_uses_the_booked_date(con):
    due(con, 1, 900, "Kim Spicer", loc="QLD"); due(con, 2, 900, "Kim Spicer", loc="NSW"); due(con, 3, 900, "Kim Spicer", loc="VIC", org="Beta Co")
    recent(con, 50, 901, "Therese Stapleton", loc="QLD", booked_on="2026-10-15", start="2027-03-01")   # future class, booked last month: counts
    recent(con, 51, 902, "Kavita Dsilva", loc="NSW", org="Gamma Co", booked_on="2025-10-10", start="2025-12-10")  # booked 13 months ago: doesn't
    recent(con, 52, 903, "Vic Booker", loc="VIC", org="Beta Co", booked_on=None, start="2026-10-01")   # no booked date: class date used
    placed = place(con)
    assert (placed[1].card_key, placed[3].card_key) == ("B:901", "B:903")


def test_current_booker_who_is_also_due_gets_one_card(con):
    due(con, 1, 900, "Kim Spicer"); due(con, 901); recent(con, 50, 901, "Therese Stapleton")
    placed = place(con)
    assert placed[1].card_key == placed[901].card_key == "B:901"
    assert placed[901].target_name == "Therese Stapleton"


def test_active_booker_keeps_only_students_in_states_they_still_book_for(con):
    due(con, 1, 901, "Therese Stapleton", loc="NSW"); due(con, 2, 901, "Therese Stapleton", loc="QLD")
    recent(con, 50, 901, "Therese Stapleton", loc="QLD"); recent(con, 51, 902, "Kavita Dsilva", loc="NSW")
    placed = place(con)
    assert (placed[1].card_key, placed[2].card_key) == ("B:902", "B:901")


def test_active_booker_keeps_a_student_in_a_state_nobody_books_for_now(con):
    due(con, 1, 901, "Therese Stapleton", loc="VIC")
    recent(con, 50, 901, "Therese Stapleton", loc="QLD")
    recent(con, 51, 902, "Kavita Dsilva", loc="NSW"); recent(con, 52, 902, "Kavita Dsilva", loc="NSW")   # busier overall
    assert place(con)[1].card_key == "B:901"
