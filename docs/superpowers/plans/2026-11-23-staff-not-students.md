# Kallibr Staff Are Not Students Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Kallibr staff off the refresher list as students, and remove the 11 staff refreshers already in the live tool.

**Architecture:** `rules.build_lines` drops students whose most recent refresher-type course was under a staff organisation, or who are on the config's staff contact list. A one-off migration, `0010`, deletes the staff students already in Supabase by the same organisation rule, and releases held cards that end up empty. It runs on live once, after a read-only preview and the owner's OK.

**Tech Stack:** Python 3, SQLite fixture, pytest; Postgres (plpgsql `do` block), psycopg for applying to live.

**Spec:** `docs/superpowers/specs/2026-11-23-staff-not-students-design.md` (changes section 5.2 of the main spec)

## Global Constraints

- **Staff organisation:** `org.strip().lower()` starts with a `config.STAFF_ORG_PREFIXES` entry (`"Kallibr"`, `"GL Training"`), lower-cased. In SQL: `lower(trim(org_name)) like 'kallibr%' or lower(trim(org_name)) like 'gl training%'`.
- **Most recent course:** the latest done event for that contact across all refresher types, before any window or due filtering. If several events share that date, one under a staff organisation is enough.
- **Staff contact list:** `config.IGNORE_BOOKER_CONTACT_IDS` (empty today).
- **No names:** names are never used to spot staff, and no names or contact IDs go into the repository.
- **Clean-up order:** the push change must be in this folder before the clean-up runs, because the nightly job runs from here.
- **Clean-up guard:** it stops without changing anything if more than 20 refreshers would go.
- **Nothing else is deleted:** call logs and card rows stay.
- **Live only:** `pjxceqwzxruuunbhgbfo` is the only project. Never run `supabase/tests`.

## Review Focus

1. **"Kallibr" in the middle of an organisation name** (`Acme c/o Kallibr`): the customer stays on the list. *(Test, Task 1.)*
2. **Case and spaces** (`  kallibr training `): still counted as staff. *(Test, Task 1.)*
3. **Ex-staff now with a customer:** their latest course is under Acme, after an older Kallibr one, so they stay. *(Test, Task 1.)*
4. **A staff course that isn't due yet:** a heights course under Kallibr, more recent than a due confined space course under Acme, still drops the student. *(Test, Task 1.)*
5. **The clean-up picks different people from the push:** the preview must list exactly the contact IDs the push now leaves out. *(Check, Task 2.)*

---

### Task 1: The push leaves staff students out

**Files:** Modify `push/rules.py`, `push/refresher_push.py` (pass the staff list), `push/config.py` (comment on `IGNORE_BOOKER_CONTACT_IDS`: Kallibr staff, never bookers and never students). Test: `push/tests/test_lines.py`. Docs:
- spec 5.2 gets a bullet: Kallibr staff are not students (added 23 Nov 2026);
- the new design's status becomes approved;
- the README's "The nightly push" paragraph says staff students are left out.

**Interfaces:**
- `rules._staff_org(org: str | None) -> bool`, also used by `_is_kallibr` in place of its inline prefix check.
- `rules.build_lines(con, today, ignore_ids: tuple[int, ...] = ()) -> list[Line]`.
- `refresher_push.run` calls `build_lines(con, today, ignore_ids=config.IGNORE_BOOKER_CONTACT_IDS)`.

