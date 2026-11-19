# Kallibr Refresher Call Tool: Design

Date: 18 November 2026
Status: approved by the owner 18 November 2026 (item 15 in section 8 added afterwards, while planning)

## 1. Intent

Kallibr has not run refresher follow-up calls for some time. There is a backlog of past students whose confined space, working at heights or Health and Safety Representative (HSR) training is overdue or about to fall due, and nobody is ringing them.

This tool gives Kallibr staff a shared call list for that backlog and keeps it topped up as new people fall due. Staff ring the person who booked the students (or the student, where they booked themselves), mention every refresher that is due, and record what happened. Managers see how each team member is going and how much of each month's past students have been won back.

## 2. Goals, non-goals, anti-goals

**Goals**

- One list of everyone due a refresher, rebuilt every night from aXcelerate data.
- Students grouped under the person who booked them, so one call covers many students.
- A student due for two refreshers is obvious on the card, and each refresher gets its own outcome.
- A card can only be worked by one staff member at a time.
- "Won" means a real booking in aXcelerate, detected automatically.
- A dashboard showing progress per team member and a stacked chart by month of original course.
- Looks like part of the Kallibr tool family (Kallibr Design Kit).

**Non-goals**

- No dialling, SMS or email from the tool.
- No writing back to aXcelerate. Bookings are still made in aXcelerate.
- No phone numbers, emails, addresses, dates of birth or USIs stored in the tool. Staff open the aXcelerate profile for contact details.
- No refresher types beyond confined space, heights and HSR in this version.
- No mobile-first layout. Staff use it at a desk.

**Anti-goals (it has failed if these happen, even if it works)**

- Two staff ring the same booker about the same students.
- Won numbers count a verbal "yes" that never became a booking.
- Student details are readable by anyone who is not a signed-in Kallibr staff member.
- A bad or partial nightly run wipes or corrupts call history.

## 3. Constraints

- **Source data** is the local SQLite database `axc_agent.db` in the `KallibrAgent` folder on one Kallibr PC, rebuilt nightly by `axc_sync.py`. It is read-only and up to a day old. aXcelerate API tokens stay in Windows Credential Manager on that PC.
- **Each KallibrAgent user's database is filtered by their own aXcelerate permissions.** Only one designated PC may push to the tool. The push must not be enabled by default in the setup package that is distributed to other users.
- **Bookings data starts 1 January 2024.** Completions go back to January 2023.
- **HSR results are almost absent from the completions reports.** Unit code `WHSQHSRNCB01` appears for one class only (11 students, 12 October 2026); `NSW_HSR_5` does not appear at all. About 74 HSR classes with roughly 700 booked places have run since 2023. HSR therefore has to be read mainly from bookings.
- **Design:** follow `KALLIBR_STYLE_GUIDE.md`, `kallibr-theme.css` and `starter-template.html` from the Kallibr Design Kit. Single HTML file with CSS and JS inline, Chart.js 4.4.1, DM Serif Display and DM Sans, emoji as icons, Australian English. No secrets in front-end files.
- **Hosting:** GitHub Pages. On a free GitHub plan the repository must be public, and a Pages site is public either way, so the repository and page hold code only, never data.
- **Dates** are worked out in Australia/Sydney time.

## 4. Approaches considered

1. **GitHub Pages + Supabase, list built nightly on the PC and pushed up (chosen).** Reuses the existing sync and business rules; tokens never leave the PC. Trade-off: if the PC is off overnight the list and won numbers go a day stale, though calling and logging still work.
2. **Same site and database, list built in the cloud straight from aXcelerate.** No PC dependency, but the tokens must live in the cloud and the sync rules are rebuilt and maintained in two places. Can be added later.
3. **Nightly spreadsheet on SharePoint.** Dropped: it cannot lock a card to the person who claimed it and the dashboard would be weak.

The owner chose approach 1.

## 5. What gets built

Three parts:

1. **Nightly push script** on the designated PC (Python, alongside the existing KallibrAgent scripts). Reads `axc_agent.db`, works out lines and cards, pushes them to Supabase, and detects wins.
2. **Supabase project** (Sydney region): Postgres tables, sign-in, and access rules.
3. **Single-page site** on GitHub Pages: Queue, My cards, Card view, Dashboard.

### 5.1 Refresher types

| Type | Courses | Interval |
|---|---|---|
| Confined space | Courses listed under "Confined Space" in `course_refresher_groups` | 24 months |
| Heights | Courses listed under "Heights" in `course_refresher_groups` | 24 months |
| HSR | Course type IDs 100882, 101060, 114315 | 12 months |

