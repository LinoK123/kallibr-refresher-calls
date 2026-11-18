# Kallibr Refresher Call Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A shared call list for Kallibr staff to ring bookers about overdue and upcoming confined space, heights and HSR refreshers, with automatic win detection and a progress dashboard.

**Architecture:** A nightly Python script on one Kallibr PC reads the local `axc_agent.db`, works out refresher lines and cards, uploads them to staging tables in Supabase, and calls one Postgres function that merges them in a single transaction. Staff use a single-file site on GitHub Pages that reads through row-level security and writes only through Postgres functions.

**Tech Stack:** Python 3 (`sqlite3`, `requests`, `keyring`, `tzdata`, `pytest`, `psycopg`), Supabase (Postgres, Auth, PostgREST), one `index.html` (vanilla JS, supabase-js v2 from CDN, Chart.js 4.4.1), Node's built-in test runner for the page logic.

**Execution method (chosen by the owner, 18 November 2026):** one session. Implement every task in order in a single session (superpowers:executing-plans if available), stopping at the owner-only steps, then have one fresh reviewer check the whole branch against the spec and this plan before Task 12 goes live.

**Spec:** `docs/superpowers/specs/2026-11-18-refresher-call-tool-design.md`. Read it first. Section numbers below (5.2, 5.3 ...) refer to it.

## Global Constraints

- Never write to aXcelerate. Source is `axc_agent.db` in `%USERPROFILE%\KallibrAgent`, read-only.
- Never store or display phone numbers, emails (other than staff sign-in emails), addresses, dates of birth, USIs, payment or invoice details.
- Held personal data is limited to: student name, booker name, organisation name, contact IDs, course names and dates.
- Profile link: `https://kallibr.app.axcelerate.com/management/management2/contact_view.cfm?contactID=<contact ID>`, opened in a new tab.
- Join courses on `course_type_id` through `course_refresher_groups`, never on course names or the `refresher_group` text.
- Refresher types are exactly `Confined Space`, `Heights`, `HSR`. Intervals: 24, 24, 12 months. HSR course type IDs: 100882, 101060, 114315.
- "Real booking" = `v_bookings.counted = 1` (Approved, Booked, Completed, Moved, Replaced on a non-cancelled class).
- All "today", week and month boundaries use Australia/Sydney.
- Only the designated PC pushes. The push is off unless a local setting exists; nothing in the distributed KallibrAgent package enables it.
- The service (secret) key lives only in Windows Credential Manager (`keyring`). It never appears in the repository, the page, logs or chat. The page carries only the publishable (anon) key.
- The push never deletes call logs, outcomes or claims.
- Site: one `index.html` with CSS and JS inline, built from `design-kit/starter-template.html`; tokens and classes from `design-kit/kallibr-theme.css`; fonts DM Serif Display + DM Sans; emoji as icons; Australian English; no other font families or icon libraries; no dark mode.
- Every string that came from the database is written to the page with `textContent` or through `RC.esc`. Never interpolate data into `innerHTML` unescaped.
- Supabase project region: Sydney (`ap-southeast-2`).
- Check Supabase API details (key names, `auth.jwt()` claims, supabase-js sign-in calls, connection strings) against the current Supabase docs before relying on them; this plan names the intent.

## Review Focus

1. **Stale page vs overnight win:** a staff member saves an outcome for a line that became Won since their page loaded. Expected: the win is kept, the other lines save, and the page says which line was skipped. (Test in Task 5.)
2. **Interrupted push:** the upload drops partway through staging. Expected: nothing visible changes, the run is recorded as failed, and the next night's run works. (Tests in Tasks 6 and 7.)
3. **Sydney date boundaries:** a call logged at 9:30 am Sydney is "that day" even though it is the previous day in UTC. Expected: win credit and "call-backs due today" use the Sydney date. (Tests in Tasks 6 and 9.)
4. **Names and notes containing HTML or quotes** (`O'Brien & Sons <Pty>`, a note with `<script>`). Expected: shown as plain text, never executed, and saved intact. (Tests in Tasks 9 and 10.)
5. **Deactivated staff with a live session.** Expected: they see nothing on their next request and their claimed cards return to the queue. (Test in Task 5.)

---

## Before starting (owner does these by hand)

- [ ] Create two Supabase projects in the Sydney region: `kallibr-refresher` (live) and `kallibr-refresher-test`. Free plan allows two.
- [ ] Create an empty GitHub repository `kallibr-refresher-calls` (public, required for Pages on a free plan).
- [ ] Have ready, but do not paste into chat or files: each project's URL, publishable key, secret key, and the test project's Postgres connection string (session pooler, IPv4).

## File structure

```
index.html                                  the site (GitHub Pages root)
design-kit/                                 copy of the three Kallibr Design Kit files (reference only)
push/config.py                              intervals, HSR IDs, thresholds
push/rules.py                               pure rules: lines, placement, checks, course history (reads SQLite only)
push/supabase_client.py                     thin PostgREST client (requests)
push/refresher_push.py                      CLI: safety stops, staging upload, apply
push/kallibragent/axc_refresher_hook.py     copied into KallibrAgent; runs the push after the nightly sync if enabled
push/requirements.txt
push/tests/fixture.py                       builds a small SQLite database shaped like axc_agent.db
push/tests/test_lines.py  test_cards.py  test_checks.py  test_push.py  test_hook.py
supabase/migrations/0001_schema.sql         tables, staging tables
supabase/migrations/0002_access.sql         helper functions, grants, row-level security
supabase/migrations/0003_staff_actions.sql  claim, release, assign, save_call_log, do-not-call, staff admin
supabase/migrations/0004_apply_push.sql     apply_push
supabase/migrations/0005_reporting.sql      v_cards, team_stats, cohort_counts
supabase/reset.sql                          drops everything the migrations create (test use only)
supabase/tests/conftest.py                  applies migrations to the test project; role helpers
supabase/tests/test_access.py  test_staff_actions.py  test_apply_push.py  test_reporting.py
tests/site/logic.test.mjs                   Node tests for the page's pure functions
README.md                                   runbook
```

Test commands used throughout:

- Rules and push: `py -m pytest push/tests -v`
- Database: `set REFRESHER_TEST_DB_URL=<test project connection string>` then `py -m pytest supabase/tests -v`
- Page logic: `node --test tests/site`

---

### Task 1: Lines (who is due)

**Files:**
- Create: `push/config.py`, `push/rules.py`, `push/requirements.txt`, `push/tests/fixture.py`, `push/tests/conftest.py` (a `con` fixture returning `make_db(tmp_path / "t.db")`), `push/tests/test_lines.py`, `.gitignore`, `README.md` (title and one paragraph only)
- Already in the project folder: `docs/` (spec and this plan) and `design-kit/` (the three Kallibr Design Kit files)

**Interfaces:**
- Produces:
  - `config`: `INTERVAL_MONTHS = {"Confined Space": 24, "Heights": 24, "HSR": 12}`, `HSR_COURSE_TYPE_IDS = (100882, 101060, 114315)`, `LOOKBACK_YEARS = 3`, `LOOKAHEAD_MONTHS = 4`, `FUTURE_BOOKING_STATUSES = ("Approved","Booked","Moved","Replaced","Tentative","Waitlisted")`, `TENTATIVE_STATUSES = ("Tentative","Waitlisted")`, `INDIVIDUAL_ORG_PREFIX = "Cash - Individual"`, `STAFF_ENTERED_MIN = 50`, `IGNORE_BOOKER_CONTACT_IDS = ()`, `MAX_SOURCE_AGE_HOURS = 36`, `MAX_LINE_DROP = 0.20`, `CHUNK = 500`
  - `rules.add_months(d: date, months: int) -> date` (clamps to month end)
  - `rules.type_map(con) -> dict[int, set[str]]` (course_type_id → refresher types, HSR IDs included)
  - `rules.Line` frozen dataclass: `contact_id:int, refresher_type:str, last_done:date, due_date:date, course_type_id:int, course_name:str, location:str|None, attendance_confirmed:bool, student_name:str, org_name:str|None`
  - `rules.build_lines(con: sqlite3.Connection, today: date) -> list[Line]`
  - `fixture.make_db(path) -> sqlite3.Connection`, `fixture.comp(con, contact, ct, on, org="Acme Pty Ltd", name=None, loc="QLD", course="Course")`, `fixture.book(con, contact, ct, start, status="Booked", counted=1, booker=None, booker_name=None, entered_by="Admin Person", booked_on=None, org="Acme Pty Ltd", name=None, loc="QLD", course="Course")`, `fixture.staff_entries(con, name, n=50)`, `fixture.set_synced(con, when: datetime)`

