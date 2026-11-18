# Call-backs List and Monday Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff see their call-backs on the site and get them by email every Monday.

**Architecture:** The site part is pure functions in `RC` plus rendering on My cards and People. The email part is a new `push/callback_digest.py` that reads `staff`, `cards`, `lines` and `students` with the push's service-key client, builds one email per person, and sends through Gmail SMTP. `refresher_push.main` calls it after an ok push.

**Tech Stack:** `index.html` (vanilla JS) with node:test; Python `smtplib` / `email.message` with pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-callbacks-design.md`

## Global Constraints

- **Dates are Sydney dates;** weeks run Monday to Sunday.
- **Callback rule:** the card is held, has `callback_on` and has at least one open refresher. The callback must not be earlier than the Sydney date of `claimed_at`.
- **No secrets in the repository.** Email credentials come from env `REFRESHER_EMAIL_USER` / `REFRESHER_EMAIL_PASSWORD`, otherwise from keyring `kallibr-refresher` (`email_user`, `email_password`).
- **Email HTML escapes every value.** Australian English throughout.

## Review Focus

1. **A call-back left by a previous holder** isn't listed or emailed. *(Tests in both tasks.)*
2. **A Sunday call-back** is "This week"; a Monday one is "Later". *(Tests.)*
3. **A PC that's off on Monday** sends on the next run, and only once that week. *(Tests.)*
4. **A name with `&`, `<` or `'`** is escaped in the email HTML. *(Test.)*
5. **An SMTP failure** is reported in the summary and the push still exits 0. *(Test.)*

---

### Task 1: Site call-backs list

**Interfaces:**
- `RC.callbackList(cards, staffId | 'all', todayIso) -> [{card, bucket, date}]`: sorted by date, then card name. `bucket` is one of `overdue`, `today`, `week` or `later`.
- `RC.fmtWeekday(iso) -> "Fri 20 Nov"`.

- [ ] **Step 1: Write the failing tests:**
  - the buckets around Wed 18 Nov 2026 (13 Nov overdue, 18 Nov today, 22 Nov week, 23 Nov later);
  - a previous holder's leftover is excluded;
  - an unheld card is excluded;
  - a card with no open refreshers is excluded;
  - `'all'` includes every holder;
  - `fmtWeekday`.
- [ ] **Step 2:** Run `node --test tests/site`. Expected: FAIL.
- [ ] **Step 3:** Implement. Render the section on My cards (`#mine-callbacks`) and a card on People (`#people-callbacks`).
- [ ] **Step 4:** Run `node --test tests/site`. Expected: all pass.

### Task 2: Monday email

**Files:**
- Create `push/callback_digest.py` and `push/tests/test_digest.py`.
- Modify `push/refresher_push.py` (`--set-email`, `--send-digest`, `--to`; call after an ok push) and `push/config.py` (`SITE_URL`, `SMTP_HOST`, `SMTP_PORT`, `DIGEST_MARKER = "refresher_digest_week.txt"`).

**Interfaces:**
- `week_start(today: date) -> date`
- `collect(client, today) -> list[Digest]`, where `Digest(email, full_name, overdue: list[Item], week: list[Item])` and `Item(card_name, org_name, date)`
- `render(d: Digest, today) -> (subject, text, html)`
- `send_all(digests, sender, today) -> (sent, failed)`, where `sender(to, subject, text, html)` raises on failure
- `run_digest(client, today, marker_path, sender, force=False, only=None) -> str` (the summary line)

- [ ] **Step 1: Write the failing tests:**
  - `week_start`;
  - `collect` with a fake client: buckets, a leftover excluded, inactive staff excluded, no-open-refresher cards excluded, people with nothing get no digest;
  - `render` escapes HTML and includes the site link;
  - `run_digest` sends once per week (the second call sends nothing), sends late in the week when Monday was missed, `force` resends, `only` limits recipients, and a sender failure is reported without raising.
- [ ] **Step 2:** Run `py -m pytest push/tests -q`. Expected: the new tests fail.
- [ ] **Step 3:** Implement, then wire it into `refresher_push.main`. If credentials are missing it prints "Call-back emails not set up (run --set-email)" and the exit code is unchanged.
- [ ] **Step 4:** Run `py -m pytest push/tests -q`. Expected: all pass.
- [ ] **Step 5:** Check in the browser, run a digest dry run on live data (counts only), then commit and push.