A course can belong to two types (116646 counts for both confined space and heights). Always join through `course_refresher_groups` by `course_type_id`, never by course name or the `refresher_group` text. The HSR course IDs and the intervals live in a small config in the push script, because the course master has no HSR group yet.

### 5.2 Lines: who is due

A **line** is one student due for one refresher type. Identity: (contact ID, refresher type, last-done date).

**A "real booking"** throughout this document means a booking that the existing `counted` flag in `v_bookings` marks as 1: status Approved, Booked, Completed, Moved or Replaced, on a class that is not cancelled. Moved and Replaced are included on purpose. In the data a Moved booking sits on the class the student actually attended (847 of 853 past Moved bookings on these courses have a completion on that class).

- **Done event, confined space and heights:** a row in `v_completions` (competent outcome) for a course in that type. Date = `completed_on`.
- **Done event, HSR:** either a row in `v_completions` for an HSR course, or a real booking on an HSR course whose class has already started. A booking-only event means "was booked on a class that ran", not "confirmed attended", so the card labels those HSR lines with a small "attendance not confirmed" hint. Lines backed by a completion carry no hint. If HSR results start flowing into the completions reports, the tool picks them up with no change.
- **Last done** = the latest done event for that student and type.
- **Due date** = last done + the type's interval.
- A line is **on the list** when all of these hold:
  - last done is within the past 3 years
  - due date is on or before today + 4 months
  - the student has no future booking in the same type (class start today or later; status Approved, Booked, Moved, Replaced, Tentative or Waitlisted)
  - the student has no real booking in the same type on a class starting after the last-done date. Someone who has already been booked again is not rung, and does not show up as an instant "won" on the first night

On 18 November 2026 this gives 4,053 lines for 3,624 people: 1,489 confined space (1,165 overdue), 2,183 heights (1,802 overdue), 381 HSR (329 overdue). 428 people have more than one line. These figures, and the card counts in 5.3, were produced by applying the rules in this document to the database synced that morning; use them as a rough check, not an exact test target, because the data changes daily.

Lines are never deleted. A line that ages past 3 years without being won is marked out of window: it leaves the queue but stays in the dashboard under its last status.

### 5.3 Cards: who gets called

A **card** is one call target with their students underneath. Each student sits on exactly one card, so someone due for two refreshers is always handled in one call.

Placement is per student, not per line. To place a student, take their most recent done event across their on-list lines and find the matching real booking (same contact, course type and class start date). Then:

| Case | Card |
|---|---|
| Booking has a requester (`bookings.whobyid`) who is not the student | **Booker card**, keyed by the requester's contact ID. Shows the requester's name with a link to their aXcelerate profile. |
| Requester is the student | **Individual card** for that student |
| No booking or requester (courses before 2024, or blank) and the student has an organisation | **Organisation card**, keyed by organisation name (trimmed, case-insensitive) |
| No requester, and no organisation or the organisation is "Cash - Individual Participants" | **Individual card** |

Group by requester contact ID, not name: one name can map to many IDs.

Two adjustments to the table:

- **One person, one card.** If a student is also the booker for other students, their own lines go on their booker card, not on a separate individual card. (54 people today.)
- **Kallibr staff are not bookers.** If the requester is a Kallibr staff member, ignore the requester and fall through to the organisation or individual rows. Treat a requester as staff when their name matches someone who has entered 50 or more bookings (`bookedstatusenteredbyfullname`), or when their contact ID is on an ignore list in the push script's config. (5 students today.)

On 18 November 2026: 1,282 cards (613 booker cards holding 2,980 lines, 136 organisation cards holding 462, 533 individual cards holding 611). 737 cards have a single line; 28 cards have 20 or more lines and hold 1,057 between them.

Rules:

- **Sticky placement:** once any call has been logged for a student on a card, that student stays on that card, including any new line of theirs that comes onto the list later, even if a later nightly run would place them elsewhere. A student is never on two cards.
- **Sibling cards:** a card shows "n other bookers at this organisation" with links, and shows who has claimed them. Siblings are not locked together.
- **State on a card** = the location(s) where its students last trained (QLD, NSW, VIC, G+L per the Kallibr location rule). A card with students in two states appears under both filters.

### 5.4 Statuses and outcomes

Each line has one status:

| Status | Meaning |
|---|---|
| Not called | No outcome logged |
| Pending | Called; latest outcome is one of: No answer / left message, Call back (with a date), Info or quote sent, Will book |
| Won | A booking was found by the nightly push |
| Lost | Latest outcome is one of: Not needed, Went elsewhere, Done in-house (added 20 Nov 2026: their company ran the refresher itself), Left the company, Do not call |

- Staff can never pick Won.
- "Do not call" on any line asks whether it applies to the whole card. If yes, every open line on the card is lost and the card key (the booker's contact ID, the individual's contact ID, or the organisation name) is flagged.
- While a card key is flagged, new lines that would land on that card are still created, so the dashboard counts stay honest, but they are marked Lost with the reason "Do not call" straight away and never enter the queue. Students are not moved to another card to be rung directly. A manager can clear the flag, which returns those lines to Not called.
- A lost line stays lost for that cycle. The student returns naturally if they later train with Kallibr and fall due again.

### 5.5 Winning

Every night, for each line that is not already won, the push looks for a real booking (see 5.2) for the same student in the same refresher type with a class start date after the line's last-done date.

- Found: the line becomes **Won**. It is credited to the staff member who most recently logged a call on that card on or before the date the booking was made.
- Found, but no call was logged before the booking date: the line becomes Won with no staff credit and is reported as **"Booked without a call"**.
- A Tentative or Waitlisted booking does not win the line; the card shows a "tentative booking" badge.
- A won line returns to the status it had before only when no real booking for that student and type remains after the last-done date. A booking moved to another date is still a win.

### 5.6 Queue and claiming