`make_db` creates plain tables with the column names the rules read, so tests do not need the real views: `course_refresher_groups(course_type_id, refresher_group)` seeded with `(100889,'Heights'), (100890,'Confined Space'), (116646,'Confined Space'), (116646,'Heights')`; `v_completions(contact_id, student, organisation, course_type_id, course_name, completed_on, location)`; `v_bookings(booking_id, contact_id, student, organisation, class_id, course_type_id, course, location, start_date, booking_status, booked_on, counted)`; `bookings(statusid, contactid, pdataid, whobyid, workshopbookingrequestedbyfullname, bookedstatusenteredbyfullname)`; `sync_log(synced_at, table_name, row_count)`. `book` writes one row to both `v_bookings` and `bookings` with matching `booking_id`/`statusid`, `contact_id`/`contactid`, `class_id`/`pdataid`. `name` defaults to `f"Student {contact}"`.

- [ ] **Step 0: Set up the repository.** In the project folder run `git init -b main`, add the GitHub repository as `origin`, run `py -m pip install -r push/requirements.txt` once `requirements.txt` exists, and confirm `py --version`, `git --version` and `node --version` all answer. `.gitignore`: `__pycache__/`, `.pytest_cache/`, `*.db`, `*.bak`, `.env`, `refresher_push.json`.
- [ ] **Step 1: Write the failing tests** in `push/tests/test_lines.py`. `TODAY = date(2026, 11, 18)`; each test gets its own empty database from the `con` fixture.

```python
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
```

- [ ] **Step 2: Run** `py -m pytest push/tests/test_lines.py -v`. Expected: FAIL (import errors).
- [ ] **Step 3: Implement** `config.py`, `fixture.py`, then `add_months`, `type_map`, `build_lines` in `rules.py`, following spec 5.2. Done events: completions for all three types; plus, for HSR only, real bookings with `start_date < today`. `attendance_confirmed` is False only when the latest done event for an HSR line has no completion on that date. The line's `course_type_id`, `course_name`, `location`, `student_name`, `org_name` come from the latest done event. Load the tables into memory once and group in Python (the views are slow under correlated subqueries). `requirements.txt`: `requests`, `keyring`, `tzdata`, `pytest`, `psycopg[binary]`.
- [ ] **Step 4: Run** the same command. Expected: 10 passed.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: refresher lines rule"`

### Task 2: Cards (who gets called)

**Files:**
- Modify: `push/rules.py`
- Test: `push/tests/test_cards.py`

**Interfaces:**
- Consumes: `Line`, `fixture.*` from Task 1
- Produces:
  - `rules.Placement` frozen dataclass: `contact_id:int, card_key:str, kind:str, target_contact_id:int|None, target_name:str, org_name:str|None, org_key:str|None`. `kind` ∈ `booker`, `organisation`, `individual`. `card_key` is `B:<booker contact id>`, `O:<org_key>` or `S:<student contact id>`. `org_key = org_name.strip().lower()` or None.
  - `rules.place_students(con, lines: list[Line], ignore_ids: tuple[int, ...] = ()) -> dict[int, Placement]` (keyed by student contact ID; one entry per student in `lines`)

- [ ] **Step 1: Write the failing tests.** Every student below also gets a matching `comp` so they have a line; `lines = build_lines(con, TODAY)`.

```python
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
```

- [ ] **Step 2: Run** `py -m pytest push/tests/test_cards.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `place_students`** per spec 5.3. For each student take the line with the latest `last_done`; find real bookings matching `(contact_id, course_type_id, start_date == last_done)`; the booker is `bookings.whobyid` and the booker name is `workshopbookingrequestedbyfullname`, joined on `statusid = booking_id`. A requester is staff when their name is entered-by on at least `STAFF_ENTERED_MIN` bookings or their ID is in `ignore_ids`. Apply the "booker who is also a student" merge after all students have a first-pass result.
- [ ] **Step 4: Run.** Expected: 12 passed (parametrised test counts as 3).
- [ ] **Step 5: Commit** `git commit -am "feat: card placement rule"`

### Task 3: Checks (won, tentative, in window) and course history

**Files:**
- Modify: `push/rules.py`
- Test: `push/tests/test_checks.py`

**Interfaces:**
- Produces:
  - `rules.LineCheck` frozen dataclass: `contact_id:int, refresher_type:str, last_done:date, in_window:bool, won:bool, booked_on:date|None, class_date:date|None, course_name:str|None, tentative:bool`
  - `rules.check_lines(con, keys: list[tuple[int, str, date]], today: date) -> list[LineCheck]` (one result per key, same order)
  - `rules.course_history(con, contact_ids: set[int]) -> list[tuple[int, str, date]]` (contact_id, course_name, completed_on) from `v_completions`, distinct

- [ ] **Step 1: Write the failing tests.** `K = (1, "Heights", date(2024, 6, 10))`.

```python
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
```

- [ ] **Step 2: Run** `py -m pytest push/tests/test_checks.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** per spec 5.5. `won` = a real booking for the contact on a course of that type with `start_date > last_done`; report the earliest such class. `tentative` = a booking with status in `TENTATIVE_STATUSES`, `start_date >= today` and `start_date > last_done`. `in_window` = `last_done >= today − 3 years`.
- [ ] **Step 4: Run** `py -m pytest push/tests -v`. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "feat: win and window checks"`

### Task 4: Database tables and access rules

**Files:**
- Create: `supabase/migrations/0001_schema.sql`, `supabase/migrations/0002_access.sql`, `supabase/reset.sql`, `supabase/tests/conftest.py`, `supabase/tests/test_access.py`

**Interfaces:**
- Produces (all in schema `public`):

```
staff(id uuid pk default gen_random_uuid(), email text unique not null (stored lower-case), full_name text not null,
      role text not null check (role in ('staff','manager')), active boolean not null default true)
cards(card_key text pk, kind text check (kind in ('booker','organisation','individual')), target_contact_id bigint,
      target_name text not null, org_name text, org_key text, claimed_by uuid references staff, claimed_at timestamptz,
      last_activity_at timestamptz, callback_on date, do_not_call boolean not null default false)
students(contact_id bigint pk, full_name text not null, org_name text, card_key text not null references cards)
lines(id bigserial pk, contact_id bigint not null references students, refresher_type text not null
        check (refresher_type in ('Confined Space','Heights','HSR')),
      last_done date not null, due_date date not null, course_name text, location text,
      attendance_confirmed boolean not null default true, in_window boolean not null default true,
      tentative boolean not null default false, first_listed_on date not null,
      status text not null default 'not_called' check (status in ('not_called','pending','won','lost')),
      outcome text, last_outcome_by uuid references staff, last_outcome_at timestamptz,
      status_before_won text, outcome_before_won text,
      won_at date, won_booked_on date, won_class_date date, won_course text,
      won_by uuid references staff, won_without_call boolean,
      unique (contact_id, refresher_type, last_done))
course_history(contact_id bigint, course_name text, completed_on date, primary key (contact_id, course_name, completed_on))
call_logs(id bigserial pk, card_key text not null references cards, staff_id uuid not null references staff,
          called_at timestamptz not null default now(), notes text, callback_on date)
line_outcomes(id bigserial pk, call_log_id bigint not null references call_logs, line_id bigint not null references lines,
              outcome text not null)
card_events(id bigserial pk, card_key text not null, staff_id uuid, event text not null
              check (event in ('claimed','released','assigned','auto_released')), at timestamptz not null default now())
