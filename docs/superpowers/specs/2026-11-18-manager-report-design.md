# Monday manager report: design (short)

Date: 18 November 2026
Status: approved by the owner 18 November 2026 ("yes, build it with the 9am task")

## Intent

Every Monday at 9 am, every active manager gets one email showing the previous week: everyone's activity, the team's inputs and outputs, and where the list stands.

## Decided

**Week.** The previous Monday to Sunday, Sydney time, counted from the day the report runs. A report run on a Tuesday, after the PC was off on Monday, still covers the week before.

**Inputs, per person and for the team:**
- **Calls logged:** `call_logs` rows whose Sydney date falls in the week.
- **Refreshers worked:** `line_outcomes` rows belonging to those calls.
- **Cards taken:** distinct cards with a `claimed` event by them, or an `assigned` event to them, in the week. Since 19 Nov 2026 a card counts only if it's still theirs or they logged a call on it after taking it.

**Outputs:**
- **Won:** lines with `status = 'won'` and `won_at` in the week. A person's wins are those with `won_by` = them. The team total also counts "booked without a call" and shows the split.
- **Lost:** lost-type outcomes (not needed, went elsewhere, done in-house, left the company, do not call) logged in the week's calls.
- **Win rate:** won ÷ (won + lost), or "–" when both are 0.

**The list now** (team only, as at the moment the report runs):
- open refreshers (not called or pending, in window), and how many of those are not called;
- cards in the Queue (unclaimed, not do-not-call, with open refreshers) and cards held;
- refreshers newly added last week (`first_listed_on` in the week);
- call-backs overdue, per person and in total, using the same "set while held" rule as the call-backs list.

**People listed:** every active team member, including managers and anyone with no activity, sorted by name. The exception is anyone whose email is in `KallibrAgent\refresher_report_leave_out.txt`: the owner asked for managers who don't call to be kept off the table. That file stays on the PC because the repository is public. Their activity still counts in the team totals.

**Recipients:** every active manager.

**Sending:** the same Gmail sender and app password as the Monday call-back email (`--set-email`), with HTML and plain-text versions and a link to the site. It goes out once per week: `KallibrAgent\refresher_report_week.txt` holds the Monday of the week last reported.

**Running it:** a Windows scheduled task, **Kallibr refresher manager report**, runs every Monday at 09:00:

```
pyw.exe -3 <repo>\push\refresher_push.py --manager-report --log %USERPROFILE%\KallibrAgent\sync.log
```

The task's settings:
- runs as soon as possible after a missed start, and wakes the PC;
- runs on battery;
- runs only while the owner is signed in, like the nightly task;
- 1-hour time limit.

The report reads the live data directly; it doesn't need that morning's sync.

**For testing by hand:**
- `--manager-report --dry-run` prints the report and the recipients and sends nothing;
- `--force` sends even if this week's has gone;
- `--to` sends to one address only, without counting as the week's send.

## Approaches

1. **Its own 9 am task on the designated PC, reusing the push script and Gmail sender** (chosen). It meets the 9 am request with nothing new in the cloud.
2. Sending with the 5:30 am nightly push: no new task, but not at 9 am. Not chosen.
3. A scheduled Supabase function: no dependence on the PC, but more set-up, and the Gmail password would have to live in Supabase too. Not chosen.
