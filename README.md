# Kallibr Refresher Call Tool

A shared call list for Kallibr staff to ring bookers about overdue and upcoming confined space, working at heights and HSR refreshers. A nightly script on one Kallibr PC reads the local aXcelerate copy (`axc_agent.db`), works out who is due and who should be rung, and pushes that to Supabase. Staff use a single-page site on GitHub Pages to take cards, log calls and follow progress on a dashboard. A refresher counts as **won** only when a real booking appears in aXcelerate; staff can never mark a win themselves.

- **Site:** https://linok123.github.io/kallibr-refresher-calls/
- **Supabase project:** `pjxceqwzxruuunbhgbfo` (Sydney). This is the **live** project and the only one; there is no separate test project.
- **Spec and plan:** `docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Day to day

- **Queue:** cards nobody has taken, biggest first. **Assigned to** switches to **All cards** (taken or not) or any team member's cards; held cards show who has them, with **Open →** instead of **Take**. Filter by state, refresher, due status, card type or name.
  - Click a column header to sort. Click again to reverse, and a third time to go back to the usual order.
  - **Take** claims a card for you; nobody else can work it until you release it.
- **Card:** the same kind of filters, plus sortable columns, for the students on a card. **Release card** sits in the card's header (for the holder or a manager).
  - **📋 Copy for email** copies the refreshers still to book that are showing in the table (filter first if you like). The columns are Student, Refresher, Last done, Due and a blank **Date to book** for the booking contact to fill in when they reply. It pastes as a table in Outlook.
- **My cards:** your cards. The **Assigned to** picker shows anyone's held cards, or **All team members**, with "held by" on each row. Only the holder or a manager can release a card. **📅 Your call-backs** at the top lists every call-back you've set, soonest first (overdue, today, this week, later), each with **Open →**. The same filters as the Queue narrow the table below it (the call-backs list always shows everything), and columns sort like the Queue. A card with no activity for 14 days and no call-back still to come goes back to the queue overnight. A card a manager assigned waits 28 days instead. If it's released and someone takes it, it's back on 14.
- **Monday email:** each team member with overdue call-backs or call-backs due this week gets one email listing them. It comes from the nightly push on the first run of each week, normally Monday morning (see "Call-back emails" below).
- **Card:** ring the booker, pick an outcome per refresher (or "Apply one outcome to all"), add notes and an optional call-back date, then **Save Call Log**.
- **Dashboard:** totals, the team table (this week, this month, all time) and progress by month of each student's last course.
- **People:** any team member's progress, opening on you. **All team members** shows the whole team together, including who holds each card and who won each refresher. It shows:
  - cards held and call-backs due, right now;
  - calls, wins, pending, lost and win rate for the chosen period (the same figures as the Dashboard's team table);
  - calls and wins per week over the last 12 weeks;
  - their open cards and recent wins;
  - a team comparison chart.

  Everyone can see everyone.
- **Admin (managers):** team members and the last 14 nightly updates.

## Adding, changing or removing a team member

1. **Admin page → + Add team member:** name, Kallibr email, role (Staff or Manager), Active ticked.
2. **Supabase → Authentication → Users → Add user → Create new user:** their email, any long random password (it is never used; don't keep it), and **Auto Confirm User** ticked. Sign-ups are switched off, so this is the only way in.
3. Send them the site address. They enter their work email, click **Email me a sign-in code**, and type the code from the email. Sign-in uses typed codes rather than links because Microsoft 365's email security scanners open links in incoming mail, which uses up one-time sign-in links before the person clicks (seen at go-live).

**Don't use "Send invitation".** An invited account stays unconfirmed until the invitation is accepted. With sign-ups off, Supabase then refuses to send that person a code, and the site says their sign-in "hasn't been activated yet". To activate someone who was invited, run this in the SQL Editor:

```sql
update auth.users set email_confirmed_at = now()
where email = '<their email, lower-case>' and email_confirmed_at is null;
```

This is safe: they still need the code that goes to their own mailbox to sign in.

To remove someone, open **Admin → Edit**, untick **Active** and save. Their cards go straight back to the queue and they see nothing on their next request. You can also delete their user under Authentication → Users. You can't remove your own manager access, so another manager has to do that.

Sign-in and invitation emails are sent through the custom SMTP account set in Supabase (Authentication → Emails → SMTP Settings): a dedicated Gmail account, sending through Gmail's own server with an app password. Without custom SMTP, Supabase only emails members of the Supabase organisation, two emails an hour. The app password lives only in Supabase and the Google account, never in this repository. A Kallibr-domain sender (for example through Brevo) needs kallibr.com.au authenticated first, because the domain's DMARC policy refuses unapproved senders.

To set up or replace the Gmail sender:

1. On the Google account, turn on 2-Step Verification.
2. Create an app password named "Supabase" (Google Account → Security → 2-Step Verification → App passwords).
3. In Supabase → Authentication → Emails → SMTP Settings, enable custom SMTP:
   - sender email and username: the Gmail address
   - sender name: `Kallibr Refresher Calls`
   - host: `smtp.gmail.com`, port: `587`
   - password: the app password

If the app password is ever exposed, revoke it in the Google account and create a new one.

**Microsoft 365 must allow the sender.** Kallibr's Microsoft 365 treated the automated code emails from a Gmail address as phishing. They were held where only admins can see them: not in Junk, and not in the person's own quarantine. A manual email from the same Gmail account still got through. The fix (18 Nov 2026) was in Microsoft Defender → Email & collaboration → Policies & rules → Threat policies → **Tenant Allow/Block Lists → Domains & addresses → Add → Allow**, with the exact Gmail address (never all of gmail.com). If codes go missing again:
- check that allow entry hasn't expired;
- run **Exchange admin center → Mail flow → Message trace** on the sender and recipient;
- release anything held in Defender → Quarantine, reporting it as not junk.

If the sender address changes, the allow entry must change too.

### Email templates (Supabase → Authentication → Emails → Templates)

The emails must carry a **code** (`{{ .Token }}`), never `{{ .ConfirmationURL }}`. A scanner that opens a link would use up the code too, because it is the same one-time token.

- **Magic Link** and **Confirm signup**, both with the subject `Your Refresher Calls sign-in code` and this body:

  ```html
  <h2>Refresher Calls</h2>
  <p>Your sign-in code is:</p>
  <p style="font-size:26px;font-weight:bold;letter-spacing:4px">{{ .Token }}</p>
  <p>Type it on the sign-in page. It works once, for one hour. If you didn't ask for it, you can ignore this email.</p>
  ```

- **Invite user** (only used if someone is invited rather than created; see above), with the subject `You've been added to Kallibr Refresher Calls` and this body:

  ```html
  <h2>Refresher Calls</h2>
  <p>You've been added to Kallibr's refresher call list.</p>
  <p>To sign in, go to <a href="{{ .SiteURL }}">{{ .SiteURL }}</a>, enter this email address and click <b>Email me a sign-in code</b>.</p>
  ```

