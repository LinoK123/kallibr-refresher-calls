"""Thin PostgREST client for the nightly push (service key). Never logs or prints the key."""
import time

import requests

TIMEOUT = 120
PAGE = 1000


class PushError(Exception):
    pass


class Client:
    """select / insert / update / rpc against <url>/rest/v1. Non-2xx raises PushError.

    Retries follow axc_common.Api.call: 429 honours Retry-After; reads also retry 5xx and
    connection errors. Writes are not retried on 5xx (a half-done insert must fail the run,
    which apply_push's staging count check would catch anyway).
    """

    def __init__(self, url: str, key: str, session=None, retries: int = 5, wait: float = 3.0):
        self.base = url.rstrip("/") + "/rest/v1"
        self.s = session or requests.Session()
        self.s.headers.update({"apikey": key, "Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"})
        self.retries, self.wait = retries, wait

    def _call(self, method, path, **kw):
        read = method == "GET"
        r = None
        for attempt in range(self.retries):
            try:
                r = self.s.request(method, f"{self.base}/{path}", timeout=TIMEOUT, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                if not read or attempt == self.retries - 1:
                    raise PushError(f"{method} {path}: {type(e).__name__}") from None
                time.sleep(self.wait * (attempt + 1))
                continue
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "30")))
                continue
            if read and r.status_code >= 500 and attempt < self.retries - 1:
                time.sleep(self.wait * (attempt + 1))
                continue
            break
        if r is None or not 200 <= r.status_code < 300:
            status = r.status_code if r is not None else "no response"
            body = (r.text or "")[:300] if r is not None else ""
            raise PushError(f"{method} {path} -> {status}: {body}")
        return r

    def select(self, table: str, columns: str, order: str = "id", **filters) -> list[dict]:
        """Every matching row, 1,000 at a time. `filters` are PostgREST filters, e.g. result='eq.ok'."""
        rows, offset = [], 0
        while True:
            params = {"select": columns, **filters, "order": order, "limit": PAGE, "offset": offset}
            batch = self._call("GET", table, params=params).json()
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            offset += PAGE

    def insert(self, table: str, rows: list[dict], returning: bool = False):
        """Insert rows. With returning=True, the inserted rows come back (e.g. to read a new id)."""
        prefer = "return=representation" if returning else "return=minimal"
        r = self._call("POST", table, json=rows, headers={"Prefer": prefer})
        return r.json() if returning else None

    def update(self, table: str, values: dict, **filters) -> None:
        self._call("PATCH", table, params=filters, json=values, headers={"Prefer": "return=minimal"})

    def rpc(self, fn: str, **params):
        r = self._call("POST", f"rpc/{fn}", json=params)
        return r.json() if r.content else None
