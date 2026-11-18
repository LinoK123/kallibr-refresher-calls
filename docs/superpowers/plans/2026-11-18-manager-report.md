# Monday Manager Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Email every active manager a weekly team report every Monday at 9 am.

**Architecture:** A new `push/manager_report.py` reads `staff`, `call_logs`, `line_outcomes`, `card_events`, `lines`, `students` and `cards` with the push's service-key client, works out the figures for the previous Sydney week, renders the email, and sends it through the existing `callback_digest.smtp_sender`. `refresher_push.py` gets `--manager-report` and `--log`. A Windows scheduled task runs it on Mondays at 09:00.

**Tech Stack:** Python 3, pytest, Windows Task Scheduler (PowerShell `Register-ScheduledTask`).

**Spec:** `docs/superpowers/specs/2026-11-18-manager-report-design.md`

## Global Constraints

- **Sydney dates;** weeks run Monday to Sunday. The report covers the week before the one containing the run date.
- **No secrets in the repository;** email credentials come from `refresher_push.email_credentials()`.
- **HTML escapes every value.** Australian English.

## Review Focus

1. **Week edges:** a call at 11:30 pm Sunday Sydney time is in the week; 12:30 am Monday is not. *(Test.)*
2. **Someone with no activity** is still listed, with zeros and "–". *(Test.)*
3. **Inactive staff** aren't listed and don't get the email. *(Test.)*
4. **A PC that's off at 9 am** sends on the next run that week, and only once. *(Test.)*
5. **One failed recipient** doesn't stop the others and is reported. *(Test.)*

---

### Task 1: Report

**Interfaces:**
- `prior_week(today) -> (monday, sunday)`
- `collect(client, today) -> Report(week_start, week_end, team: dict, people: list[dict])`. The team keys are `calls, worked, cards_taken, won, won_credited, won_without_call, lost, win_rate, open, not_called, queue_cards, held_cards, new_listed, callbacks_overdue`. The person keys are `name, cards_taken, calls, worked, won, lost, win_rate, callbacks_overdue`.
- `render(report) -> (subject, text, html)`
- `run_report(client, today, marker_path, sender, force=False, only=None) -> str`

- [ ] **Step 1: Write the failing tests** in `push/tests/test_manager_report.py`: the week edges, every figure on a fake dataset, render escaping, sending once a week to active managers, force and only, and failure reporting.
- [ ] **Step 2:** Run `py -m pytest push/tests -q`. Expected: the new tests fail.
- [ ] **Step 3:** Implement. Run the tests again. Expected: all pass.

### Task 2: Wiring and task

- [ ] **Step 1: Write the failing tests:**
  - `--manager-report` calls `run_report` with the marker in the database's folder;
  - `--dry-run` prints without sending;
  - `--log` appends the output to the file.
- [ ] **Step 2:** Implement in `refresher_push.main`. Run all tests. Expected: all pass.
- [ ] **Step 3:** Preview on live data with `--manager-report --dry-run`.
- [ ] **Step 4:** Register the scheduled task, read it back, update the runbook, then commit and push.
