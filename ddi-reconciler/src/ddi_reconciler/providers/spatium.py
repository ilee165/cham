"""SpatiumDDI adapter — the SOURCE OF TRUTH side. Read-only: truth is never
written to by the reconciler.

Endpoint paths *and the pagination envelope* are a per-deployment seam: confirm
against the running stack (`curl -s $BASE/openapi.json`) and adjust the
constants below if the release differs. The adapter reads every page and then
checks the read against whatever count the envelope declared, because a short
read of truth is not a benign truncation here: a desired record that never
arrives is indistinguishable downstream from "this record should not exist",
i.e. a delete order. So an envelope this adapter cannot fully account for is an
error, never a quietly-assumed "that was probably everything".

Malformed payloads are reported as `spatium API error` RuntimeErrors rather
than escaping as KeyError/AttributeError, which would bypass the CLI's 0/1/2
exit-code contract. That includes a truth record the model rejects: it is
*not* skipped, because dropping a record from truth is the delete order above.

Value normalization (IP canonicalization, case, sorting) is CanonicalRecord's
job, not the adapter's.
"""
from __future__ import annotations

import ipaddress
import sys
import urllib.parse

import requests

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord, canonical_name

ZONES_PATH = "/api/v1/dns/zones"
RECORDS_PATH = "/api/v1/dns/zones/{zone_id}/records"

# Envelope seam. A wrapped collection must carry its items under one of
# ITEM_KEYS; the rest describe how to walk to the next page and how to tell
# afterwards whether the walk was complete. A dict body matching none of them
# is an error, not an empty page.
ITEM_KEYS = ("items", "results", "records", "data")
TOTAL_KEYS = ("total", "total_count", "totalCount", "count")
PAGE_COUNT_KEYS = ("pages", "total_pages", "totalPages", "page_count")
PAGE_KEYS = ("page", "page_number", "current_page")
LIMIT_KEYS = ("limit", "size", "per_page", "page_size")
OFFSET_KEYS = ("offset", "skip")
NEXT_KEYS = ("next", "next_url", "next_page", "nextPage", "next_page_url")

_MAX_PAGES = 200
_TIMEOUT = 10


def _first_int(body: dict, keys: tuple[str, ...]) -> int | None:
    """First of `keys` present in `body` with an integer-ish value."""
    for key in keys:
        value = body.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _with_query(url: str, params: dict[str, int]) -> str:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items()})
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _is_loopback(host: str) -> bool:
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