sync_runs(id bigserial pk, started_at timestamptz not null default now(), finished_at timestamptz, source_synced_at timestamptz,
          result text not null default 'running' check (result in ('running','ok','aborted','failed')), message text,
          lines_pushed int, students_pushed int, checks_pushed int, history_pushed int, wins int, reversals int)
stage_students(run_id bigint, contact_id bigint, full_name text, org_name text, card_key text, card_kind text,
               target_contact_id bigint, target_name text, card_org_name text, card_org_key text)
stage_lines(run_id bigint, contact_id bigint, refresher_type text, last_done date, due_date date, course_name text,
            location text, attendance_confirmed boolean)
stage_checks(run_id bigint, contact_id bigint, refresher_type text, last_done date, in_window boolean, won boolean,
             booked_on date, class_date date, course_name text, tentative boolean)
stage_history(run_id bigint, contact_id bigint, course_name text, completed_on date)
```

  - `outcome_status(p_outcome text) returns text` immutable: `no_answer`, `call_back`, `info_sent`, `will_book` → `pending`; `not_needed`, `went_elsewhere`, `left_company`, `do_not_call` → `lost`; anything else raises.
  - `sydney_today() returns date` = `(now() at time zone 'Australia/Sydney')::date`
  - `current_staff_id() returns uuid` security definer: the `staff.id` whose `email` equals the lower-cased `email` claim of the request JWT and `active`; else null.
  - `is_staff() returns boolean` = `current_staff_id() is not null`; `is_manager() returns boolean`.
  - **Explicit grants, in the same migration.** Do not rely on Supabase exposing new tables or functions automatically; newer projects may not, and the result must be the same whichever project settings the owner chose. `grant select` on the nine readable tables to `authenticated`. `grant select, insert, update, delete` on every table (staging included) and `usage, select` on every sequence to `service_role`. For every function in migrations 0002–0005: `revoke execute ... from public`, then grant execute only to the role named for it (`authenticated` for staff actions and reporting, `service_role` for `apply_push`). Nothing is granted to `anon`.
  - Every table gets an explicit `alter table ... enable row level security` in the migration, whether or not the project has automatic RLS switched on.
  - Row-level security enabled on every table above. `select` policy `to authenticated using (is_staff())` on `staff, cards, students, lines, course_history, call_logs, line_outcomes, card_events, sync_runs`. No policies at all on the `stage_*` tables. No insert, update or delete policies for `authenticated` or `anon` anywhere. Revoke all on all tables from `anon`.
  - `conftest.py`: session fixture applies `reset.sql` then every migration in order to `REFRESHER_TEST_DB_URL`; function fixture `cur` yields a cursor in a transaction that is rolled back; helpers `as_user(cur, email)` (sets role `authenticated` and the JWT claims for that email), `as_anon(cur)`, `as_service(cur)` (role `service_role`), `add_staff(cur, email, role="staff", active=True) -> uuid`, `seed_card(cur, card_key="B:900", students=((1, "Sam Lee"),), lines=((1, "Heights", "2024-06-10"),)) -> dict` returning line IDs keyed by `(contact_id, type)`.

- [ ] **Step 1: Write the failing tests** in `test_access.py`.

```python
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
```

- [ ] **Step 2: Run** `py -m pytest supabase/tests/test_access.py -v`. Expected: FAIL (tables missing).
- [ ] **Step 3: Write** `0001_schema.sql`, `0002_access.sql`, `reset.sql` and `conftest.py` to the interfaces above. Add indexes on `students(card_key)`, `lines(contact_id)`, `lines(status)`, `call_logs(card_key)`, `line_outcomes(line_id)`, `cards(org_key)`, `cards(claimed_by)`.
- [ ] **Step 4: Run.** Expected: all pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: schema and access rules"`

### Task 5: Staff actions

**Files:**
- Create: `supabase/migrations/0003_staff_actions.sql`, `supabase/tests/test_staff_actions.py`
- Modify: `supabase/reset.sql`

**Interfaces:**
- Consumes: Task 4 tables and helpers
- Produces (all `security definer`, `set search_path = public`, executable by `authenticated` only, each raising `not staff` unless `is_staff()`):
  - `claim_card(p_card_key text) returns boolean`: true if the card was unclaimed, not `do_not_call`, and is now claimed by the caller. Writes a `claimed` event.
  - `release_card(p_card_key text) returns void`: caller must own the card or be a manager. Writes `released`.
  - `assign_card(p_card_key text, p_staff_id uuid) returns void`: manager only; `p_staff_id` null unassigns. Writes `assigned` with the new owner's ID.
  - `save_call_log(p_card_key text, p_notes text, p_callback_on date, p_outcomes jsonb, p_dnc_card boolean default false) returns jsonb`: `p_outcomes` is `[{"line_id": 12, "outcome": "will_book"}, ...]`. Returns `{"call_log_id": n, "skipped_line_ids": [..]}`.
  - `clear_do_not_call(p_card_key text) returns void`: manager only.
  - `upsert_staff(p_email text, p_full_name text, p_role text, p_active boolean) returns uuid`: manager only.

`save_call_log` rules, in order:
1. Caller must be the card's `claimed_by`, or a manager. Otherwise raise `card not claimed by you`.
2. `p_outcomes` must not be empty; every `line_id` must belong to a student on this card, else raise `line not on this card`.
3. If any outcome is `call_back`, `p_callback_on` must be set and not before `sydney_today()`, else raise `call-back date required`.
4. Insert one `call_logs` row. For each outcome whose line is currently `won`: add the line ID to `skipped_line_ids` and do nothing else. For the rest: insert a `line_outcomes` row and set the line's `status = outcome_status(outcome)`, `outcome`, `last_outcome_by`, `last_outcome_at = now()`.
5. Set the card's `callback_on = p_callback_on` and `last_activity_at = now()`.
6. If `p_dnc_card`: set `do_not_call = true`, set every `not_called` or `pending` line on the card to `lost` / `do_not_call` (with a `line_outcomes` row each), clear `claimed_by` and `callback_on`.

`clear_do_not_call`: set `do_not_call = false`; every line on the card with `outcome = 'do_not_call'` and status `lost` returns to `not_called` with `outcome` null.

`upsert_staff`: insert or update by lower-cased email. When `p_active` is false, release every card that person holds (event `released`).

- [ ] **Step 1: Write the failing tests.** A module fixture adds staff `JO` and `AL` and manager `MEL`, and calls `seed_card(cur, "B:900", students=((1, "Sam Lee"), (2, "Kim Tran")), lines=((1, "Heights", "2024-06-10"), (1, "Confined Space", "2024-02-05"), (2, "Heights", "2025-01-10")))`, binding the three line IDs to `h`, `c` and `h2`. The simultaneous-claim test needs committed rows, so `run_concurrently` creates card `B:901` and the two staff on its own connection and deletes them afterwards.