## Supabase settings that must stay as they are

- **Authentication → Sign In / Providers:** new sign-ups **off**, email confirmation **on**. The site trusts the email address on a signed-in session, so these two settings are what stop strangers getting in.
- **Authentication → URL Configuration:** Site URL and Redirect URLs = `https://linok123.github.io/kallibr-refresher-calls/`.
- **Authentication → Emails → SMTP Settings:** custom SMTP on (Gmail: host `smtp.gmail.com`, port `587`, the Gmail address and its app password). **Rate Limits:** emails per hour high enough for the team. Gmail itself allows about 500 a day from a normal account.

## The nightly push

`push/refresher_push.py` runs on the **designated PC** after the nightly aXcelerate sync. It opens `%USERPROFILE%\KallibrAgent\axc_agent.db` read-only. From it, it works out who is due (spec 5.2), which card each student belongs on (5.3) and which refreshers have been won (5.5). A booking's booker is the person it was requested by. On an in-house class, though, the booker is the class owner, unless the owner works for Kallibr: an organisation starting "Kallibr" or "GL Training" (`STAFF_ORG_PREFIXES` in `push/config.py`), or a staff name. See `docs/superpowers/specs/2026-11-18-current-booker-design.md`. It uploads that to staging tables in Supabase and calls `apply_push` to merge it in one transaction, so a failure changes nothing. It never deletes call logs, outcomes or claims.

