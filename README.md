# Kallibr Refresher Call Tool

A shared call list for Kallibr staff to ring bookers about overdue and upcoming confined space, working at heights and HSR refreshers. A nightly script on one Kallibr PC reads the local aXcelerate copy (`axc_agent.db`), works out who is due and who should be rung, and pushes that to Supabase; staff use a single-page site on GitHub Pages to take cards, log calls and follow progress on a dashboard.