```python
def test_claim_is_exclusive(cur):
    as_user(cur, JO); cur.execute("select claim_card('B:900')"); assert cur.fetchone()[0] is True
    as_user(cur, AL); cur.execute("select claim_card('B:900')"); assert cur.fetchone()[0] is False

def test_simultaneous_claims_give_one_winner(db_url):
    # two separate connections, both inside open transactions; the second blocks until the first commits
    results = run_concurrently(db_url, [(JO, "select claim_card('B:901')"), (AL, "select claim_card('B:901')")])
    assert sorted(results) == [False, True]

def test_only_owner_or_manager_releases(cur):
    claim(cur, JO)
    as_user(cur, AL)
    with pytest.raises(psycopg.Error): cur.execute("select release_card('B:900')")

def test_assign_is_manager_only(cur): ...   # AL raises; MEL assigns to AL; cards.claimed_by == AL's id; event 'assigned'

def test_save_sets_each_line_separately(cur):
    claim(cur, JO)
    out = save(cur, JO, [(h, "will_book"), (c, "not_needed")], notes="spoke to Pat")
    assert out["skipped_line_ids"] == []
    assert line(cur, h)[:2] == ("pending", "will_book") and line(cur, c)[:2] == ("lost", "not_needed")
    assert line(cur, h2)[:2] == ("not_called", None)

def test_save_requires_claim(cur): ...               # AL saving on JO's card raises 'card not claimed by you'
def test_line_from_another_card_is_rejected(cur): ...  # raises 'line not on this card'; no call_logs row created
def test_call_back_needs_a_date_not_in_the_past(cur): ...  # None raises; yesterday raises; today is accepted and cards.callback_on is set

def test_won_line_is_skipped_not_overwritten(cur):          # Review Focus 1
    claim(cur, JO); as_service(cur); cur.execute("update lines set status='won', won_at=current_date where id=%s", (h,))
    out = save(cur, JO, [(h, "not_needed"), (c, "will_book")])
    assert out["skipped_line_ids"] == [h]
    assert line(cur, h)[0] == "won" and line(cur, c)[0] == "pending"

def test_notes_are_stored_verbatim(cur):                     # Review Focus 4
    claim(cur, JO); out = save(cur, JO, [(h, "no_answer")], notes="<script>alert(1)</script> O'Brien & Sons")
    assert call_log(cur, out["call_log_id"]).notes == "<script>alert(1)</script> O'Brien & Sons"

def test_do_not_call_whole_card(cur):
    claim(cur, JO); save(cur, JO, [(h, "do_not_call")], dnc_card=True)
    assert [line(cur, x)[:2] for x in (h, c, h2)] == [("lost", "do_not_call")] * 3
    assert card(cur, "B:900") == dict(do_not_call=True, claimed_by=None, callback_on=None)
    as_user(cur, AL); cur.execute("select claim_card('B:900')"); assert cur.fetchone()[0] is False

def test_clear_do_not_call_is_manager_only_and_restores(cur): ...  # JO raises; MEL clears; all three lines back to ('not_called', None)

def test_deactivating_staff_releases_cards_and_blocks_reads(cur):   # Review Focus 5
    claim(cur, JO); as_user(cur, MEL); cur.execute("select upsert_staff(%s, 'Jo', 'staff', false)", (JO,))
    assert card(cur, "B:900")["claimed_by"] is None
    as_user(cur, JO); cur.execute("select count(*) from students"); assert cur.fetchone()[0] == 0
```

Write the `...` tests out in full with the assertions named in their comments; `claim`, `save`, `line`, `card`, `call_log`, `run_concurrently` are small helpers added to `conftest.py`.

- [ ] **Step 2: Run** `py -m pytest supabase/tests/test_staff_actions.py -v`. Expected: FAIL.
- [ ] **Step 3: Write** `0003_staff_actions.sql`. `claim_card` is a single `update ... where card_key = p_card_key and claimed_by is null and not do_not_call` and returns `found`.
- [ ] **Step 4: Run** `py -m pytest supabase/tests -v`. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "feat: claim, call log and do-not-call actions"`

### Task 6: Nightly merge (`apply_push`)

**Files:**
- Create: `supabase/migrations/0004_apply_push.sql`, `supabase/tests/test_apply_push.py`
- Modify: `supabase/reset.sql`, `supabase/tests/conftest.py`

**Interfaces:**
- Consumes: staging tables (Task 4), `sydney_today()`
- Produces: `apply_push(p_run_id bigint) returns jsonb`, `security definer`, executable by `service_role` only. Returns `{"lines_new": n, "wins": n, "reversals": n, "released": n}`. The whole function is one transaction: any error leaves live tables untouched.
- `conftest.py` gains `stage(cur, students=[...], lines=[...], checks=[...], history=[...]) -> run_id`, which inserts a `sync_runs` row with the matching expected counts and the staging rows.

Algorithm, in this order:
1. Load the `sync_runs` row; raise `run not found or not running` unless `result = 'running'`. Raise `staging incomplete` unless the row counts in the four staging tables for this run equal `students_pushed`, `lines_pushed`, `checks_pushed`, `history_pushed`.
2. **Cards:** insert each distinct staged card that does not exist; for existing cards update only `target_name`, `org_name`, `org_key`.
3. **Students:** insert new students with the staged `card_key`. For existing students update `full_name`, `org_name`; change `card_key` only if the student has no `line_outcomes` rows on any of their lines (sticky placement, spec 5.3).
4. **Lines:** insert staged lines that do not exist (`status 'not_called'`, `first_listed_on = sydney_today()`); for existing lines update `due_date`, `course_name`, `location`, `attendance_confirmed` only.
5. **Do not call:** every `not_called` line whose student's card has `do_not_call` becomes `lost` / `do_not_call` (no `line_outcomes` row, `last_outcome_by` null).
6. **Checks:** for each staged check that matches a line: set `in_window`, `tentative`. Then:
   - check won, line not won → save `status_before_won`, `outcome_before_won`; set `status 'won'`, `won_at = sydney_today()`, `won_booked_on = coalesce(booked_on, sydney_today())`, `won_class_date`, `won_course`; `won_by` = `staff_id` of the latest `call_logs` row on the student's card whose `(called_at at time zone 'Australia/Sydney')::date <= won_booked_on`; `won_without_call = (won_by is null)`.
   - check not won, line won → restore `status`, `outcome` from the saved values and null every `won_*` and `*_before_won` column.
   - Lines with no staged check are left alone.
7. **Auto-release:** cards with `claimed_by` set, `last_activity_at < now() - interval '14 days'` and (`callback_on` is null or `callback_on < sydney_today()`) are released with an `auto_released` event.
8. **Course history:** delete rows for every staged `contact_id`, then insert the staged rows.
9. Update the run: `finished_at`, `result 'ok'`, `wins`, `reversals`. Delete staging rows where `run_id <= p_run_id`. Mark any older run still `running` as `failed` with message `superseded`.

- [ ] **Step 1: Write the failing tests** (each begins `as_service(cur)`):

```python
def test_first_push_creates_cards_students_lines(cur): ...
    # stage 1 booker card, 2 students, 3 lines → counts 1/2/3; all lines ('not_called', in_window True); result lines_new == 3; run result 'ok'; staging tables empty
def test_running_twice_changes_nothing(cur): ...           # second identical run: lines_new == 0, same row counts
def test_incomplete_staging_raises_and_changes_nothing(cur):   # Review Focus 2
    run = stage(cur, students=S, lines=L); cur.execute("delete from stage_lines where run_id=%s and contact_id=1", (run,))
    with pytest.raises(psycopg.Error, match="staging incomplete"): cur.execute("select apply_push(%s)", (run,))
    # after rollback to savepoint: select count(*) from lines == 0
def test_student_with_calls_stays_on_their_card(cur): ...  # log a call on B:900, restage student onto B:901 → still B:900
def test_student_without_calls_moves(cur): ...             # no call → card_key becomes B:901
def test_new_line_on_do_not_call_card_is_lost(cur): ...    # ('lost','do_not_call'); not in queue; clear_do_not_call returns it to not_called
def test_win_credits_last_caller_before_booking(cur):
    # JO logs a call on 2026-11-17 10:00 Sydney, AL on 2026-11-21 10:00 Sydney; check won with booked_on 2026-11-20
    assert won(cur, h) == dict(status="won", won_by=JO_ID, won_without_call=False, won_booked_on=date(2026, 11, 20))
def test_win_without_any_earlier_call(cur): ...            # won_by None, won_without_call True
def test_win_credit_uses_sydney_date(cur):                 # Review Focus 3
    # call logged at 2026-11-19 22:30 UTC = 20 Nov 09:30 Sydney; booked_on 2026-11-19 → not credited
    assert won(cur, h)["won_without_call"] is True
def test_reversal_restores_previous_status(cur): ...       # pending/will_book → won → check won False → pending/will_book, won_* all null
def test_still_won_while_any_real_booking_remains(cur): ...  # second run with won True and a different class_date: status stays 'won', won_by unchanged
def test_line_without_a_check_is_untouched(cur): ...
def test_out_of_window_and_tentative_flags(cur): ...
def test_auto_release_after_14_days(cur): ...              # 15 days idle, no call-back → released + 'auto_released' event; with callback_on tomorrow → kept; 13 days → kept
def test_call_history_is_never_deleted(cur): ...           # call_logs and line_outcomes counts identical before and after a run that stages nothing for that student
def test_course_history_is_replaced_per_student(cur): ...
def test_only_service_role_may_run(cur):
    as_user(cur, JO)
    with pytest.raises(psycopg.errors.InsufficientPrivilege): cur.execute("select apply_push(1)")