- **Queue:** all cards with open lines that nobody has claimed, sorted by number of open lines (largest first), then most overdue.
- **Filters:** state, refresher type, due status (overdue / due within 4 months), card type, and a search on organisation or booker name.
- **Take:** a staff member claims a card. The claim is atomic: if two people click at once, one gets it and the other is told it has been taken.
- **Release:** the owner can hand a card back to the queue.
- **Auto-release:** a claimed card with no activity for 14 days and no future call-back date returns to the queue. A card a manager assigned waits 28 days instead. What counts is how the current holder got it last, so an assigned card that was released and then taken is back on 14. *(Owner's request, 18 Nov 2026: migration 0006.)*
- **Managers** can assign or reassign any card to a named staff member.
- **My cards:** the staff member's claimed cards, with call-backs due today or earlier at the top.

### 5.7 Card view

```
┌──────────────────────────────────────────────────────────────┐
│ Booker name → (aXcelerate link)     Organisation name    QLD │
│ 9 students · 11 refreshers · 7 overdue, 4 due by March       │
│ 2 other bookers at this organisation                         │
├──────────────────────────────────────────────────────────────┤
│ Student →        Refresher       Last done   Due       Outcome│
│ Student A →      Confined space  Feb 2024    Feb 2026   [ ▾ ] │
│   DUE FOR BOTH   Heights         Mar 2024    Mar 2026   [ ▾ ] │
│ Student B →      Heights         Jan 2025    Jan 2027   [ ▾ ] │
├──────────────────────────────────────────────────────────────┤
│ Apply one outcome to all [ ▾ ]   Call back on [ date ]       │
│ Notes [                    ]              [ Save Call Log ]  │
│ History: 12 Nov · no answer · left message                   │
└──────────────────────────────────────────────────────────────┘
```

- Profile links use `https://kallibr.app.axcelerate.com/management/management2/contact_view.cfm?contactID=<contact ID>` and open in a new tab.
- Students are sorted by due date, overdue first. A student with two lines gets two rows and a "Due for both" badge.
- Each student row expands to show their other Kallibr courses (course name and date only).
- **Save Call Log** records one call: who, when, notes, optional call-back date, and the outcome chosen for each line. "Apply one outcome to all" fills every open line, and staff can then change individual rows before saving.
- **Updates with no call** (added 20 Nov 2026, owner's request): a **How** choice above the form, 📞 Phone call (the default) or ✉️ No call (email or other), for when someone replies another way. It saves the same way (outcomes, notes, call-back date) with `call_logs.no_call = true` and the button reads **Save Update**. It isn't counted as a call logged anywhere (Team table, People, Monday report). It still counts as work on the card: it keeps a take in Cards taken, and a later booking is credited to whoever saved it. The form goes back to Phone call after each save.
- History lists every call and update on the card, newest first; updates are tagged "✉️ No call".

### 5.8 Dashboard

- **KPI row:** total refreshers, not called, pending, won, lost. "Booked without a call" shown as a sub-figure under won.
- **Team table:** per staff member: cards taken, calls logged, refreshers pending, won, lost, and win rate. A toggle switches between this week, this month and all time.
- **Cohort chart:** vertical stacked bars. One bar per month of last-done date; height = number of refreshers; segments = won, booked without a call, lost, pending, not called. Filters for refresher type and state. Colours follow the design kit's semantic meanings (green won, red/rose lost, amber/peach pending, neutral not called).
- The dashboard counts refreshers (lines), not people.
- A footer line shows when the list was last updated, with a warning banner if the last successful push is more than 36 hours old.

### 5.9 Data held in Supabase

Held: student name, booker name, organisation name, aXcelerate contact IDs, course names and dates, refresher lines, cards, call logs, outcomes, staff accounts, a log of nightly runs.

Not held: phone numbers, emails, addresses, dates of birth, USIs, payment or invoice details.

### 5.10 Access

- Sign-in through Supabase Auth with a Kallibr email. Public sign-up is off; a manager invites staff.
- Two roles: **staff** and **manager**. Everyone sees the dashboard. Only managers assign cards, clear "Do not call", and manage staff.
- Row-level security on every table: nothing is readable without a signed-in, active staff account. Staff can only write call logs and claims as themselves. Only the nightly push (service key) can write lines, cards, course history and win data.
- The service key is stored in Windows Credential Manager on the designated PC, the same way as the aXcelerate tokens. It never goes in the repository or the page. The page carries only the public (anon) key.

### 5.11 Nightly push

- Runs after `axc_sync.py` on the designated PC only, switched on by an explicit local setting.
- Safe to run twice: it upserts by stable keys (line identity, card key).
- Never deletes call logs, outcomes or claims.
- **Safety stop:** it aborts without changing anything, and records the failure, if the local database's last sync is more than 36 hours old or if the number of lines it is about to push is more than 20% lower than the previous run.
- Records each run (time, counts, result) for the "last updated" line on the site.

## 6. Where the existing pieces are

The build happens on the designated Kallibr PC, where these already exist:

- `%USERPROFILE%\KallibrAgent`: `axc_agent.db`, `axc_sync.py` (builds the views used above), `axc_nightly.pyw` (the nightly job), `axc_common.py` (shared helpers, including how tokens are read from Windows Credential Manager), `recipes.sql`, and the dated setup packages that are distributed to other users.
- `Documents\Claude\Claude Code\Kallibr Design Kit`: `KALLIBR_STYLE_GUIDE.md`, `kallibr-theme.css`, `starter-template.html`.

Read these before planning. The push script follows the patterns in `axc_sync.py` and `axc_common.py`; the site starts from `starter-template.html`.

## 7. Left to the builder

- Table and column design, indexes, and whether statuses are stored or derived.
- Sign-in method (password or emailed link).
- How the atomic claim and the 14-day auto-release are implemented.
- Whether the card view is a modal or its own page, and exact layout within the design kit.
- Test approach. At minimum: the due-list, card-placement and win rules tested against a small fixture database, and the access rules tested for a signed-out visitor, a staff member and a manager.
- Repository layout and how the push script is added to the nightly job.

## 8. Calls made by the designer (not yet confirmed by the owner)

1. HSR uses a completion where one exists; otherwise it is read from bookings ("booked on a class that ran") and labelled "attendance not confirmed".
2. Student name, booker name and organisation are stored and shown; no other personal details.
3. Each student sits on one card, chosen from their most recent course, and stays there once a call is logged.
4. Students with no recorded booker are grouped by organisation; self-bookers and "Cash - Individual Participants" get individual cards.
5. Someone who booked themselves and also booked colleagues gets one card, not two.
6. A booking requested by Kallibr staff does not make that staff member the booker.
7. Moved and Replaced bookings count as real bookings; Tentative and Waitlisted do not count as won.
8. A win is only reversed when no real booking remains; a moved booking stays won.
9. "Booked without a call" is its own segment on the chart.
10. Claims auto-release after 14 days without activity.
11. Two roles (staff, manager); everyone sees the dashboard.
12. A lost line stays lost for that cycle. "Do not call" can cover the whole card, and that booker's future students are then marked lost automatically, not rung directly, until a manager clears it.
13. Queue order: most open refreshers first, then most overdue.
14. The push stops itself if the data looks stale or shrinks by more than 20%.
15. A student who already has a real booking after their last-done date never enters the list (added while planning).
