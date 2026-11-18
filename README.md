# Kallibr Refresher Call Tool

A shared call list for Kallibr staff to ring bookers about overdue and upcoming confined space, working at heights and HSR refreshers. A nightly script on one Kallibr PC reads the local aXcelerate copy (`axc_agent.db`), works out who is due and who should be rung, and pushes that to Supabase; staff use a single-page site on GitHub Pages to take cards, log calls and follow progress on a dashboard.

## Nightly push

`push/refresher_push.py` runs on the designated PC after the nightly aXcelerate sync. It opens `%USERPROFILE%\KallibrAgent\axc_agent.db` read-only, works out who is due (spec 5.2), which card each student belongs on (5.3) and which refreshers have been won (5.5), uploads that to staging tables in Supabase, and calls `apply_push` to merge it in one transaction.

```
py push/refresher_push.py --set-key    # once per PC: Supabase project URL + secret key into Windows Credential Manager
py push/refresher_push.py --dry-run    # work everything out, write nothing
py push/refresher_push.py              # the real push; prints one summary line, exit 0 when ok
```

It stops itself, records the stop and changes nothing if the local database was last synced more than 36 hours ago, or if the list would shrink by more than 20% since the last successful run.

On the designated PC, `push/kallibragent/axc_refresher_hook.py` is copied into the KallibrAgent folder and called by `axc_nightly.pyw`. It does nothing unless `refresher_push.json` sits next to it. Never put that file in a setup package.