```

Write every `...` test in full with the assertions named in its comment.

- [ ] **Step 2: Run** `py -m pytest supabase/tests/test_apply_push.py -v`. Expected: FAIL.
- [ ] **Step 3: Write** `0004_apply_push.sql` following the nine steps.
- [ ] **Step 4: Run** `py -m pytest supabase/tests -v`. Expected: all pass.
- [ ] **Step 5: Commit** `git commit -am "feat: nightly merge function"`

### Task 7: Push script and nightly hook

**Files:**
- Create: `push/supabase_client.py`, `push/refresher_push.py`, `push/kallibragent/axc_refresher_hook.py`, `push/tests/test_push.py`, `push/tests/test_hook.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `rules.build_lines`, `place_students`, `check_lines`, `course_history`; `config.*`; database objects from Tasks 4 and 6
- Produces:
  - `supabase_client.Client(url: str, key: str, session=None)` with `select(table: str, columns: str, **filters) -> list[dict]` (pages through all rows, 1,000 at a time), `insert(table: str, rows: list[dict]) -> None`, `update(table: str, values: dict, **filters) -> None`, `rpc(fn: str, **params) -> Any`. Non-2xx raises `PushError`.
  - `refresher_push.credentials() -> tuple[str, str]`: env `REFRESHER_SUPABASE_URL` / `REFRESHER_SERVICE_KEY` first, then `keyring` service `kallibr-refresher`, names `supabase_url`, `service_key`. Missing → `SystemExit("No Supabase key found. Run:  py refresher_push.py --set-key")`.
  - `refresher_push.run(con: sqlite3.Connection, client, today: date, now: datetime, dry_run: bool = False) -> dict` returning `{"result": "ok"|"aborted"|"failed"|"dry-run", "message": str, "lines": int, "students": int, "checks": int, "history": int}`
  - CLI: `py refresher_push.py [--db PATH] [--dry-run] [--set-key]`. `--db` defaults to `%USERPROFILE%\KallibrAgent\axc_agent.db`. Opens the database read-only (`file:...?mode=ro`). Exit code 0 for `ok` and `dry-run`, 1 otherwise. Prints one summary line. Never prints the key.
  - `axc_refresher_hook.run_if_enabled(here: Path) -> int | None`: if `here / "refresher_push.json"` is missing return None. Otherwise read `{"repo": "<path>"}` and run `<repo>/push/refresher_push.py` with the same Python (`subprocess.run([sys.executable, ...])`), returning its exit code. Output goes to the caller's stdout so it lands in `sync.log`.

`run` steps:
1. `source_synced_at` = `max(synced_at)` from `sync_log`. If missing or older than `MAX_SOURCE_AGE_HOURS` before `now`: record an `aborted` run (`insert` into `sync_runs` with `result`, `message`, `finished_at`) and return. Message: `Local database last synced <time>; more than 36 hours old.`
2. `lines = build_lines`, `placed = place_students(..., ignore_ids=IGNORE_BOOKER_CONTACT_IDS)`.
3. Previous size = `lines_pushed` of the latest `ok` run. If one exists and `len(lines) < (1 - MAX_LINE_DROP) * previous`: record `aborted` with `Refusing to push: <n> lines is more than 20% below last run (<previous>).` and return.
4. Existing keys = all `lines` rows in Supabase (`contact_id, refresher_type, last_done`). `checks = check_lines(keys ∪ new line keys)`. `history = course_history(all student IDs staged)`.
5. If `dry_run`: return counts with `result "dry-run"`; make no writes.
6. Insert a `sync_runs` row (`result 'running'`, the four expected counts, `source_synced_at`) and read back its `id`.
7. Insert staging rows in chunks of `CHUNK`. Then `rpc("apply_push", p_run_id=id)`.
8. On any exception after step 6: `update sync_runs set result='failed', message=<short error>, finished_at=now` for that run, and return `failed`. Do not call `apply_push`.

- [ ] **Step 1: Write the failing tests** using a `FakeClient` that records calls and can be told to fail on the nth insert.

```python
def test_stale_source_aborts_and_records(con):
    set_synced(con, NOW - timedelta(hours=37)); out = run(con, fake, TODAY, NOW)
    assert out["result"] == "aborted" and "36 hours" in out["message"]
    assert fake.inserted("sync_runs")[0]["result"] == "aborted" and fake.rpc_calls == [] and fake.inserted("stage_lines") == []

def test_big_drop_aborts(con):       # previous ok run lines_pushed=100; database yields 79 lines
    assert run(con, fake, TODAY, NOW)["result"] == "aborted"

def test_drop_of_exactly_20_percent_proceeds(con):   # previous 100; database yields 80
    assert run(con, fake, TODAY, NOW)["result"] == "ok"

def test_happy_path_stages_then_applies(con):
    out = run(con, fake, TODAY, NOW)                    # database with 3 students, 4 lines
    run_row = fake.inserted("sync_runs")[0]
    assert (run_row["result"], run_row["lines_pushed"], run_row["students_pushed"]) == ("running", 4, 3)
    assert len(fake.inserted("stage_lines")) == 4 and fake.rpc_calls == [("apply_push", {"p_run_id": fake.run_id})]
    assert fake.call_order.index("stage_lines") < fake.call_order.index("rpc")

def test_existing_supabase_lines_get_checked(con):      # fake holds a line no longer on the list; a real later booking exists
    run(con, fake, TODAY, NOW)
    assert any(c["won"] and c["contact_id"] == 9 for c in fake.inserted("stage_checks"))

def test_chunks_of_500(con): ...                        # 1,200 lines → stage_lines insert called with 500, 500, 200

def test_upload_failure_marks_failed_and_never_applies(con):    # Review Focus 2
    fake.fail_on("stage_lines", call=2); out = run(con, fake, TODAY, NOW)
    assert out["result"] == "failed" and fake.rpc_calls == []
    assert fake.updated("sync_runs")[-1]["result"] == "failed"

def test_dry_run_writes_nothing(con):
    out = run(con, fake, TODAY, NOW, dry_run=True)
    assert out["result"] == "dry-run" and fake.writes == []

def test_missing_key_exits_with_instructions(monkeypatch): ...   # SystemExit message contains "--set-key"

def test_hook_does_nothing_without_setting(tmp_path):
    assert run_if_enabled(tmp_path) is None

def test_hook_runs_the_repo_script(tmp_path): ...       # writes refresher_push.json pointing at a stub repo whose script exits 3 → returns 3
```

- [ ] **Step 2: Run** `py -m pytest push/tests -v`. Expected: new tests FAIL.
- [ ] **Step 3: Implement** the three modules. `supabase_client` talks to `<url>/rest/v1/<table>` and `<url>/rest/v1/rpc/<fn>` with the key in the `apikey` and `Authorization: Bearer` headers, following the retry style of `Api.call` in `KallibrAgent\axc_common.py`. `today` in the CLI is `datetime.now(ZoneInfo("Australia/Sydney")).date()`.
- [ ] **Step 4: Run** `py -m pytest push/tests -v`. Expected: all pass.
- [ ] **Step 5: Dry run against the real database.** Run `py push/refresher_push.py --dry-run` (needs the test project's key set with `--set-key` first). Expected: one line reporting roughly 4,050 lines and 3,620 students (the spec's 18 November figures; they drift daily).
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: nightly push script and hook"`

### Task 8: Reporting queries

**Files:**
- Create: `supabase/migrations/0005_reporting.sql`, `supabase/tests/test_reporting.py`
- Modify: `supabase/reset.sql`

