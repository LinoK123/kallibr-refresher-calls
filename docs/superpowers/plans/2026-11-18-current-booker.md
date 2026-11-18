# Current Booking Contact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place students whose booker has gone quiet (or who have no booker) on their company's current booker card, per state.

**Architecture:** One extra step inside `rules.place_students`, between the first pass and the "one person, one card" merge. It's fed by a new loader that reads every real booking (any course) from the last 12 months. The nightly push passes `today`.

**Tech Stack:** Python 3, SQLite fixture, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-current-booker-design.md` (changes section 5.3 of the main spec)

## Global Constraints

- **Window:** 12 months, judged on `coalesce(booked_on, start_date) >= add_months(today, -12)`.
- **Real booking** means `counted = 1`. A requester is `bookings.whobyid`; it's not a requester when it equals the student, is a staff name (`STAFF_ENTERED_MIN`), or is in `ignore_ids`.
- **Company** is `org_name.strip().lower()`, excluding blank names and names starting `Cash - Individual`. **State** is the class `location`.
- **Self-bookers and individual cards never move.** Sticky placement is in `apply_push`, so it's unchanged.

## Review Focus

1. **Two bookers tied** in the same company and state: pick deterministically (latest booking, then lowest ID), not by row order. *(Test.)*
2. **A future class booked recently** counts as active (judged by booked date). *(Test.)*
3. **A booking made 13 months ago** doesn't keep a booker active. *(Test.)*
4. **Staff as requesters** are never chosen as the current booker. *(Test.)*
5. **The current booker is also a due student:** after the merge, one person still has one card. *(Covered by the existing merge test plus one new test.)*

---

### Task 1: Current-booker step

**Files:** Modify `push/rules.py` and `push/refresher_push.py` (pass `today=today`). Test: `push/tests/test_cards.py`. Config: `push/config.py` gets `CURRENT_BOOKER_MONTHS = 12`.

**Interfaces:** `rules.place_students(con, lines, ignore_ids=(), today: date | None = None)`. With `today=None` the new step is skipped, which keeps the original behaviour for callers that don't pass it.

- [ ] **Step 1: Write the failing tests** in `test_cards.py`. Each test uses `today=TODAY` (18 Nov 2026), and recent bookings are made with a non-refresher course type (`555`) to show that any course counts.
  - Quiet booker replaced by the QLD current booker.
  - Active booker keeps the student.
  - NSW and QLD students at one company split onto two booker cards.
  - A state with no bookings falls back to the company's busiest booker.
  - A company with no bookings in 12 months keeps its organisation card.
  - Organisation-card students go to the current booker.
  - A self-booker keeps their own card.
  - Staff requesters are ignored.
  - Most bookings wins, and a tie goes to the latest booking.
  - The 12-month edge: 13 months ago doesn't count, and a future class booked last month does.
  - The current booker who is also a due student ends up on their own card.
- [ ] **Step 2:** Run `py -m pytest push/tests -q`. Expected: the new tests fail.
- [ ] **Step 3:** Implement `_current_bookers(con, today, staff, ignore) -> (by_state, by_org, active)` and the step in `place_students`. Pass `today` from `refresher_push.run`.
- [ ] **Step 4:** Run `py -m pytest push/tests -q`. Expected: all pass.
- [ ] **Step 5: Dry run** with `py push/refresher_push.py --dry-run`, plus the NBN Co check. Expected: the line count is unchanged (4,053 give or take daily drift); NBN Co is Therese / Kavita / self-bookers.
- [ ] **Step 6:** Commit, push to live, and commit and push to GitHub.
