# Kallibr staff are not students: design (short)

Date: 23 November 2026
Status: approved by the owner 23 November 2026 ("Approve")
Changes: spec `2026-11-18-refresher-call-tool-design.md` section 5.2 (who is due)

## Intent

Kallibr's own people should never be on the refresher list. Nobody should ring a colleague about their refresher. Staff are already kept off cards as **bookers** (spec 5.3 and the in-house owner rule), but not as **students**. On 23 Nov 2026 that left 10 staff on the list (11 refreshers), all with "Kallibr Training" as the organisation on their last course; 5 of them are trainers.

## Goals, non-goals, anti-goals

- **Goals:**
  - The nightly push never lists a Kallibr staff member as a student.
  - The 11 staff refreshers already in the tool are removed. That includes the 3 already logged as lost, so they stop counting as losses on the Dashboard and the logger's win rate *(owner's choice: "Remove all 11")*.
- **Non-goals:**
  - no change to how bookers are chosen;
  - no change to the site;
  - no change to `apply_push`.
- **Anti-goals:**
  - a real customer is dropped (for example, a customer who shares a name with a trainer: matching by name would have dropped one on 23 Nov 2026);
  - a call log is deleted;
  - the clean-up touches anything beyond the staff students' own rows.

## Approaches

1. **The push skips staff, plus a one-off clean-up** (chosen by the owner). The rule lives in one place, the Python config. The nightly merge function is untouched. Trade-off: if the staff rule widens later, already-listed people need another clean-up by hand.
2. The push sends its staff list to `apply_push`, which deletes their refreshers every night. It cleans itself up, but it changes the core nightly function on the live database without a test database, and it makes the nightly job delete logged outcomes automatically, which it was built never to do. Not chosen.
3. `apply_push` filters by organisation. The rule would be in two places, and the push would still upload staff. Dropped.

## Decided

**Who counts as staff (as a student).** Both of these are builder's calls:
- The organisation on their most recent done event, across all three refresher types (on the list or not), starts with a `config.STAFF_ORG_PREFIXES` entry ("Kallibr", "GL Training"), trimmed and case-insensitive. If two events share that date, one under a staff organisation is enough.
- Or their contact ID is on `config.IGNORE_BOOKER_CONTACT_IDS`, which the spec already defines as Kallibr staff (it's empty today).

Names are not used. Someone who later trains with another company goes back on the list under that company.

**The push.** `rules.build_lines` leaves staff students out, so they get no line, no card, no student row and no course history. On 23 Nov 2026 this takes the list from 4,013 lines (3,593 students) to 4,002 (3,583). That is well inside the 20% shrink stop.

**The one-off clean-up** (migration `0010_remove_staff_students.sql`, run once on live):
- It picks staff students by the same organisation rule, applied to `students.org_name`, so no names or contact IDs go into the public repository.
- In one transaction it deletes, for those students:
  - the outcomes on their refreshers;
  - their refreshers;
  - their course history;
  - their student rows.
- It then releases any held card left with no students and records a `released` event for the holder (builder's call). The site already hides cards with no open refreshers, so this only stops an empty card counting as a card taken. A card with a call logged on it still counts.
- Card rows and all call logs stay; a call whose only outcomes were removed shows in the card history with its notes and no outcomes.
- It stops itself, changing nothing, if more than 20 refreshers would go (builder's call; 11 are expected).
- Before it runs on live, a read-only preview shows exactly what it would remove. It runs only on the owner's OK, after the push change is in place: the nightly job runs from this folder, so running the clean-up first would let the next push put them back.
- On an empty database it removes nothing.

**Records.** The README's "Database changes" list records when `0010` was applied, and spec 5.2 gets a line saying staff are not students.

## Left to the builder

Exact code shape and tests (fixture students under a Kallibr organisation, including a student whose staff course is more recent than their due one), and how the clean-up is applied to live.
