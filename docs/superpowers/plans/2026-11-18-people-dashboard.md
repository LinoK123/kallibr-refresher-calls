# People Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second dashboard, the **People** page, showing any team member's progress (open to every signed-in staff member), plus a team comparison.

**Architecture:** Page-only. The page computes from data staff can already read: the `team_stats(p_from)` function for the period figures (so they match the Team table), `call_logs` and `lines` for the 12-week chart and recent wins, and the cards already loaded (`S.cards`, from `v_cards`). No database change.

**Tech Stack:** `index.html` (vanilla JS, supabase-js 2.118.0, Chart.js 4.4.1), node's built-in test runner.

**Spec:** `docs/superpowers/specs/2026-11-18-people-dashboard-design.md`

## Global Constraints

- **Dates are Sydney dates.** Weeks run Monday to Sunday.
- **Period figures must match the Dashboard's Team table**, so the page uses `team_stats(p_from)` with `p_from = RC.periodStart(period, today)`.
- **Win credit stays as the database records it** (`won_by`). "Booked without a call" (`won_by` null) is nobody's.
- **Every database string goes through `RC.esc` or `textContent`.**
- **Kit tokens and patterns only.** Calls are lavender `#b8a9de` and wins sage `#9ecf9e`. Australian English.

## Review Focus

1. **Someone with no activity:** all tiles 0, win rate "–", the chart shows 12 empty weeks, and the empty-state lines appear in place of the card and win lists. *(Task 1 tests.)*
2. **A call late on Sunday night Sydney time** (Saturday afternoon UTC) counts in that Sunday's week. *(Task 1 test.)*
3. **Inactive staff** aren't in the picker or the comparison (`team_stats` lists active staff only). *(Task 2 check.)*
4. **Names with quotes or HTML** show as plain text. *(Task 2, by `RC.esc`.)*
5. **Figures agree with the Dashboard's Team table** for the same person and period. *(Task 2 browser check.)*

---

### Task 1: People-page logic

**Files:** Modify `index.html` (the `rc-logic` block). Test: `tests/site/logic.test.mjs`.

**Interfaces — produces:**
- `RC.weekStarts(todayIso: string, n = 12) -> string[]`: the Monday ISO dates, oldest first; the last is the Monday of the week containing `todayIso`.
- `RC.weeklySeries(callDates: string[], winDates: string[], todayIso: string, n = 12) -> {labels: string[], calls: number[], wins: number[]}`:
  - inputs are Sydney ISO dates, and dates outside the n weeks are ignored;
  - labels are each week's Monday as `"16 Nov"`.
- `RC.personTiles(row: object|undefined, cards: object[], staffId: string, todayIso: string) -> {held, callbacks, calls, won, pending, lost, rate}`:
  - `held` = cards claimed by `staffId` with `open_lines > 0`;
  - `callbacks` = those where `RC.callbackDue` is true;
  - `calls`, `won`, `pending`, `lost` and `rate` come from the `team_stats` row (`calls_logged`, `won`, `pending`, `lost`, `win_rate`), or 0 / null if there's no row.
- `RC.teamComparison(rows: object[]) -> {labels, calls, wins}`: sorted by calls logged (most first), then won, then name.

- [ ] **Step 1: Write the failing tests:**
  - `weekStarts('2026-11-18', 3)` → `['2026-11-02','2026-11-09','2026-11-16']`.
  - `weekStarts('2026-11-22', 1)` → `['2026-11-16']` (a Sunday belongs to the week starting the Monday before).
  - `weeklySeries(['2026-11-16','2026-11-22','2026-11-10','2026-10-01'], ['2026-11-17'], '2026-11-18', 2)` → `{labels:['9 Nov','16 Nov'], calls:[1,2], wins:[0,1]}`.
  - `personTiles(undefined, [], 'me', T)` → all zeros, `rate: null`.
  - `personTiles(row, cards, 'me', T)`, with 2 held cards (one call-back due) and the row `{calls_logged:5, won:1, pending:2, lost:1, win_rate:'0.5'}` → `{held:2, callbacks:1, calls:5, won:1, pending:2, lost:1, rate:'0.5'}`.
  - `teamComparison` orders `[{full_name:'B', calls_logged:3, won:1}, {full_name:'A', calls_logged:3, won:2}, {full_name:'C', calls_logged:9, won:0}]` as C, A, B.
- [ ] **Step 2:** Run `node --test tests/site`. Expected: the new tests fail.
- [ ] **Step 3:** Implement the four functions and export them on `RC`.
- [ ] **Step 4:** Run `node --test tests/site`. Expected: all pass.

### Task 2: People page

**Files:** Modify `index.html` (sidebar, a `page-people` section, the `rc-app` script) and `README.md` (one line under "Day to day").

**Interfaces — consumes:** Task 1's functions; the `team_stats` RPC; the `call_logs` and `lines` tables; `S.cards`, `S.staff`, `openCard`.

- [ ] **Step 1: Sidebar.** Under Progress, add `👥 People` (`data-nav="people"`). `showPage('people')` calls `renderPeople()`.
- [ ] **Step 2: Header.** Title "People", subtitle "How each team member is going: calls, wins and the cards they hold". On the right:
  - a team-member select (active staff by name, defaulting to the viewer);
  - the period segmented toggle (This week / This month / All time).
- [ ] **Step 3: Tiles.** In a `.kpi-5`-style grid of seven: Cards held, Call-backs due, Calls logged, 🟢 Won, 🟡 Pending, 🔴 Lost, Win rate (`RC.fmtRate`). Use the semantic accents.
- [ ] **Step 4: Weekly chart.** Card title "Calls and wins per week", subtitle "Last 12 weeks". It's a Chart.js bar chart (calls, lavender) with a line dataset (wins, sage), using the Dashboard's axis styling and a legend at the bottom.
  - Data: `call_logs.called_at`, `staff_id = picked`, `called_at >= first Monday`; and `lines.won_at`, `won_by = picked`, `status = won`, `won_at >= first Monday`.
  - Convert `called_at` to a Sydney date with `RC.sydneyToday(new Date(ts))`.
- [ ] **Step 5: Two lists side by side** (`.grid-2`):
  - "Their cards": `RC.myCards(S.cards, picked, today)`, showing name, open refreshers, and the 🟡 badge when `RC.callbackDue`, with `Open →`.
  - "Recent wins": `lines` where `won_by = picked`, ordered by `won_at` desc, limit 10, with `students(full_name)`. Show the student (linked to their profile), the refresher, "class <date>" and "booked <date>".
  - Empty states: "No cards held right now." and "No wins yet."
- [ ] **Step 6: Team comparison.** A horizontal grouped bar chart (`indexAxis: 'y'`) of calls and wins per person for the period, from `RC.teamComparison(team_stats rows)`.
- [ ] **Step 7:** Stale responses (a quick change of person or period) must not overwrite newer ones; use the ticket pattern from the Dashboard.
- [ ] **Step 8:** Run `node --test tests/site` and `py -m pytest push/tests -q`. Expected: all pass.
- [ ] **Step 9: Browser check (read-only, no saving).** The page loads for the owner. The tiles match the Dashboard's Team table for the same period. Switching person and period updates everything, and the console is clean.
- [ ] **Step 10:** Add the README line, then commit and push. Wait for GitHub Pages to serve the new page.
