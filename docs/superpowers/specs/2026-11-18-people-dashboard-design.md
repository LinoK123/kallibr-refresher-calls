# People dashboard: design (short)

Date: 18 November 2026
Status: approved by the owner 18 November 2026 ("yes, build it")

## Intent

A second dashboard, alongside the existing one, focused on people: managers see how each team member is going, and staff see their own progress. The owner chose that **everyone sees everything**, so any signed-in staff member can look at any team member.

## Goals, non-goals

- **Goals:**
  - A **People** page with a team-member picker (defaults to the viewer) and a period toggle (This week / This month / All time, Sydney dates).
  - Tiles for the picked person:
    - cards held now;
    - call-backs due;
    - calls logged;
    - won;
    - pending;
    - lost;
    - win rate.
  - A weekly chart of their calls (bars) and wins (line) for the last 12 weeks.
  - Their open cards (click to open).
  - Their recent wins.
  - A team comparison chart of calls and wins per person for the period.
- **Non-goals:** replacing the current Dashboard; any change to the database or to who can see what; new metrics beyond those above.
- **Anti-goals:**
  - figures that disagree with the existing Team table for the same period;
  - crediting "booked without a call" wins to anyone.

## Approaches

1. **New page; figures worked out in the page from data staff can already read** (chosen). No live-database change, which matters with no test project, and it's fast enough at Kallibr's scale.
2. New database reporting functions: only worth it at a much larger scale, and it would change the live database without a test project.
3. A tab inside the current Dashboard: that page is already long; a person-focused view reads better on its own.

## Decided

- **Period figures come from the existing `team_stats(p_from)` function**, so they match the Team table exactly: calls logged, won, pending, lost, win rate. The team comparison uses the same rows.
- **"Cards held" and "call-backs due" are current state, not period figures.** They use the same rules as My cards (`RC.callbackDue`).
- **Weekly chart:** the 12 weeks run Monday to Sunday, Sydney time, ending with the current week. Calls are dated by `call_logs.called_at` on the Sydney calendar, and wins by `lines.won_at`, both for that person. Updates saved with no call (`no_call`) aren't counted as calls (since 20 Nov 2026).
- **Recent wins:** the person's last 10 won refreshers. Each shows the student, refresher type, class date and the date booked, linking to the student's aXcelerate profile.
- **Look:** the Kallibr Design Kit patterns already used on the Dashboard (KPI cards, cards, Chart.js 4.4.1 settings).

## Left to the builder

Exact layout within the kit, chart colours from the kit palette (calls in lavender, wins in sage), and the empty-state wording.
