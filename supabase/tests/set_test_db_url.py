"""Store the TEST project's Postgres connection string in Windows Credential Manager.

Run:  py supabase/tests/set_test_db_url.py

1. Paste the Session pooler string (hidden prompt). Either with the real password already in it,
   or exactly as Supabase shows it with the [YOUR-...] placeholder left in.
2. Password prompt (hidden): press Enter if the password is already in the string,
   otherwise type the database password (no brackets).
The script tests the connection and saves only if it works. Nothing is printed or written to a file.
The database tests read it from here when REFRESHER_TEST_DB_URL is not set.
"""
import getpass
from urllib.parse import quote, unquote

import keyring

SERVICE, NAME = "kallibr-refresher-test", "db_url"


def _parts(template: str):
    template = template.strip()
    scheme, sep, rest = template.partition("://")
    if scheme not in ("postgres", "postgresql") or not sep:
        raise ValueError("That doesn't look like a postgresql:// connection string.")
    userinfo, at, hostpart = rest.rpartition("@")
    user, _, embedded = userinfo.partition(":")
    if not at or not user or not hostpart:
        raise ValueError("That doesn't look like a Supabase connection string (user@host missing).")
    return user, embedded, hostpart


def _url(user: str, password: str, hostpart: str) -> str:
    url = f"postgresql://{user}:{quote(password, safe='')}@{hostpart}"
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def build_url(template: str, password: str) -> str:
    """Connection string with the password percent-encoded so any character is safe.

    A typed password replaces whatever sits in the password position (Supabase's
    [YOUR-PASSWORD] / [YOUR-DATABASE-PASSWORD] placeholder, or anything else).
    With no typed password, the password already in the pasted string is used.
    """
    return candidate_urls(template, password)[0]


def candidate_urls(template: str, password: str) -> list[str]:
    """Connection strings to try, most likely first."""
    user, embedded, hostpart = _parts(template)
    if password:
        return [_url(user, password, hostpart)]
    if not embedded or (embedded.upper().startswith("[YOUR-") and embedded.endswith("]")):
        raise ValueError("The string still has Supabase's placeholder: type the password at the second prompt.")
    tries = [embedded]
    if unquote(embedded) != embedded:
        tries.append(unquote(embedded))                 # it was already percent-encoded
    if embedded.startswith("[") and embedded.endswith("]"):
        tries.append(embedded[1:-1])                    # placeholder brackets left around it
    return [_url(user, p, hostpart) for p in dict.fromkeys(tries)]


def main():
    template = getpass.getpass("Session pooler connection string (hidden, paste and press Enter): ")
    password = getpass.getpass("Database password (hidden; press Enter if it's already in the string): ")
    try:
        urls = candidate_urls(template, password)
    except ValueError as e:
        raise SystemExit(f"{e} Nothing saved.")
    import psycopg
    last = ""
    for url in urls:
        try:
            psycopg.connect(url, connect_timeout=15).close()
        except psycopg.OperationalError as e:
            last = str(e).splitlines()[0] if str(e) else type(e).__name__
            continue
        keyring.set_password(SERVICE, NAME, url)
        print("Connected OK. Saved to Windows Credential Manager (kallibr-refresher-test / db_url).")
        return
    hint = (" Check the password, or reset it in Supabase: Project Settings > Database > Reset database password."
            if "password authentication failed" in last else "")
    raise SystemExit(f"Could not connect: {last}.{hint} Nothing saved.")


if __name__ == "__main__":
    main()