```
py push/refresher_push.py --set-key          # once per PC: project URL + secret key into Windows Credential Manager
py push/refresher_push.py --dry-run          # work everything out, write nothing, print one line
py push/refresher_push.py                    # the real push (the nightly job runs this)
py push/refresher_push.py --allow-reversals  # only after checking an "aborted: ... would lose their booking" run
py push/refresher_push.py --set-email        # once per PC: the Gmail sender + its app password, for the Monday emails
py push/refresher_push.py --send-digest --to you@kallibr.com.au   # send this week's call-back email now, to one person
py push/refresher_push.py --manager-report --dry-run              # preview last week's manager report, send nothing
py push/refresher_push.py --manager-report --force --to you@kallibr.com.au   # send last week's report to one person
```

### Call-back emails

- **What triggers them:** after a successful push, the first run of each Monday-to-Sunday week emails every active team member who has overdue call-backs or call-backs due by Sunday. People with none get nothing. A call-back left over from a card's previous holder doesn't count.
- **What they contain:** the card name, organisation and date, plus a link to the site.
- **Never twice a week:** `KallibrAgent\refresher_digest_week.txt` holds the Monday of the week last sent. Delete it to let this week send again.
- **The sender** is the same Gmail account as the sign-in codes (already allowed in Microsoft 365). Its address and app password live in Windows Credential Manager, set with `--set-email`.
- **In `sync.log`:** the push's last line reads "Call-back emails: n sent, n failed". "Not set up" means `--set-email` hasn't been run. An email problem never fails the push.
- `--send-digest` sends this week's emails straight away (all of them, or just `--to` one address) without a push. With `--to`, it doesn't count as this week's send.

### Monday manager report

- **Who gets it:** every active team member whose role is **manager** (Admin → Team). Changing someone's role or making them inactive changes the list from the next send.
- **What it covers:** the previous Monday-to-Sunday week, in Sydney time.
  - **Inputs:** calls logged, refreshers worked (outcomes recorded in those calls) and cards taken (claimed or assigned).
  - **Outputs:** refreshers won (credited to staff, or booked without a call), lost, and the win rate.
  - **The list now:** refreshers still open, cards in the Queue and held, new refreshers added last week, and call-backs overdue.
  - **One row per active team member:** people with no activity are still listed. "–" means no wins or losses yet.
- **Leaving someone off the table:** list their email, one per line, in `KallibrAgent\refresher_report_leave_out.txt`. A `#` starts a note. Use this for managers who don't make calls. They still get the email if they're managers, and their activity still counts in the team totals. Changes apply from the next send. `--dry-run` shows the result.
- **When:** the scheduled task **Kallibr refresher manager report** runs every Monday at 9:00 am and wakes a sleeping PC. If the PC is off, it runs at the next sign-in. A run later in the week still reports the previous week, so a missed Monday sends on Tuesday.
- **The task's action:** `pyw.exe -3 "<repository>\push\refresher_push.py" --manager-report --log "%USERPROFILE%\KallibrAgent\sync.log"`. Its working folder is `<repository>\push`. It needs no push and no sync.
- **Never twice a week:** `KallibrAgent\refresher_report_week.txt` holds the Monday of the week last reported. Delete it to let this week send again, or use `--force`. If every send fails, the file isn't written, so the next run tries again.
- **In `sync.log`:** a block headed "=== date time manager report ===" ends with "Manager report: n sent, n failed" (with the failed addresses), "already sent this week", or the error. "Not set up" means `--set-email` hasn't been run.
- **Options:**
  - `--dry-run` prints the report and its recipients and sends nothing.
  - `--to` sends to one address only and doesn't count as this week's send.
  - `--force` sends even if this week's has gone.
  - `--log PATH` appends everything to a file and prints nothing.
- **Moving PCs:** export the task, or re-create it with the action above. Then delete it on the old PC. Copy `refresher_report_leave_out.txt` across too.

How it is wired on the designated PC:

