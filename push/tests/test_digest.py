from datetime import date

import pytest

import callback_digest as cd
import config

WED = date(2026, 11, 18)


class FakeClient:
    """Serves staff, cards, students and lines; filters are ignored (the digest filters for itself)."""

    def __init__(self):
        self.tables = {
            "staff": [
                {"id": "u1", "email": "jo@kallibr.com.au", "full_name": "Jo Smith", "active": True},
                {"id": "u2", "email": "al@kallibr.com.au", "full_name": "Al Brown", "active": True},
                {"id": "u3", "email": "gone@kallibr.com.au", "full_name": "Gone Person", "active": False},
                {"id": "u4", "email": "none@kallibr.com.au", "full_name": "No Callbacks", "active": True},
            ],
            "cards": [
                card("B:1", "O'Brien & Sons <Pty>", "u1", "2026-11-13", org="Acme"),          # overdue
                card("B:2", "Pat Booker", "u1", "2026-11-18"),                               # today
                card("B:3", "Kim Tran", "u1", "2026-11-22"),                                 # Sunday: this week
                card("B:4", "Later Co", "u1", "2026-11-23"),                                 # next week: not listed
                card("B:5", "Leftover", "u1", "2026-11-10", claimed_at="2026-11-15T00:00:00+00:00"),  # set before the claim
                card("B:6", "Done Card", "u1", "2026-11-19"),                                # no open refreshers
                card("B:7", "Al Card", "u2", "2026-11-20"),
                card("B:8", "Gone Card", "u3", "2026-11-19"),                                # inactive holder
                card("B:9", "Queue Card", None, "2026-11-19"),                               # nobody holds it
            ],
            "students": [{"contact_id": 10 + i, "card_key": f"B:{i}"} for i in range(1, 10)],
            "lines": [{"contact_id": 10 + i, "status": "won" if i == 6 else "not_called", "in_window": True} for i in range(1, 10)],
        }

    def select(self, table, columns, **filters):
        return [dict(r) for r in self.tables[table]]


def card(key, name, holder, callback, org=None, claimed_at="2026-11-01T00:00:00+00:00"):
    return {"card_key": key, "target_name": name, "org_name": org, "claimed_by": holder,
            "claimed_at": claimed_at if holder else None, "callback_on": callback}


class Sender:
    def __init__(self, fail_for=()):
        self.sent, self.fail_for = [], set(fail_for)

    def __call__(self, to, subject, text, html):
        if to in self.fail_for:
            raise OSError("SMTP said no")
        self.sent.append((to, subject, text, html))


def test_week_start_is_the_monday():
    assert cd.week_start(WED) == date(2026, 11, 16)
    assert cd.week_start(date(2026, 11, 22)) == date(2026, 11, 16)
    assert cd.week_start(date(2026, 11, 23)) == date(2026, 11, 23)


def test_collect_lists_overdue_and_this_weeks_call_backs_per_person():
    digests = {d.email: d for d in cd.collect(FakeClient(), WED)}
    assert sorted(digests) == ["al@kallibr.com.au", "jo@kallibr.com.au"]
    jo = digests["jo@kallibr.com.au"]
    assert [(i.card_name, i.date) for i in jo.overdue] == [("O'Brien & Sons <Pty>", date(2026, 11, 13))]
    assert [(i.card_name, i.date) for i in jo.week] == [("Pat Booker", date(2026, 11, 18)), ("Kim Tran", date(2026, 11, 22))]
    assert [i.card_name for i in digests["al@kallibr.com.au"].week] == ["Al Card"]


def test_render_escapes_names_and_links_to_the_site():
    jo = next(d for d in cd.collect(FakeClient(), WED) if d.email.startswith("jo"))
    subject, text, html = cd.render(jo, WED)
    assert subject == "Your call-backs this week (from Mon 16 Nov)"
    assert "O'Brien & Sons <Pty>" in text and "Overdue" in text
    assert "Later Co" not in text and "Leftover" not in text and "Al Card" not in text
    assert "&lt;Pty&gt;" in html and "<Pty>" not in html and "&amp;" in html
    assert config.SITE_URL in text and config.SITE_URL in html
    assert "Wed 18 Nov" in text and "Sun 22 Nov" in text and "Fri 13 Nov" in text


def test_sends_once_per_week(tmp_path):
    marker, sender = tmp_path / "marker.txt", Sender()
    first = cd.run_digest(FakeClient(), WED, marker, sender)
    assert [s[0] for s in sender.sent] == ["al@kallibr.com.au", "jo@kallibr.com.au"]
    assert "2 sent" in first and marker.read_text().strip() == "2026-11-16"
    second = cd.run_digest(FakeClient(), date(2026, 11, 19), marker, sender)
    assert len(sender.sent) == 2 and "already sent this week" in second


def test_a_missed_monday_sends_on_the_next_run_that_week(tmp_path):
    marker, sender = tmp_path / "marker.txt", Sender()
    marker.write_text("2026-11-09")
    cd.run_digest(FakeClient(), date(2026, 11, 19), marker, sender)
    assert len(sender.sent) == 2 and marker.read_text().strip() == "2026-11-16"


def test_force_resends_and_only_limits_without_touching_the_marker(tmp_path):
    marker, sender = tmp_path / "marker.txt", Sender()
    marker.write_text("2026-11-16")
    summary = cd.run_digest(FakeClient(), WED, marker, sender, force=True, only="JO@kallibr.com.au")
    assert [s[0] for s in sender.sent] == ["jo@kallibr.com.au"] and "1 sent" in summary
    assert marker.read_text().strip() == "2026-11-16"


def test_a_failed_email_is_reported_not_raised(tmp_path):
    sender = Sender(fail_for={"al@kallibr.com.au"})
    summary = cd.run_digest(FakeClient(), WED, tmp_path / "marker.txt", sender)
    assert "1 sent" in summary and "1 failed" in summary


def test_smtp_sender_builds_a_two_part_message():
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, msg):
            sent["msg"] = msg

    send = cd.smtp_sender("sender@gmail.com", "app-password", smtp=FakeSMTP)
    send("jo@kallibr.com.au", "Subject", "plain", "<p>html</p>")
    msg = sent["msg"]
    assert sent["server"] == (config.SMTP_HOST, config.SMTP_PORT) and sent["tls"] and sent["login"] == "sender@gmail.com"
    assert msg["To"] == "jo@kallibr.com.au" and "sender@gmail.com" in msg["From"]
    # a Gmail sender shown with the company's name looks like impersonation to Microsoft 365, so it never uses it
    assert msg["From"].startswith("Refresher call list <") and "kallibr" not in msg["From"].split("<")[0].lower()
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]
