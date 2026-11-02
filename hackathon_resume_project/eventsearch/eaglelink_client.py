"""Polite client for EagleLink's (Campus Labs Engage) undocumented event search API."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import httpx2

from .models import EAGLELINK_BASE_URL, Event, event_url

USER_AGENT = "HackathonResumeProject/0.1 (FGCU student hackathon demo)"
CATEGORY_IDS = {"recruitment": 2648, "training_workshop": 1974, "community_service": 2044}
_BLOCK_TAGS = {"p", "br", "li", "div", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class EventSearchError(RuntimeError):
    """Raised when the EagleLink API or a snapshot file can't be used."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = unescape("".join(parser.parts)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def parse_event(raw: dict) -> Event:
    if not isinstance(raw, dict) or raw.get("id") in (None, "") or not raw.get("name"):
        raise EventSearchError("event is missing 'id' or 'name'")
    return Event(
        id=str(raw["id"]),
        name=str(raw["name"]).strip(),
        description_text=strip_html(raw.get("description")),
        starts_on=raw.get("startsOn") or "",
        ends_on=raw.get("endsOn") or "",
        location=raw.get("location") or "",
        categories=list(raw.get("categoryNames") or []),
        organization=raw.get("organizationName") or "",
        url=event_url(raw["id"]),
    )


def _parse_events(items: list, skip_bad: bool = True) -> list[Event]:
    events = []
    for item in items:
        try:
            events.append(parse_event(item))
        except EventSearchError:
            if not skip_bad:
                raise
    return events


def load_events_file(path) -> list[Event]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = data["value"]
        if not isinstance(items, list):
            raise TypeError("'value' is not a list")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EventSearchError(f"could not read events file {path}: {exc}") from exc
    return _parse_events(items)


class EagleLinkClient:
    def __init__(self, base_url=EAGLELINK_BASE_URL, timeout=15.0, cache_ttl=900,
                 http_client: httpx2.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.cache_ttl = cache_ttl
        self._http = http_client or httpx2.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self._cache: dict[tuple, tuple[float, list[Event]]] = {}

    def _get_page(self, params: dict) -> dict:
        url = f"{self.base_url}/api/discovery/event/search"
        try:
            resp = self._http.get(url, params=params)
        except httpx2.TimeoutException as exc:
            raise EventSearchError(f"EagleLink request timed out: {exc}") from exc
        except httpx2.HTTPError as exc:
            raise EventSearchError(f"EagleLink request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise EventSearchError(f"EagleLink returned HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise EventSearchError("EagleLink returned non-JSON response") from exc
        if not isinstance(body, dict) or not isinstance(body.get("value"), list):
            raise EventSearchError("EagleLink response is missing 'value' list")
        return body

    def search(self, query=None, category_id=None, ends_after: datetime | None = None,
               take=25, max_pages=1) -> list[Event]:
        take = max(1, min(50, int(take)))
        max_pages = max(1, min(3, int(max_pages)))
        ends_after = (ends_after or datetime.now(timezone.utc)).astimezone(timezone.utc)
        hour = ends_after.replace(minute=0, second=0, microsecond=0)
        key = (query, category_id, hour.isoformat(), take, max_pages)

        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return list(cached[1])

        params = {
            "endsAfter": hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "Approved",
            "orderByField": "endsOn",
            "orderByDirection": "ascending",
            "take": take,
        }
        if query:
            params["query"] = query
        if category_id is not None:
            params["categoryIds"] = category_id

        events: list[Event] = []
        for page in range(max_pages):
            body = self._get_page({**params, "skip": page * take})
            items = body["value"]
            events.extend(_parse_events(items))
            total = body.get("@odata.count")
            if len(items) < take or (isinstance(total, int) and (page + 1) * take >= total):
                break

        self._cache[key] = (time.monotonic(), events)
        return list(events)

    def career_events(self, take=25) -> list[Event]:
        merged: dict[str, Event] = {}
        for found in (
            self.search(category_id=CATEGORY_IDS["recruitment"], take=take),
            self.search(query="career", take=take),
        ):
            for event in found:
                merged.setdefault(event.id, event)
        return [e for e in merged.values() if e.categories != ["Community Service"]]