- [ ] **Step 1: Write the failing tests** in `test_lines.py` (`TODAY` = 18 Nov 2026; heights `100889`, confined space `100890`):
  - `test_staff_org_student_left_out`:
    - contact 1 has `comp(..., "2024-06-10", org="Kallibr Training")`;
    - contact 2 the same with `org="GL Training"`;
    - contact 3 the same with `org="Acme Pty Ltd"`;
    - expect the contact IDs `[3]`.
  - `test_staff_org_case_and_spaces`: `org="  kallibr training "` gives no lines.
  - `test_kallibr_mid_name_is_a_customer`: `org="Acme c/o Kallibr"` gives one line.
  - `test_ex_staff_back_on_list_under_new_company`:
    - a heights course on 2023-12-01 under Kallibr Training;
    - a confined space course on 2024-06-10 under Acme;
    - expect one Confined Space line with `org_name == "Acme Pty Ltd"`.
  - `test_newer_staff_course_not_yet_due_drops_student`:
    - a confined space course on 2024-06-10 under Acme (due);
    - a heights course on 2026-01-15 under Kallibr Training (not due);
    - expect `[]`.
  - `test_same_day_staff_event_counts`: two completions on 2024-06-10, one under Acme and one under Kallibr Training, give `[]`.
  - `test_ignore_ids_left_out`: `build_lines(con, TODAY, ignore_ids=(1,))` with contacts 1 and 2 due gives `[2]`.
- [ ] **Step 2:** Run `py -m pytest push/tests -q`. Expected: the new tests fail (unexpected lines, and a `TypeError` for `ignore_ids`).
- [ ] **Step 3: Implement** `_staff_org` and the filter in `build_lines`. Find each contact's latest event date across all `events` keys for that contact, before the window and due checks. Skip the contact if any event on that date has a staff organisation, or if the contact is in `ignore_ids`. Pass the list from `refresher_push.run`.
- [ ] **Step 4:** Run `py -m pytest push/tests -q` and `"C:\Program Files\nodejs\node.exe" --test tests/site`. Expected: all pass (120 + 7 Python, 47 site).
- [ ] **Step 5: Dry run** with `py push/refresher_push.py --dry-run`. Expected: a "dry-run" line with about 4,002 lines and 3,583 students, 11 lines and 10 students fewer than before (give or take daily drift).
- [ ] **Step 6: Commit:** `git commit -m "feat: Kallibr staff are not students on the refresher list"`.

### Task 2: One-off clean-up of the live tool

**Files:** Create `supabase/migrations/0010_remove_staff_students.sql`. Docs: the README's "Database changes" list gets the `0010` entry, with the date it was applied and the counts.

**Interfaces:** consumes the organisation rule from the Global Constraints. It produces no functions: it's one `do` block that runs once.

- [ ] **Step 1: Write `0010`.** It's one `do $$ … $$` block. It picks staff students from `students` by the SQL organisation rule, keeping their contact IDs and their card keys. Then:
  - it raises an exception if more than 20 of their lines exist, which aborts with nothing changed;
  - it deletes, in this order, `line_outcomes` on their lines, their `lines`, their `course_history` and their `students` rows;
  - for each of their cards that is held and now has no students, it clears `claimed_by`, `claimed_at` and `callback_on`, and inserts a `card_events` `released` row naming the previous holder;
  - it raises a notice with each count: students, lines, outcomes, history rows, cards released.
- [ ] **Step 2: Read-only preview,** using selects with the service key (`Client(*credentials())`). List the students the rule picks, their lines (status and outcome), the outcomes, the history row count and the cards that would be released. Check against tonight's data:
  - the contact IDs are exactly the ones `build_lines` dropped in Task 1, Step 5;
  - expected counts: 10 students, 11 lines, 4 outcomes, 8 cards released (all held by one person).

  Show the owner and wait for an OK.
- [ ] **Step 3: Apply to live** with psycopg, using the connection string in Windows Credential Manager (`kallibr-refresher-test` / `db_url`, which points at the live project). Run `0010` in one transaction. Before committing, check that no student matches the rule any more and that the notice counts equal the preview. Roll back if anything differs.
- [ ] **Step 4: Check afterwards:**
  - `v_cards` has no card with an open line for those students;
  - `py push/refresher_push.py --dry-run` still gives the Task 1 counts.
- [ ] **Step 5: Commit** `0010` and the README entry: `git commit -m "chore: remove Kallibr staff already on the refresher list (0010)"`. Ask the owner before pushing to GitHub.
