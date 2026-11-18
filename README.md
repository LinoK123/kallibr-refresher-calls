# Kallibr Refresher Call Tool

A shared call list for Kallibr staff to ring bookers about overdue and upcoming confined space, working at heights and HSR refreshers. A nightly script on one Kallibr PC reads the local aXcelerate copy (`axc_agent.db`), works out who is due and who should be rung, and pushes that to Supabase. Staff use a single-page site on GitHub Pages to take cards, log calls and follow progress on a dashboard. A refresher counts as **won** only when a real booking appears in aXcelerate; staff can never mark a win themselves.

- **Site:** https://linok123.github.io/kallibr-refresher-calls/
- **Supabase project:** `pjxceqwzxruuunbhgbfo` (Sydney). This is the **live** project and the only one; there is no separate test project.
- **Spec and plan:** `docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Day to day

- **Queue:** cards nobody has taken, biggest first. Filter by state, refresher, due status, card type or name.
  - Click a column header to sort. Click again to reverse, and a third time to go back to the usual order.
  - **Take** claims a card for you; nobody else can work it until you release it.
- **Card:** the same kind of filters, plus sortable columns, for the students on a card.
- **My cards:** your cards, with call-backs due today at the top. A card with no activity for 14 days and no call-back still to come goes back to the queue overnight.
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

`push/refresher_push.py` runs on the **designated PC** after the nightly aXcelerate sync. It opens `%USERPROFILE%\KallibrAgent\axc_agent.db` read-only. From it, it works out who is due (spec 5.2), which card each student belongs on (5.3) and which refreshers have been won (5.5). It uploads that to staging tables in Supabase and calls `apply_push` to merge it in one transaction, so a failure changes nothing. It never deletes call logs, outcomes or claims.

```
py push/refresher_push.py --set-key          # once per PC: project URL + secret key into Windows Credential Manager
py push/refresher_push.py --dry-run          # work everything out, write nothing, print one line
py push/refresher_push.py                    # the real push (the nightly job runs this)
py push/refresher_push.py --allow-reversals  # only after checking an "aborted: ... would lose their booking" run
```

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