- The Windows scheduled task **Kallibr aXcelerate sync** runs daily at 5:30 am. It wakes a sleeping PC, and if the PC was off it runs as soon as you next sign in to Windows. It must run `pyw.exe -3 "%USERPROFILE%\KallibrAgent\axc_nightly.pyw"`. Older installs run `py axc_sync.py` directly, which syncs but never pushes. Double-click `KallibrAgent\Hide-SyncWindow.cmd` to switch the task over; it keeps the task's time and settings. To check, run `(Get-ScheduledTask 'Kallibr aXcelerate sync').Actions | Format-List Execute, Arguments` in PowerShell.
- `KallibrAgent\axc_nightly.pyw` runs `axc_sync.py`. If the sync succeeds, it calls `axc_refresher_hook.run_if_enabled(HERE)` (a copy of `push/kallibragent/axc_refresher_hook.py`).
- The hook does nothing unless `KallibrAgent\refresher_push.json` exists. That file holds `{"repo": "<path to this repository>"}` and is what makes a PC the designated one. **Never put `refresher_push.json` in a KallibrAgent setup package.** The hook file and the edited `axc_nightly.pyw` are harmless on other PCs without it.
- The push's one-line summary is appended to `KallibrAgent\sync.log`, after the sync's own output.

### What each nightly result means (Admin → Nightly updates)

| Result | Meaning | What to do |
|---|---|---|
| 🟢 OK | The list and wins were updated. | Nothing. |
| 🟡 Stopped (`aborted`) | A safety stop fired and nothing changed. There are three stops: the local database was last synced more than 36 hours ago; the list would shrink by more than 20%; or more than 10 won refreshers (or 5% of all wins, if that's more) would lose their booking. | **Stale:** check the PC was on and the scheduled sync ran (`sync.log`), then run `axc_nightly.pyw` again. **Shrink or reversals:** usually a partial or filtered sync. Run `py axc_sync.py`, then `py push/refresher_push.py --dry-run` to compare. Only if the change is real, push with `--allow-reversals` (reversals), or run the push by hand after confirming the smaller list is right. |
| 🔴 Failed | Upload or merge error; the live tables were left untouched. | The message says why, and `sync.log` has the detail. The next night retries automatically. |
| Running | In progress, or abandoned by a crash. | The next successful run marks abandoned runs as failed ("superseded"). |

The site shows a warning banner when the last successful update is more than 36 hours old. Calling and logging still work.

### Moving the push to another PC

1. **Old PC:** delete `KallibrAgent\refresher_push.json`.
2. **New PC:** this must be a PC whose aXcelerate permissions see all bookings, because each user's local database is filtered by their own permissions.
   1. Clone this repository.
   2. Run `py -m pip install -r push/requirements.txt`.
   3. Run `py push/refresher_push.py --set-key` and type the project URL and the **secret** key.
   4. Copy `push/kallibragent/axc_refresher_hook.py` into `KallibrAgent`.
   5. Add the refresher block to the end of `axc_nightly.pyw`, as on the current PC.
   6. Create `refresher_push.json` with the new repository path.
   7. Make sure the scheduled task runs `axc_nightly.pyw` (double-click `Hide-SyncWindow.cmd`).
   8. Run `py push/refresher_push.py --dry-run` to check.

The secret key lives only in Windows Credential Manager (service `kallibr-refresher`). **Never copy it out of there:** not into a file, an email, a chat or this repository. The site carries only the publishable key.

## Changing which courses count

- **Confined Space or Heights:** set the course's **Refresher group** in `KallibrAgent\Kallibr_Course_Master.xlsx` (sheet "Course Master") to `Confined Space`, `Heights`, or both (e.g. `Confined Space, Heights`), spelt exactly like that. The next sync picks it up.
- **HSR:** the course master has no HSR group, so HSR course type IDs live in `push/config.py` (`HSR_COURSE_TYPE_IDS`). Intervals, the 3-year window, the 4-month look-ahead and the safety-stop limits are there too.

## Tests

```
py -m pytest push/tests -q                            # rules, push script, hook, client (offline)
"C:\Program Files\nodejs\node.exe" --test tests/site   # the page's logic (offline)
```

The database tests (`supabase/tests`) drop and recreate every tool table, so they only run against a **separate, empty** test Supabase project (`REFRESHER_TEST_DB_URL`, or `py supabase/tests/set_test_db_url.py`). They refuse to run against a database that holds staff, refreshers or call history. There is no test project at the moment.

## Database changes

Migrations are in `supabase/migrations`, applied in order. `0001`–`0005` were applied to the live project on 18 Nov 2026 (clean rebuild, then the first live push). There is no migration-tracking table, so record here each later migration and the date it was applied to live.

- `0006_assigned_auto_release.sql`: assigned cards auto-release after 28 days, not 14. Applied to live on 18 Nov 2026 at the owner's request, without the database tests, since there's no test database. The push run straight afterwards succeeded with 0 released.
