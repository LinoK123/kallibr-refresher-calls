"""Kallibr refresher push: reads axc_agent.db (read-only), works out refresher lines and cards,
uploads them to Supabase staging tables, then calls apply_push to merge them in one transaction.

    py refresher_push.py [--db PATH] [--dry-run] [--set-key]

Runs on the designated PC only (see axc_refresher_hook.py). The service key lives in Windows
Credential Manager (service 'kallibr-refresher'); it is never printed, logged or written to a file.
"""
import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import callback_digest  # noqa: E402
import manager_report  # noqa: E402
from rules import build_lines, check_lines, course_history, place_students  # noqa: E402
from supabase_client import Client, PushError  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
KEYRING_SERVICE = "kallibr-refresher"
DEFAULT_DB = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "KallibrAgent" / "axc_agent.db"


def _keyring_get(name):
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, name)
    except Exception:
        return None


def credentials() -> tuple[str, str]:
    """Env vars first, then Windows Credential Manager (set with --set-key)."""
    url = os.environ.get("REFRESHER_SUPABASE_URL") or _keyring_get("supabase_url")
    key = os.environ.get("REFRESHER_SERVICE_KEY") or _keyring_get("service_key")
    if not url or not key:
        raise SystemExit("No Supabase key found. Run:  py refresher_push.py --set-key")
    return url.rstrip("/"), key


def set_key():
    import getpass
    import keyring
    url = input("Supabase project URL (https://<ref>.supabase.co): ").strip().rstrip("/")
    if not url.startswith("https://"):
        raise SystemExit("The project URL starts with https://. Nothing saved.")
    key = getpass.getpass("Secret (service role) key, hidden: ").strip()
    if not key:
        raise SystemExit("No key typed. Nothing saved.")
    keyring.set_password(KEYRING_SERVICE, "supabase_url", url)
    keyring.set_password(KEYRING_SERVICE, "service_key", key)
    print(f"Saved to Windows Credential Manager under '{KEYRING_SERVICE}'.")
    try:
        Client(url, key).select("sync_runs", "id")
        print("Checked: the key can read the project.")
    except PushError as e:
        print(f"Saved, but a test read failed ({str(e).split(':')[0]}). Check the URL and key, "
              "and that the migrations have been applied.")


def _now() -> datetime:
    return datetime.now(SYDNEY)


def _fmt(dt: datetime | None) -> str:
    return dt.astimezone(SYDNEY).strftime("%d %b %Y %H:%M") if dt else "never"


def source_synced_at(con) -> datetime | None:
    """Latest sync_log time. axc_sync.py writes naive local (Sydney) times."""
    try:
        row = con.execute("select max(synced_at) from sync_log").fetchone()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    dt = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    return dt.replace(tzinfo=SYDNEY) if dt.tzinfo is None else dt


def _abort(client, out, message, synced, now, dry_run):
    out.update(result="aborted", message=message)
    if not dry_run:
        client.insert("sync_runs", [{"result": "aborted", "message": message, "finished_at": now.isoformat(),
                                     "source_synced_at": synced.isoformat() if synced else None}])
    return out


def _previous_ok_size(client) -> int | None:
    rows = [r for r in client.select("sync_runs", "id,lines_pushed", result="eq.ok") if r.get("lines_pushed") is not None]
    return max(rows, key=lambda r: r["id"])["lines_pushed"] if rows else None


