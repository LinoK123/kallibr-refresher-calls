from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import config
import refresher_push
from fixture import book, comp, set_synced
from refresher_push import run
from supabase_client import PushError

TODAY = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 9, 0, tzinfo=ZoneInfo("Australia/Sydney"))


class FakeClient:
    """Records every call. Holds `lines` already in Supabase and the previous ok run's size."""

    def __init__(self, lines=(), previous=None):
        self.existing = list(lines)
        self.previous = previous
        self.run_id = 41
        self.call_order, self.writes, self.rpc_calls = [], [], []
        self._fail = {}
        self._inserts = {}

    def fail_on(self, table, call):
        self._fail[table] = call

    def select(self, table, columns, **filters):
        self.call_order.append(f"select:{table}")
        if table == "sync_runs":
            return [] if self.previous is None else [{"id": 7, "lines_pushed": self.previous}]
        if table == "lines":
            return list(self.existing)
        return []

    def insert(self, table, rows, returning=False):
        self._inserts[table] = n = self._inserts.get(table, 0) + 1
        self.call_order.append(table)
        if self._fail.get(table) == n:
            raise PushError(f"insert {table} failed (call {n})")
        self.writes.append(("insert", table, [dict(r) for r in rows]))
        if returning:
            return [dict(r, id=self.run_id) for r in rows]
        return None

    def update(self, table, values, **filters):
        self.call_order.append(f"update:{table}")
        self.writes.append(("update", table, dict(values), filters))

    def rpc(self, fn, **params):
        self.call_order.append("rpc")
        self.rpc_calls.append((fn, params))
        self.writes.append(("rpc", fn, params))
        return {"lines_new": 0, "wins": 0, "reversals": 0, "released": 0}

    def inserted(self, table):
        return [r for w in self.writes if w[0] == "insert" and w[1] == table for r in w[2]]

    def insert_sizes(self, table):
        return [len(w[2]) for w in self.writes if w[0] == "insert" and w[1] == table]

    def updated(self, table):
        return [w[2] for w in self.writes if w[0] == "update" and w[1] == table]


@pytest.fixture
def fake():
    return FakeClient()


def students(con, n, start=1):
    """n students with one Heights line each."""
    for cid in range(start, start + n):
        comp(con, cid, 100889, "2024-06-10")


def test_stale_source_aborts_and_records(con, fake):
    set_synced(con, NOW - timedelta(hours=37)); out = run(con, fake, TODAY, NOW)
    assert out["result"] == "aborted" and "36 hours" in out["message"]
    assert fake.inserted("sync_runs")[0]["result"] == "aborted" and fake.rpc_calls == [] and fake.inserted("stage_lines") == []


def test_never_synced_aborts(con, fake):
    out = run(con, fake, TODAY, NOW)
    assert out["result"] == "aborted" and fake.inserted("sync_runs")[0]["result"] == "aborted"


def test_sync_35_hours_ago_proceeds(con, fake):
    set_synced(con, NOW - timedelta(hours=35)); students(con, 1)
    assert run(con, fake, TODAY, NOW)["result"] == "ok"


def test_big_drop_aborts(con):       # previous ok run lines_pushed=100; database yields 79 lines
    fake = FakeClient(previous=100); set_synced(con, NOW); students(con, 79)
    out = run(con, fake, TODAY, NOW)
    assert out["result"] == "aborted" and "20%" in out["message"]
    assert fake.inserted("sync_runs")[0]["result"] == "aborted" and fake.rpc_calls == []


def test_drop_of_exactly_20_percent_proceeds(con):   # previous 100; database yields 80
    fake = FakeClient(previous=100); set_synced(con, NOW); students(con, 80)
    assert run(con, fake, TODAY, NOW)["result"] == "ok"