**Interfaces:**
- Produces:
  - View `v_cards` (`with (security_invoker = true)`, select granted to `authenticated`): `card_key, kind, target_contact_id, target_name, org_name, org_key, claimed_by, claimed_by_name, claimed_at, callback_on, do_not_call, students int, open_lines int, overdue_lines int, earliest_due date, locations text[], types text[], has_tentative boolean, sibling_cards int`. An **open line** is `status in ('not_called','pending') and in_window`. `students`, `overdue_lines` (due before `sydney_today()`), `earliest_due`, `locations`, `types`, `has_tentative` are computed over the card's open lines. `sibling_cards` = other cards with the same non-null `org_key` and at least one open line. Cards with no open lines still appear, with `open_lines = 0`.
  - `team_stats(p_from date default null) returns table(staff_id uuid, full_name text, cards_taken int, calls_logged int, pending int, won int, lost int, win_rate numeric)`: one row per active staff member. `cards_taken` = distinct cards with a `claimed` event by them or an `assigned` event to them on or after `p_from`; `calls_logged` = their `call_logs`; `pending` / `lost` = lines with that status whose `last_outcome_by` is them and `last_outcome_at` on or after `p_from`; `won` = lines with `won_by` them and `won_at >= p_from`; `win_rate = round(won::numeric / nullif(won + lost, 0), 3)`. All date comparisons on Sydney dates; null `p_from` means all time. `security definer`, raises unless `is_staff()`.
  - `cohort_counts(p_type text default null, p_location text default null) returns table(month date, segment text, n int)`: `month = date_trunc('month', last_done)`; `segment` ∈ `won`, `booked_without_call`, `lost`, `pending`, `not_called` (a won line with `won_without_call` is `booked_without_call`). Includes lines that are out of window. `security definer`, raises unless `is_staff()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_v_cards_counts_open_lines_only(cur): ...
    # card with lines: not_called overdue (QLD, Heights), pending due next month (NSW, Confined Space), lost, won, out-of-window not_called
    # → students 2, open_lines 2, overdue_lines 1, locations {'NSW','QLD'}, types {'Confined Space','Heights'}
def test_v_cards_siblings_share_org_key(cur): ...       # B:900 and B:901 same org_key, both with open lines → sibling_cards 1 each; a third card with no open lines is not counted
def test_v_cards_hidden_from_non_staff(cur): ...        # stranger sees 0 rows
def test_team_stats_counts_and_period(cur): ...
    # JO: 2 claimed events, 3 calls, lines pending 1 / lost 1 / won 1 → win_rate 0.5; p_from tomorrow → all zero and win_rate None
def test_team_stats_lists_staff_with_no_activity(cur): ...
def test_cohort_segments(cur):
    # lines last done Jan 2025: not_called, pending, lost, won by JO, won without call; one Feb 2025 not_called
    cur.execute("select month, segment, n from cohort_counts() order by 1, 2")
    assert cur.fetchall() == [(date(2025,1,1),'booked_without_call',1), (date(2025,1,1),'lost',1), (date(2025,1,1),'not_called',1),
                              (date(2025,1,1),'pending',1), (date(2025,1,1),'won',1), (date(2025,2,1),'not_called',1)]
def test_cohort_filters(cur): ...                       # p_type='Heights' and p_location='NSW' narrow the counts
def test_reporting_refused_for_non_staff(cur): ...      # stranger calling team_stats() or cohort_counts() raises
```

Write every `...` test in full.

- [ ] **Step 2: Run** `py -m pytest supabase/tests/test_reporting.py -v`. Expected: FAIL.
- [ ] **Step 3: Write** `0005_reporting.sql`.
- [ ] **Step 4: Run** `py -m pytest supabase/tests -v`. Expected: all pass.
- [ ] **Step 5: Load the test project with real data** for the page tasks: apply the migrations to the test project, set its key (`--set-key`), run `py push/refresher_push.py`, then add yourself with `insert into staff (email, full_name, role) values ('<owner email>', '<name>', 'manager')` in the Supabase SQL editor. Expected: `select count(*) from lines` is about 4,050.
- [ ] **Step 6: Commit** `git commit -am "feat: queue, team and cohort queries"`

### Task 9: Site shell, sign-in, queue and My cards

**Files:**
- Create: `index.html` (start from `design-kit/starter-template.html`), `tests/site/logic.test.mjs`

**Interfaces:**
- Consumes: `v_cards`, `claim_card`, `release_card`, `sync_runs`, `staff`
- Produces, inside `<script id="rc-logic">` as one object `RC` (also `module.exports = RC` when `module` exists). No DOM or network access in this block.
  - `RC.PROFILE_URL = "https://kallibr.app.axcelerate.com/management/management2/contact_view.cfm?contactID="`; `RC.profileUrl(contactId) -> string`
  - `RC.esc(value) -> string` (escapes `& < > " '`; null and undefined → `""`)
  - `RC.sydneyToday(now = new Date()) -> "YYYY-MM-DD"`
  - `RC.fmtMonth("2024-02-10") -> "Feb 2024"`; `RC.fmtDate("2026-11-12") -> "12 Nov 2026"`
  - `RC.dueLabel(dueIso, todayIso) -> {text, overdue}`: overdue → `{text: "Overdue since Feb 2026", overdue: true}`; else `{text: "Due Mar 2027", overdue: false}`
  - `RC.sortQueue(cards) -> cards`: `open_lines` descending, then `earliest_due` ascending
  - `RC.filterCards(cards, {state, type, due, kind, search}) -> cards`: `state` matches any of `locations`; `type` any of `types`; `due` is `"overdue"` (`overdue_lines > 0`) or `"upcoming"` (`open_lines > overdue_lines`); `search` is a case-insensitive substring of `target_name` or `org_name`; empty filters match everything
  - `RC.queueCards(cards) -> cards`: unclaimed, not `do_not_call`, `open_lines > 0`
  - `RC.myCards(cards, staffId, todayIso) -> cards`: claimed by `staffId` with `open_lines > 0`; cards with `callback_on <= todayIso` first (earliest first), then the rest by `sortQueue`
  - `RC.staleBanner(lastOkFinishedAtIso, nowMs) -> string | null`: more than 36 hours → `"The list was last updated <date>. It may be out of date."`
- Page structure: sign-in screen; app shell with sidebar items `📞 Queue`, `🗂️ My cards`, `📊 Dashboard`, `⚙️ Admin` (managers only); pages `page-queue`, `page-mine`, `page-card`, `page-dashboard`, `page-admin`. Two constants at the top of `<script id="rc-app">`: `SUPABASE_URL`, `SUPABASE_KEY` (publishable key). `openCard(cardKey)` shows `page-card` (filled in Task 10).

- [ ] **Step 1: Write the failing tests** in `tests/site/logic.test.mjs`. Load `RC` by reading `index.html`, extracting the contents of `<script id="rc-logic">` and evaluating it with `node:vm`.

```js
test('esc neutralises markup and quotes', () => {            // Review Focus 4
  assert.equal(RC.esc(`<img src=x onerror=1> & "O'Brien"`), '&lt;img src=x onerror=1&gt; &amp; &quot;O&#39;Brien&quot;');
  assert.equal(RC.esc(null), '');
});
test('profileUrl', () => assert.equal(RC.profileUrl(14929308),
  'https://kallibr.app.axcelerate.com/management/management2/contact_view.cfm?contactID=14929308'));
test('sydneyToday is the Sydney date, not UTC', () => {       // Review Focus 3
  assert.equal(RC.sydneyToday(new Date('2026-11-19T22:30:00Z')), '2026-11-20');
});
test('dueLabel', () => {
  assert.deepEqual(RC.dueLabel('2026-02-10', '2026-11-18'), { text: 'Overdue since Feb 2026', overdue: true });
  assert.deepEqual(RC.dueLabel('2027-03-18', '2026-11-18'), { text: 'Due Mar 2027', overdue: false });
});
test('sortQueue: biggest first, then most overdue', () => { /* open_lines 3/due 2026-05, 9/2026-08, 9/2026-01 → order 9/2026-01, 9/2026-08, 3 */ });
test('filterCards by state, type, due and search', () => { /* one card NSW+QLD Heights overdue "Pat Booker"/"Acme"; one VIC HSR upcoming; assert each filter alone and combined; search "acme" and "PAT" both hit */ });
test('queueCards hides claimed, do-not-call and finished cards', () => { /* 4 cards → 1 */ });
test('myCards puts due call-backs first', () => { /* today 2026-11-18: callback 2026-11-17, callback 2026-11-25, none → order: 17th, then the other two by sortQueue */ });
test('staleBanner only after 36 hours', () => { /* 35h → null; 37h → message containing "out of date" */ });
```