def _chunks(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def run(con: sqlite3.Connection, client, today: date, now: datetime, dry_run: bool = False,
        allow_reversals: bool = False) -> dict:
    out = {"result": None, "message": "", "lines": 0, "students": 0, "checks": 0, "history": 0}

    # 1. Safety stop: stale local database.
    synced = source_synced_at(con)
    if synced is None or now - synced > timedelta(hours=config.MAX_SOURCE_AGE_HOURS):
        return _abort(client, out, f"Local database last synced {_fmt(synced)}; more than "
                                   f"{config.MAX_SOURCE_AGE_HOURS} hours old.", synced, now, dry_run)

    # 2. Lines and cards.
    lines = build_lines(con, today)
    placed = place_students(con, lines, ignore_ids=config.IGNORE_BOOKER_CONTACT_IDS, today=today)

    # 3. Safety stop: the list shrank too much.
    previous = _previous_ok_size(client)
    if previous and len(lines) < round(previous * (1 - config.MAX_LINE_DROP), 6):
        return _abort(client, out, f"Refusing to push: {len(lines)} lines is more than "
                                   f"{config.MAX_LINE_DROP:.0%} below last run ({previous}).", synced, now, dry_run)

    # 4. Checks for every line we push and every line already in Supabase; history for every student.
    keys = {(l.contact_id, l.refresher_type, l.last_done): None for l in lines}
    won_now = set()
    for e in client.select("lines", "contact_id,refresher_type,last_done,status"):
        key = (int(e["contact_id"]), e["refresher_type"], date.fromisoformat(e["last_done"]))
        keys.setdefault(key, None)
        if e.get("status") == "won":
            won_now.add(key)
    checks = check_lines(con, list(keys), today)
    history = course_history(con, set(placed))

    # Safety stop: a partial or filtered bookings sync would take back wins wholesale.
    reversing = sum(1 for c in checks if not c.won and (c.contact_id, c.refresher_type, c.last_done) in won_now)
    limit = max(config.MAX_REVERSALS_MIN, config.MAX_REVERSAL_SHARE * len(won_now))
    if reversing > limit and not allow_reversals:
        return _abort(client, out, f"Refusing to push: {reversing} won refreshers would lose their booking "
                                   f"(limit {limit:.0f}). Check the local bookings data; if it is right, run "
                                   "py refresher_push.py --allow-reversals.", synced, now, dry_run)

    latest = {}
    for l in lines:
        if l.contact_id not in latest or l.last_done > latest[l.contact_id].last_done:
            latest[l.contact_id] = l
    stage_students = [{
        "contact_id": cid, "full_name": latest[cid].student_name or f"Contact {cid}",
        "org_name": (latest[cid].org_name or "").strip() or None,
        "card_key": p.card_key, "card_kind": p.kind, "target_contact_id": p.target_contact_id,
        "target_name": p.target_name or (f"Contact {p.target_contact_id}" if p.target_contact_id else p.card_key),
        "card_org_name": p.org_name, "card_org_key": p.org_key,
    } for cid, p in sorted(placed.items())]
    stage_lines = [{
        "contact_id": l.contact_id, "refresher_type": l.refresher_type, "last_done": l.last_done.isoformat(),
        "due_date": l.due_date.isoformat(), "course_name": l.course_name, "location": l.location,
        "attendance_confirmed": l.attendance_confirmed,
    } for l in lines]
    stage_checks = [{
        "contact_id": c.contact_id, "refresher_type": c.refresher_type, "last_done": c.last_done.isoformat(),
        "in_window": c.in_window, "won": c.won, "booked_on": c.booked_on.isoformat() if c.booked_on else None,
        "class_date": c.class_date.isoformat() if c.class_date else None, "course_name": c.course_name,
        "tentative": c.tentative,
    } for c in checks]
    stage_history = [{"contact_id": cid, "course_name": name, "completed_on": on.isoformat()}
                     for cid, name, on in history]
    out.update(lines=len(stage_lines), students=len(stage_students), checks=len(stage_checks),
               history=len(stage_history))

    # 5. Dry run: report only.
    if dry_run:
        out.update(result="dry-run", message="Nothing written.")
        return out

    # 6. The run row, with the counts apply_push will insist on.
    run_row = client.insert("sync_runs", [{
        "result": "running", "source_synced_at": synced.isoformat(),
        "students_pushed": len(stage_students), "lines_pushed": len(stage_lines),
        "checks_pushed": len(stage_checks), "history_pushed": len(stage_history),
    }], returning=True)[0]
    run_id = run_row["id"]

    # 7-8. Stage, then merge. Any failure marks the run failed and leaves live tables alone.
    try:
        for table, rows in (("stage_students", stage_students), ("stage_lines", stage_lines),
                            ("stage_checks", stage_checks), ("stage_history", stage_history)):
            for chunk in _chunks(rows, config.CHUNK):
                client.insert(table, [dict(r, run_id=run_id) for r in chunk])
        result = client.rpc("apply_push", p_run_id=run_id) or {}
    except Exception as e:
        message = (str(e) or type(e).__name__)[:500]
        try:
            client.update("sync_runs", {"result": "failed", "message": message, "finished_at": _now().isoformat()},
                          id=f"eq.{run_id}")
        except Exception:
            pass
        out.update(result="failed", message=message)
        return out

    out.update(result="ok", message=(f"{result.get('lines_new', 0)} new, {result.get('wins', 0)} wins, "
                                     f"{result.get('reversals', 0)} reversals, {result.get('released', 0)} released"))
    return out


def summary(out: dict) -> str:
    counts = f"{out['lines']} lines, {out['students']} students, {out['checks']} checks, {out['history']} history rows"
    if out["result"] in ("ok", "dry-run"):
        return f"Refresher push {out['result']}: {counts}; {out['message']}"
    return f"Refresher push {out['result']}: {out['message']}"


def email_credentials() -> tuple[str, str] | None:
    """The Gmail sender and app password: env vars first, then Windows Credential Manager (--set-email)."""
    user = os.environ.get("REFRESHER_EMAIL_USER") or _keyring_get("email_user")
    password = os.environ.get("REFRESHER_EMAIL_PASSWORD") or _keyring_get("email_password")
    return (user, password) if user and password else None


def set_email():
    import getpass
    import keyring
    user = input("Gmail address that sends the emails: ").strip()
    if "@" not in user:
        raise SystemExit("That isn't an email address. Nothing saved.")
    password = getpass.getpass("Gmail app password (16 letters, hidden): ").replace(" ", "").strip()
    if not password:
        raise SystemExit("No app password typed. Nothing saved.")
    keyring.set_password(KEYRING_SERVICE, "email_user", user)
    keyring.set_password(KEYRING_SERVICE, "email_password", password)
    print(f"Saved to Windows Credential Manager under '{KEYRING_SERVICE}'. "
          "Test it with:  py refresher_push.py --send-digest --to <your email>")


def send_call_back_emails(client, today: date, marker_path: Path, force: bool = False, only: str | None = None) -> str:
    """The Monday call-back emails. Never raises: problems come back as the summary line."""
    creds = email_credentials()
    if not creds:
        return "Call-back emails not set up (run: py refresher_push.py --set-email)"
    try:
        return callback_digest.run_digest(client, today, marker_path, callback_digest.smtp_sender(*creds),
                                          force=force, only=only)
    except Exception as e:
        return f"Call-back emails failed: {type(e).__name__}: {str(e)[:200]}"


def manager_report_cli(a, client, today: date, folder: Path) -> int:
    """--manager-report: last week's team report to every active manager (or a preview with --dry-run).
    The marker and the leave-out list live in `folder` (the KallibrAgent folder)."""
    leave_out = folder / config.REPORT_LEAVE_OUT
    if a.dry_run:
        report = manager_report.collect(client, today, manager_report.read_addresses(leave_out))
        subject, text, _ = manager_report.render(report)
        print(f"Manager report preview (nothing sent). To: {', '.join(manager_report.managers(client)) or '(no active managers)'}")
        print(f"Subject: {subject}\n\n{text}")
        return 0
    creds = email_credentials()
    if not creds:
        print("Manager report not set up (run: py refresher_push.py --set-email)")
        return 1
    try:
        print(manager_report.run_report(client, today, folder / config.REPORT_MARKER, callback_digest.smtp_sender(*creds),
                                        force=a.force, only=a.to, leave_out_path=leave_out))
    except Exception as e:
        print(f"Manager report failed: {type(e).__name__}: {str(e)[:200]}")
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Push refresher lines and cards to Supabase.")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="path to axc_agent.db (opened read-only)")
    ap.add_argument("--dry-run", action="store_true", help="work everything out, write nothing")
    ap.add_argument("--set-key", action="store_true", help="store the Supabase URL and secret key")
    ap.add_argument("--set-email", action="store_true", help="store the Gmail sender and app password")
    ap.add_argument("--send-digest", action="store_true", help="send this week's call-back emails now (no push)")
    ap.add_argument("--manager-report", action="store_true", help="email last week's team report to the managers (no push)")
    ap.add_argument("--force", action="store_true", help="with --manager-report: send even if this week's has gone")
    ap.add_argument("--to", help="with --send-digest or --manager-report: send only to this address")
    ap.add_argument("--log", help="append everything printed to this file (for scheduled runs)")
    ap.add_argument("--allow-reversals", action="store_true",
                    help="push even though many won refreshers would lose their booking (after checking)")
    a = ap.parse_args(argv)
    if a.log:
        import contextlib
        with open(a.log, "a", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            what = "manager report" if a.manager_report else "refresher push"
            print(f"\n=== {_now():%Y-%m-%d %H:%M} {what} ===")
            try:
                return _main(a)
            except Exception:                         # scheduled runs have no console: keep the reason in the log
                import traceback
                traceback.print_exc()
                return 1
    return _main(a)


def _main(a) -> int:
    if a.set_key:
        set_key()
        return 0
    if a.set_email:
        set_email()
        return 0
    url, key = credentials()
    db = Path(a.db).resolve()
    marker = db.parent / config.DIGEST_MARKER
    if a.send_digest:
        print(send_call_back_emails(Client(url, key), _now().date(), marker, force=True, only=a.to))
        return 0
    if a.manager_report:
        return manager_report_cli(a, Client(url, key), _now().date(), db.parent)
    if not db.exists():
        print(f"Refresher push failed: no database at {db}")
        return 1
    con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    client = Client(url, key)
    try:
        now = _now()
        try:
            out = run(con, client, now.date(), now, dry_run=a.dry_run, allow_reversals=a.allow_reversals)
        except PushError as e:
            out = {"result": "failed", "message": str(e)[:500], "lines": 0, "students": 0, "checks": 0, "history": 0}
    finally:
        con.close()
    print(summary(out))
    if out["result"] == "ok":                    # the Monday call-back emails, once a week
        print(send_call_back_emails(client, now.date(), marker))
    return 0 if out["result"] in ("ok", "dry-run") else 1


if __name__ == "__main__":
    sys.exit(main())