class SpatiumProvider:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
            self._warn_if_plaintext()

    def _warn_if_plaintext(self) -> None:
        """IN-2: the bearer token traverses whatever scheme `base_url` names.
        `http://localhost:8000` is the documented lab setup and stays silent;
        plaintext to anything else puts SPATIUM_API_TOKEN on the wire, so warn
        rather than refuse (refusing would break the documented lab)."""
        parts = urllib.parse.urlsplit(self.base_url)
        if parts.scheme != "http" or _is_loopback((parts.hostname or "").lower()):
            return
        print(f"warning: spatium base_url {self.base_url!r} is plaintext http to a "
              "non-loopback host — SPATIUM_API_TOKEN is sent in the clear on every "
              "request; use https://", file=sys.stderr)

    # ---- HTTP -------------------------------------------------------------

    def _request(self, url: str, path: str):
        try:
            resp = self._session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"spatium API error on {path}: {exc}") from exc
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"spatium API error on {path}: response body is not JSON: {exc}") from exc

    @staticmethod
    def _envelope_items(body: dict, path: str) -> list:
        for key in ITEM_KEYS:
            if key in body:
                value = body[key]
                if not isinstance(value, list):
                    raise RuntimeError(
                        f"spatium API error on {path}: {key!r} is "
                        f"{type(value).__name__}, expected a list")
                return value
        raise RuntimeError(
            f"spatium API error on {path}: unrecognized response envelope with key(s) "
            f"{sorted(body)}; expected one of {list(ITEM_KEYS)} to carry the collection. "
            "Refusing to read it as an empty page — adjust ITEM_KEYS for this deployment.")

    def _same_origin(self, raw, current_url: str, path: str) -> str:
        """Resolve a pagination link, refusing one that leaves `base_url` —
        following it would hand SPATIUM_API_TOKEN to another host."""
        target = urllib.parse.urljoin(current_url, str(raw))
        base = urllib.parse.urlsplit(self.base_url)
        parts = urllib.parse.urlsplit(target)
        if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
            raise RuntimeError(
                f"spatium API error on {path}: pagination link {raw!r} leaves the configured "
                f"base_url {self.base_url!r}; refusing to follow it")
        return target

    def _explicit_next(self, body: dict, current_url: str,
                       path: str) -> tuple[bool, str | None]:
        """(the envelope carries a next-link relation, its resolved URL or None).

        Presence is what matters: a `next` that is explicitly null is the API
        saying "no more pages", and it is authoritative — no page/offset
        guessing on top of it. If it disagrees with a declared total, the
        short-read check below is what fires.
        """
        for container in (body, body.get("links"), body.get("pagination"), body.get("meta")):
            if not isinstance(container, dict):
                continue
            for key in NEXT_KEYS:
                if key in container:
                    value = container[key]
                    return True, (self._same_origin(value, current_url, path)
                                  if value else None)
        return False, None

    def _next_url(self, body: dict, path: str, current_url: str, page_number: int,
                  consumed: int, page_len: int, total: int | None) -> str | None:
        has_link, link = self._explicit_next(body, current_url, path)
        if has_link:
            return link
        # Page-numbered envelope (fastapi-pagination Page: page/pages/size).
        pages = _first_int(body, PAGE_COUNT_KEYS)
        if pages is not None:
            current = _first_int(body, PAGE_KEYS)
            if current is None:
                current = page_number
            return None if current >= pages else _with_query(current_url, {"page": current + 1})
        # Offset/limit envelope (fastapi-pagination LimitOffsetPage), inferred
        # from the declared total: there is more to read and no link to it.
        if total is not None and consumed < total and page_len:
            offset = _first_int(body, OFFSET_KEYS)
            limit = _first_int(body, LIMIT_KEYS)
            return _with_query(current_url, {
                "offset": (consumed - page_len if offset is None else offset) + page_len,
                "limit": page_len if limit is None else limit})
        return None

    def _get(self, path: str) -> list:
        url: str | None = f"{self.base_url}{path}"
        items: list = []
        declared_total: int | None = None
        previous_page: list | None = None
        page_number = 0
        while url is not None:
            page_number += 1
            if page_number > _MAX_PAGES:
                raise RuntimeError(
                    f"spatium API error on {path}: pagination did not terminate after "
                    f"{_MAX_PAGES} pages")
            body = self._request(url, path)
            if isinstance(body, list):  # bare list: no envelope, no paging
                items.extend(body)
                break
            if not isinstance(body, dict):
                raise RuntimeError(
                    f"spatium API error on {path}: expected a JSON list or object, got "
                    f"{type(body).__name__}")
            page_items = self._envelope_items(body, path)
            if page_items and page_items == previous_page:
                raise RuntimeError(
                    f"spatium API error on {path}: pagination did not advance — page "
                    f"{page_number} returned the same items as page {page_number - 1}")
            previous_page = page_items
            items.extend(page_items)
            total = _first_int(body, TOTAL_KEYS)
            if total is not None:
                declared_total = total
            following = self._next_url(body, path, url, page_number, len(items),
                                       len(page_items), declared_total)
            if following == url:
                raise RuntimeError(
                    f"spatium API error on {path}: pagination did not advance — the next "
                    f"page resolves to the URL just read")
            url = following

        if declared_total is not None and len(items) != declared_total:
            raise RuntimeError(
                f"spatium API error on {path}: response declares {declared_total} record(s) "
                f"but the adapter read {len(items)}; refusing a short read of the source of "
                "truth, because a desired record that never arrives reads as a delete order "
                "downstream")
        return items

    # ---- payload access ---------------------------------------------------

    @staticmethod
    def _field(payload, key: str, what: str):
        """Dict access that lands on the CLI's exit-1 contract instead of
        escaping as a bare KeyError/TypeError traceback."""
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"spatium API error: {what} is {type(payload).__name__}, expected an object")
        try:
            return payload[key]
        except KeyError as exc:
            raise RuntimeError(
                f"spatium API error: {what} is missing required field {key!r} "
                f"(field(s) present: {sorted(payload)})") from exc

    @staticmethod
    def _relative(fqdn: str, zone: str) -> str:
        fqdn = canonical_name(fqdn)
        if fqdn == zone:
            return "@"
        if fqdn.endswith("." + zone):
            return fqdn[: -(len(zone) + 1)]
        return fqdn  # already zone-relative

    def fetch_desired(self, zones: set[str]) -> list[CanonicalRecord]:
        wanted = {canonical_name(z) for z in zones}
        grouped: dict[tuple[str, str, str], dict] = {}
        for zone in self._get(ZONES_PATH):
            zone_name = canonical_name(str(self._field(zone, "name", "zone entry")))
            if zone_name not in wanted:
                continue
            zone_id = self._field(zone, "id", f"zone {zone_name!r}")
            for rec in self._get(RECORDS_PATH.format(zone_id=zone_id)):
                what = f"record in zone {zone_name!r}"
                rtype = str(self._field(rec, "type", what)).strip().upper()
                if rtype not in SUPPORTED_RECORD_TYPES:
                    continue
                raw_name = str(self._field(rec, "name", what))
                what = f"record {raw_name}/{rtype} in zone {zone_name!r}"
                value = self._field(rec, "value", what)
                raw_ttl = rec.get("ttl")
                try:
                    ttl = int(raw_ttl) if raw_ttl is not None else 300
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"spatium API error: {what} has a non-integer ttl "
                        f"{raw_ttl!r}") from exc
                entry = grouped.setdefault((zone_name, self._relative(raw_name, zone_name),
                                            rtype), {"values": [], "ttl": ttl})
                entry["values"].append(str(value))

        records: list[CanonicalRecord] = []
        for (zone_name, name, rtype), entry in grouped.items():
            try:
                records.append(CanonicalRecord(zone=zone_name, name=name, rtype=rtype,
                                               values=tuple(entry["values"]), ttl=entry["ttl"]))
            except (TypeError, ValueError) as exc:
                # Not skipped: an unreadable truth record is a record the edge
                # would then be told to delete. Name it and stop.
                raise RuntimeError(
                    f"spatium API error: truth record {zone_name}/{name}/{rtype} is "
                    f"malformed: {exc}. Refusing to drop it — a desired record that never "
                    "arrives reads as a delete order for that key.") from exc
        return records