def test_happy_path_stages_then_applies(con, fake):
    set_synced(con, NOW - timedelta(hours=1))
    comp(con, 1, 116646, "2024-05-01"); comp(con, 2, 100889, "2024-06-10"); comp(con, 3, 100890, "2024-03-01")
    out = run(con, fake, TODAY, NOW)                    # database with 3 students, 4 lines
    run_row = fake.inserted("sync_runs")[0]
    assert (run_row["result"], run_row["lines_pushed"], run_row["students_pushed"]) == ("running", 4, 3)
    assert len(fake.inserted("stage_lines")) == 4 and fake.rpc_calls == [("apply_push", {"p_run_id": fake.run_id})]
    assert fake.call_order.index("stage_lines") < fake.call_order.index("rpc")
    assert all(r["run_id"] == fake.run_id for r in fake.inserted("stage_lines") + fake.inserted("stage_students"))
    assert (out["result"], out["lines"], out["students"]) == ("ok", 4, 3)


def test_staged_rows_carry_the_card(con, fake):
    set_synced(con, NOW)
    comp(con, 1, 100889, "2024-06-10", name="Sam Lee")
    book(con, 1, 100889, "2024-06-10", booker=900, booker_name="O'Brien & Sons <Pty>")
    run(con, fake, TODAY, NOW)
    [s] = fake.inserted("stage_students")
    assert (s["contact_id"], s["full_name"], s["card_key"], s["card_kind"], s["target_contact_id"], s["target_name"]) == \
           (1, "Sam Lee", "B:900", "booker", 900, "O'Brien & Sons <Pty>")
    [l] = fake.inserted("stage_lines")
    assert (l["last_done"], l["due_date"], l["attendance_confirmed"]) == ("2024-06-10", "2026-06-10", True)


def test_existing_supabase_lines_get_checked(con):      # fake holds a line no longer on the list; a real later booking exists
    fake = FakeClient(lines=[{"contact_id": 9, "refresher_type": "Heights", "last_done": "2024-06-10"}])
    set_synced(con, NOW); students(con, 1)
    comp(con, 9, 100889, "2024-06-10"); book(con, 9, 100889, "2026-12-01", booked_on="2026-11-17")
    run(con, fake, TODAY, NOW)
    assert any(c["won"] and c["contact_id"] == 9 for c in fake.inserted("stage_checks"))
    assert fake.inserted("sync_runs")[0]["checks_pushed"] == len(fake.inserted("stage_checks")) == 2


def test_history_staged_for_every_student(con, fake):
    set_synced(con, NOW); comp(con, 1, 100889, "2024-06-10", course="WORK SAFELY AT HEIGHTS")
    comp(con, 1, 555, "2024-01-01", course="FIRST AID")
    run(con, fake, TODAY, NOW)
    assert sorted(h["course_name"] for h in fake.inserted("stage_history")) == ["FIRST AID", "WORK SAFELY AT HEIGHTS"]


def test_chunks_of_500(con, fake):                         # 1,200 lines → stage_lines insert called with 500, 500, 200
    set_synced(con, NOW); students(con, 1200)
    run(con, fake, TODAY, NOW)
    assert fake.insert_sizes("stage_lines") == [500, 500, 200]


def test_upload_failure_marks_failed_and_never_applies(con, fake):    # Review Focus 2
    set_synced(con, NOW); students(con, 600)
    fake.fail_on("stage_lines", call=2); out = run(con, fake, TODAY, NOW)
    assert out["result"] == "failed" and fake.rpc_calls == []
    assert fake.updated("sync_runs")[-1]["result"] == "failed"
    assert "stage_lines" in fake.updated("sync_runs")[-1]["message"]


def test_apply_failure_marks_failed(con, fake):
    set_synced(con, NOW); students(con, 1)

    def boom(fn, **params):
        raise PushError("rpc apply_push -> 400: staging incomplete")
    fake.rpc = boom
    out = run(con, fake, TODAY, NOW)
    assert out["result"] == "failed" and fake.updated("sync_runs")[-1]["result"] == "failed"


def test_dry_run_writes_nothing(con, fake):
    set_synced(con, NOW); students(con, 3)
    out = run(con, fake, TODAY, NOW, dry_run=True)
    assert out["result"] == "dry-run" and fake.writes == []
    assert (out["lines"], out["students"]) == (3, 3)