Write the commented tests out in full.

- [ ] **Step 2: Run** `node --test tests/site`. Expected: FAIL.
- [ ] **Step 3: Build the page.** Keep the starter template's shell, stylesheet block and Chart.js tag; remove its sample pages. Add supabase-js v2 from a CDN. Sign-in: one email field and a "Email me a sign-in link" button (`signInWithOtp`, no new-user creation); after sign-in, look up the caller's `staff` row; if none, show "Your account isn't set up for this tool yet. Ask your manager." and a Sign out button. Queue page: page header ("Queue", subtitle "Bookers and students due a refresher that nobody has taken yet"), filter row (state pills QLD / NSW / VIC / G+L, type pills, due pills, card-type select, search input), table (`Booker or student`, `Organisation`, `State`, `Refreshers`, `Overdue`, `Earliest due`, action) with pagination at 25 rows and a `Take` button per row. `Take` calls `claim_card`; true → toast "Card taken ✓" and `openCard`; false → toast "Someone else just took that card" and refresh. My cards page: same table for `RC.myCards`, with a 🟡 "Call back today" badge where due and `Open →` and `Release` buttons. Sidebar footer: "List updated <date>"; warning banner from `RC.staleBanner`. Empty states per the style guide. All data through `RC.esc` or `textContent`.
- [ ] **Step 4: Run** `node --test tests/site`. Expected: all pass.
- [ ] **Step 5: Check in the browser** against the test project (serve the folder with `py -m http.server 8080`, add `http://localhost:8080` to the test project's allowed redirect URLs):
  - Signed out: only the sign-in screen; the network tab shows no data requests returning rows.
  - Sign in as the owner: Queue lists cards, largest first; each filter narrows the list; search finds an organisation.
  - `Take` on a card moves it to My cards; in a second browser profile signed in as another staff member the card is gone from the Queue.
  - `Release` returns it.
  - Layout matches the starter template (cream background, white 24px-radius cards, lavender table header, DM fonts).
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: site shell, queue and my cards"`

### Task 10: Card view and call logging

**Files:**
- Modify: `index.html`, `tests/site/logic.test.mjs`

**Interfaces:**
- Consumes: `RC.*` from Task 9; tables `cards`, `students`, `lines`, `course_history`, `call_logs`, `line_outcomes`, `staff`; `save_call_log`, `release_card`, `assign_card`, `clear_do_not_call`; `v_cards` (siblings)
- Produces in `RC`:
  - `RC.OUTCOMES = [{code:'no_answer', label:'No answer / left message', status:'pending'}, {code:'call_back', label:'Call back', status:'pending'}, {code:'info_sent', label:'Info or quote sent', status:'pending'}, {code:'will_book', label:'Will book', status:'pending'}, {code:'not_needed', label:'Not needed', status:'lost'}, {code:'went_elsewhere', label:'Went elsewhere', status:'lost'}, {code:'left_company', label:'Left the company', status:'lost'}, {code:'do_not_call', label:'Do not call', status:'lost'}]`
  - `RC.STATUS_BADGE = {not_called: ['badge-neutral','Not called'], pending: ['badge-warning','🟡 Pending'], won: ['badge-success','🟢 Won'], lost: ['badge-danger','🔴 Lost']}`
  - `RC.groupLines(lines, students, todayIso) -> [{contact_id, full_name, dueForBoth, rows:[line...]}]`: one entry per student who has at least one line, sorted by the student's earliest open `due_date` (students with no open line last); `rows` sorted by `due_date`; `dueForBoth` true when the student has two or more open lines
  - `RC.cardSummary(groups, todayIso) -> string`: e.g. `"9 students · 11 refreshers · 7 overdue, 4 due by Mar 2027"` (counts open lines and the students who have at least one; the "due by" month is the latest open due date; omit a part that is zero; singular "1 student", "1 refresher")
  - `RC.buildOutcomes(selections) -> [{line_id, outcome}]`: drops lines with no selection
  - `RC.validateCallLog(outcomes, callbackOn, todayIso) -> string | null`: `"Choose an outcome for at least one refresher."`, `"Pick a call-back date."`, `"The call-back date can't be in the past."`, else null

- [ ] **Step 1: Add the failing tests**

```js
test('groupLines sorts and flags due-for-both', () => {
  // student 1: Confined Space due 2026-02-05 (open) + Heights due 2026-03-07 (open); student 2: Heights due 2027-01-10 (open); student 3: Heights won
  const g = RC.groupLines(LINES, STUDENTS, '2026-11-18');
  assert.deepEqual(g.map(x => [x.contact_id, x.dueForBoth, x.rows.length]), [[1, true, 2], [2, false, 1], [3, false, 1]]);
});
test('a second line that is already lost does not count as due-for-both', () => { /* one open + one lost → false */ });
test('cardSummary', () => assert.equal(RC.cardSummary(RC.groupLines(LINES, STUDENTS, '2026-11-18'), '2026-11-18'),
  '2 students · 3 refreshers · 2 overdue, 1 due by Jan 2027'));
test('buildOutcomes drops blanks', () => assert.deepEqual(RC.buildOutcomes({ 11: 'will_book', 12: '' }), [{ line_id: 11, outcome: 'will_book' }]));
test('validateCallLog', () => {
  assert.equal(RC.validateCallLog([], null, T), 'Choose an outcome for at least one refresher.');
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'call_back' }], null, T), 'Pick a call-back date.');
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'call_back' }], '2026-11-17', T), "The call-back date can't be in the past.");
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'will_book' }], null, T), null);
});
test('every outcome maps to pending or lost, never won', () => assert.ok(RC.OUTCOMES.every(o => ['pending', 'lost'].includes(o.status))));
```

- [ ] **Step 2: Run** `node --test tests/site`. Expected: new tests FAIL.
- [ ] **Step 3: Build `page-card`** to the sketch in spec 5.7:
  - Hero: target name linking to `RC.profileUrl(target_contact_id)` (no link on organisation cards), organisation, state tags, `RC.cardSummary`, "n other bookers at this organisation" listing each sibling's name, owner and an `Open →` link, and a `tentative booking` badge where any line has `tentative`.
  - Table: `Student` (link to profile), `Refresher`, `Last done` (`RC.fmtMonth`), `Due` (`RC.dueLabel`, red badge when overdue), status badge, `Outcome` select. Second row of a due-for-both student shows a purple `Due for both` badge under the name. HSR lines with `attendance_confirmed = false` show the hint "attendance not confirmed". Won lines show "Booked for <class date>" and no select. Each student row expands to list `course_history` (course and date).
  - Form: `Apply one outcome to all` select (fills every open line's select), `Call back on` date, `Notes` textarea, primary button `Save Call Log`.
  - Saving: validate with `RC.validateCallLog`; if any outcome is `do_not_call`, ask "Mark this whole card as do not call? Every open refresher on it will be closed and this person won't appear on future lists." (Yes → `p_dnc_card true`; No → only that line). Call `save_call_log`. On success toast "Call log saved ✓" and reload the card; if `skipped_line_ids` is not empty, show an info banner "<n> refresher(s) were booked since you opened this card, so they stay as Won." On failure keep everything the user typed and show the error in a danger banner.
  - History: `log-item` entries, newest first: date and time (Sydney), staff name, each line's outcome label, notes via `textContent`.
  - Buttons: `Release card` (owner or manager). Managers also see `Assign to…` (staff select) and, on a do-not-call card, `Clear do not call`.
  - Card not claimed by the viewer: the form is replaced by "Taken by <name>" or a `Take` button.
- [ ] **Step 4: Run** `node --test tests/site`. Expected: all pass.
- [ ] **Step 5: Check in the browser** against the test project:
  - Open the largest card: all students listed, overdue first; a due-for-both student has two rows and the badge.
  - Both profile links open the right aXcelerate contact in a new tab.
  - "Apply one outcome to all" fills every row; changing one row then saving records different outcomes per line (confirm in the History entry).
  - `Call back` without a date is refused with the message; with a date, the card shows 🟡 on My cards on that date.
  - Type `<b>bold</b> & "quotes"` in Notes, save: History shows the literal text.
  - In the Supabase SQL editor set one open line on the card to `won`; without reloading the page, save an outcome for it: the banner about booked refreshers appears and the line stays Won.
  - Turn the network off, press Save: the notes are still in the box and an error shows.
- [ ] **Step 6: Commit** `git commit -am "feat: card view and call logging"`

### Task 11: Dashboard and admin

**Files:**
- Modify: `index.html`, `tests/site/logic.test.mjs`

**Interfaces:**
- Consumes: `cohort_counts`, `team_stats`, `upsert_staff`, `staff`, `sync_runs`
- Produces in `RC`:
  - `RC.SEGMENTS = [{key:'won', label:'Won', color:'#9ecf9e'}, {key:'booked_without_call', label:'Booked without a call', color:'#c8e6c8'}, {key:'lost', label:'Lost', color:'#f2a0b0'}, {key:'pending', label:'Pending', color:'#f9be7c'}, {key:'not_called', label:'Not called', color:'#ddd4f0'}]`
  - `RC.cohortChart(rows) -> {labels, datasets}`: `labels` are every month from the earliest to the latest in `rows` with no gaps, formatted `RC.fmtMonth`; one dataset `{label, data, backgroundColor}` per segment in `RC.SEGMENTS` order with zeros filled in
  - `RC.kpis(rows) -> {total, not_called, pending, won, lost, booked_without_call}` where `won` includes `booked_without_call`
  - `RC.periodStart(period, todayIso) -> "YYYY-MM-DD" | null`: `"week"` → Monday of the current week; `"month"` → first of the month; `"all"` → null
  - `RC.fmtRate(x) -> string`: `0.5 → "50%"`, null → `"–"`

- [ ] **Step 1: Add the failing tests**

```js
test('cohortChart fills gaps and keeps segment order', () => {
  const rows = [{ month: '2025-01-01', segment: 'won', n: 2 }, { month: '2025-03-01', segment: 'not_called', n: 5 }];
  const c = RC.cohortChart(rows);
  assert.deepEqual(c.labels, ['Jan 2025', 'Feb 2025', 'Mar 2025']);
  assert.deepEqual(c.datasets.map(d => d.label), ['Won', 'Booked without a call', 'Lost', 'Pending', 'Not called']);
  assert.deepEqual(c.datasets[0].data, [2, 0, 0]); assert.deepEqual(c.datasets[4].data, [0, 0, 5]);
});
test('cohortChart with no rows', () => assert.deepEqual(RC.cohortChart([]), { labels: [], datasets: RC.SEGMENTS.map(s => ({ label: s.label, data: [], backgroundColor: s.color })) }));
test('kpis', () => assert.deepEqual(RC.kpis([{ month: '2025-01-01', segment: 'won', n: 2 }, { month: '2025-01-01', segment: 'booked_without_call', n: 1 },
  { month: '2025-02-01', segment: 'lost', n: 4 }, { month: '2025-02-01', segment: 'not_called', n: 10 }]),
  { total: 17, not_called: 10, pending: 0, won: 3, lost: 4, booked_without_call: 1 }));
test('periodStart', () => {                                    // 18 Nov 2026 is a Wednesday
  assert.equal(RC.periodStart('week', '2026-11-18'), '2026-11-16');
  assert.equal(RC.periodStart('month', '2026-11-18'), '2026-11-01');
  assert.equal(RC.periodStart('all', '2026-11-18'), null);
});
test('fmtRate', () => { assert.equal(RC.fmtRate(0.5), '50%'); assert.equal(RC.fmtRate(null), '–'); });
```

- [ ] **Step 2: Run** `node --test tests/site`. Expected: new tests FAIL.
- [ ] **Step 3: Build `page-dashboard`:** KPI row (`.grid-4` plus one): Total refreshers, Not called, Pending, Won (sub-text "<n> booked without a call"), Lost, with `.accent-*` stripes matching the segment meanings. Cohort card: title "Progress by month of last course", filter pills for refresher type and state, a vertical stacked bar chart (Chart.js `type: 'bar'`, both axes `stacked: true`, `borderRadius: 6`, axis and tick settings from style guide section 6, legend shown at the bottom because the segments need naming, tooltip "<segment>: <n>"). Team card: segmented toggle `This week / This month / All time`, table `Team member`, `Cards taken`, `Calls logged`, `Pending`, `Won`, `Lost`, `Win rate` (`.num` columns). **Build `page-admin`** (managers only): staff table with `+ Add team member` modal (name, email, role select, active check-pill) calling `upsert_staff`, a hint that the person must also be invited under Authentication in Supabase, and a "Nightly updates" list of the last 14 `sync_runs` (date, result badge, message, lines, wins).
- [ ] **Step 4: Run** `node --test tests/site`. Expected: all pass.
- [ ] **Step 5: Check in the browser:** the chart shows one vertical bar per month from late 2023, tallest around mid-2024; the five KPI numbers add up (total = not called + pending + won + lost); logging a call on a card and reloading moves one refresher from Not called to Pending and adds 1 to your Calls logged; a staff (non-manager) account sees no Admin item and gets an error calling `upsert_staff` from the console.
- [ ] **Step 6: Commit** `git commit -am "feat: dashboard and admin"`

### Task 12: Go live

**Files:**
- Modify: `index.html` (live `SUPABASE_URL` and publishable key), `README.md`, `%USERPROFILE%\KallibrAgent\axc_nightly.pyw`
- Create: `%USERPROFILE%\KallibrAgent\axc_refresher_hook.py` (copy), `%USERPROFILE%\KallibrAgent\refresher_push.json`

- [ ] **Step 1: Live database.** Apply migrations `0001`–`0005` to the live project in order. In Supabase Auth settings turn off new sign-ups and set the site URL and redirect URL to the GitHub Pages address. Insert the owner's `staff` row as `manager`. Invite the owner's email under Authentication.
- [ ] **Step 2: Publish.** Put the live URL and publishable key in `index.html`. Run `git grep -n -i "service_role\|sb_secret\|secret"`; expected: no key material (matches in docs or variable names only). Push to GitHub and enable Pages from the `main` branch root.
- [ ] **Step 3: Check the public page signed out.** Open the Pages address in a private window. Expected: sign-in screen only. Run `curl "<live url>/rest/v1/students?select=*" -H "apikey: <publishable key>"`; expected: an empty list or a permission error, never rows.
- [ ] **Step 4: First live push.** `py push/refresher_push.py --set-key` (owner types the live URL and secret key), then `py push/refresher_push.py --dry-run`, then `py push/refresher_push.py`. Expected: `ok`, about 4,050 lines, wins 0. Run it a second time; expected: `ok`, 0 new lines.
- [ ] **Step 5: Nightly hook.** Copy `push/kallibragent/axc_refresher_hook.py` into KallibrAgent. In `axc_nightly.pyw`, after the `try/except/finally` and before `sys.exit(code)`, add: if `code == 0`, call `axc_refresher_hook.run_if_enabled(HERE)`; if it returns a non-zero code, print `Refresher push failed (exit <n>)` and set `code = 1`. Create `refresher_push.json` with the repo path. Do not add `refresher_push.json` to any setup package. Run `pyw axc_nightly.pyw` once by hand; expected: `sync.log` ends with the sync summary followed by the push summary line, and the site footer shows today's date.
- [ ] **Step 6: Runbook.** Finish `README.md`: what the tool is, how to add a team member (Admin page + Supabase invite), how to change the designated PC (`--set-key`, hook file, `refresher_push.json`), what each `sync_runs` result means and what to do about `aborted` and `failed`, how to add a course to a refresher type (course master) or an HSR course ID (`push/config.py`), how to run the three test suites, and that the secret key is never to be copied out of Credential Manager.
- [ ] **Step 7: Commit and push** `git add -A && git commit -m "docs: runbook; chore: live configuration" && git push`