def test_dry_run_with_stale_source_writes_nothing(con, fake):
    set_synced(con, NOW - timedelta(hours=40))
    out = run(con, fake, TODAY, NOW, dry_run=True)
    assert out["result"] == "aborted" and fake.writes == []


def test_missing_key_exits_with_instructions(monkeypatch):
    monkeypatch.delenv("REFRESHER_SUPABASE_URL", raising=False)
    monkeypatch.delenv("REFRESHER_SERVICE_KEY", raising=False)
    monkeypatch.setattr(refresher_push, "_keyring_get", lambda name: None)
    with pytest.raises(SystemExit, match="--set-key"):
        refresher_push.credentials()


def test_env_credentials_win(monkeypatch):
    monkeypatch.setenv("REFRESHER_SUPABASE_URL", "https://x.supabase.co/")
    monkeypatch.setenv("REFRESHER_SERVICE_KEY", "k")
    assert refresher_push.credentials() == ("https://x.supabase.co", "k")


def test_cli_dry_run_prints_one_line_and_opens_read_only(con, tmp_path, monkeypatch, capsys):
    set_synced(con, NOW); students(con, 2); con.close()
    fake = FakeClient()
    monkeypatch.setattr(refresher_push, "credentials", lambda: ("https://x.supabase.co", "secret-key-value"))
    monkeypatch.setattr(refresher_push, "Client", lambda url, key: fake)
    monkeypatch.setattr(refresher_push, "_now", lambda: NOW)
    code = refresher_push.main(["--db", str(tmp_path / "t.db"), "--dry-run"])
    printed = capsys.readouterr().out
    assert code == 0 and len(printed.strip().splitlines()) == 1 and "2 lines" in printed
    assert "secret-key-value" not in printed


def test_cli_exit_code_is_1_when_aborted(con, tmp_path, monkeypatch, capsys):
    con.close()
    monkeypatch.setattr(refresher_push, "credentials", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(refresher_push, "Client", lambda url, key: FakeClient())
    monkeypatch.setattr(refresher_push, "_now", lambda: NOW)
    assert refresher_push.main(["--db", str(tmp_path / "t.db")]) == 1
    assert "aborted" in capsys.readouterr().out


# ---- Final review, issue 1: a bad night must not mass-reverse wins ----

def won_line(cid):
    return {"contact_id": cid, "refresher_type": "Heights", "last_done": "2024-06-10", "status": "won"}


def test_mass_reversal_aborts_and_records(con):
    fake = FakeClient(lines=[won_line(c) for c in range(100, 111)])     # 11 wins whose bookings have vanished
    set_synced(con, NOW); students(con, 1)
    out = run(con, fake, TODAY, NOW)
    assert out["result"] == "aborted" and "11 won refreshers" in out["message"] and "--allow-reversals" in out["message"]
    assert fake.inserted("sync_runs")[0]["result"] == "aborted"
    assert fake.inserted("stage_lines") == [] and fake.rpc_calls == []


def test_ten_reversals_proceed(con):
    fake = FakeClient(lines=[won_line(c) for c in range(100, 110)])
    set_synced(con, NOW); students(con, 1)
    assert run(con, fake, TODAY, NOW)["result"] == "ok"


def test_reversal_limit_scales_with_wins(con):
    fake = FakeClient(lines=[won_line(c) for c in range(100, 500)])     # 400 wins → limit 20
    set_synced(con, NOW); students(con, 1)
    for cid in range(100, 485):                                          # 385 still booked, 15 reversing
        book(con, cid, 100889, "2026-12-01")
    assert run(con, fake, TODAY, NOW)["result"] == "ok"


def test_allow_reversals_overrides_the_stop(con):
    fake = FakeClient(lines=[won_line(c) for c in range(100, 111)])
    set_synced(con, NOW); students(con, 1)
    assert run(con, fake, TODAY, NOW, allow_reversals=True)["result"] == "ok"


def test_dry_run_shows_a_mass_reversal_without_writing(con):
    fake = FakeClient(lines=[won_line(c) for c in range(100, 111)])
    set_synced(con, NOW); students(con, 1)
    out = run(con, fake, TODAY, NOW, dry_run=True)
    assert out["result"] == "aborted" and fake.writes == []


def test_push_places_students_with_the_current_booker(con, fake):
    set_synced(con, NOW)
    comp(con, 1, 100889, "2024-06-10")
    book(con, 1, 100889, "2024-06-10", booker=900, booker_name="Kim Spicer", booked_on="2024-05-01")
    book(con, 50, 555, "2026-10-20", booker=901, booker_name="Therese Stapleton", booked_on="2026-10-01")
    run(con, fake, TODAY, NOW)
    [s] = fake.inserted("stage_students")
    assert (s["card_key"], s["target_name"]) == ("B:901", "Therese Stapleton")


# ---- Monday call-back email wiring ----

@pytest.fixture
def cli(con, tmp_path, monkeypatch):
    """main() against the fixture database with a fake Supabase client; returns (fake, digest calls)."""
    set_synced(con, NOW); students(con, 2); con.close()
    fake, calls = FakeClient(), []
    monkeypatch.setattr(refresher_push, "credentials", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(refresher_push, "Client", lambda url, key: fake)
    monkeypatch.setattr(refresher_push, "_now", lambda: NOW)
    monkeypatch.setattr(refresher_push, "email_credentials", lambda: ("sender@gmail.com", "app-pw"))

    def fake_run_digest(client, today, marker_path, sender, force=False, only=None):
        calls.append(dict(today=today, marker=marker_path, force=force, only=only))
        return "Call-back emails: 2 sent, 0 failed"
    monkeypatch.setattr(refresher_push.callback_digest, "run_digest", fake_run_digest)
    return fake, calls, tmp_path


def test_call_back_emails_go_out_after_an_ok_push(cli, capsys):
    fake, calls, tmp = cli
    assert refresher_push.main(["--db", str(tmp / "t.db")]) == 0
    assert calls == [dict(today=TODAY, marker=tmp / config.DIGEST_MARKER, force=False, only=None)]
    out = capsys.readouterr().out
    assert "Refresher push ok" in out and "Call-back emails: 2 sent" in out


def test_no_call_back_emails_after_a_dry_run(cli):
    fake, calls, tmp = cli
    assert refresher_push.main(["--db", str(tmp / "t.db"), "--dry-run"]) == 0
    assert calls == []


def test_email_not_set_up_is_reported_and_the_push_still_succeeds(cli, monkeypatch, capsys):
    fake, calls, tmp = cli
    monkeypatch.setattr(refresher_push, "email_credentials", lambda: None)
    assert refresher_push.main(["--db", str(tmp / "t.db")]) == 0
    assert calls == [] and "not set up" in capsys.readouterr().out


def test_an_email_crash_never_fails_the_push(cli, monkeypatch, capsys):
    fake, calls, tmp = cli

    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(refresher_push.callback_digest, "run_digest", boom)
    assert refresher_push.main(["--db", str(tmp / "t.db")]) == 0
    assert "Call-back emails failed" in capsys.readouterr().out


def test_send_digest_now_to_one_address_skips_the_push(cli, capsys):
    fake, calls, tmp = cli
    assert refresher_push.main(["--db", str(tmp / "t.db"), "--send-digest", "--to", "jo@kallibr.com.au"]) == 0
    assert calls == [dict(today=TODAY, marker=tmp / config.DIGEST_MARKER, force=True, only="jo@kallibr.com.au")]
    assert fake.writes == []


def test_email_credentials_from_env(monkeypatch):
    monkeypatch.setenv("REFRESHER_EMAIL_USER", "sender@gmail.com")
    monkeypatch.setenv("REFRESHER_EMAIL_PASSWORD", "pw")
    assert refresher_push.email_credentials() == ("sender@gmail.com", "pw")
