from datetime import datetime, timezone
from pathlib import Path

import httpx2
import pytest

from eventsearch.eaglelink_client import (
    CATEGORY_IDS,
    USER_AGENT,
    EagleLinkClient,
    EventSearchError,
    load_events_file,
    parse_event,
    strip_html,
)

SNAPSHOT = Path(__file__).parent.parent / "fixtures" / "sample_events.json"


def raw_event(i, cats=None, **extra):
    return {"id": i, "name": f"Event {i}", "categoryNames": cats or [], **extra}


def make_client(handler, **kw):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    http = httpx2.Client(
        transport=httpx2.MockTransport(wrapped),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    return EagleLinkClient(http_client=http, **kw), calls


def json_handler(events, count=None):
    def handler(request):
        skip = int(request.url.params.get("skip", 0))
        take = int(request.url.params["take"])
        return httpx2.Response(200, json={
            "@odata.count": count if count is not None else len(events),
            "value": events[skip:skip + take],
        })
    return handler


# --- strip_html -----------------------------------------------------------

def test_strip_html_tags_and_entities():
    out = strip_html("<p>Hello&nbsp;<b>World</b> &amp; friends</p><ul><li>One</li><li>Two</li></ul>")
    assert out == "Hello World & friends\nOne\nTwo"


def test_strip_html_br_and_whitespace():
    assert strip_html("a<br/>  b \n\n  c") == "a\nb\nc"


@pytest.mark.parametrize("value", [None, ""])
def test_strip_html_empty(value):
    assert strip_html(value) == ""


# --- parse_event ----------------------------------------------------------

def test_parse_event_full():
    ev = parse_event({
        "id": 123, "name": "Career Fair", "description": "<p>Meet <i>employers</i></p>",
        "startsOn": "2026-11-05T14:00:00+00:00", "endsOn": "2026-11-05T16:00:00+00:00",
        "location": "Student Union", "categoryNames": ["Recruitment"],
        "organizationName": "CDS",
    })
    assert ev.id == "123"
    assert ev.description_text == "Meet employers"
    assert ev.categories == ["Recruitment"]
    assert ev.organization == "CDS"
    assert ev.url == "https://getinvolved.fgcu.edu/event/123"


def test_parse_event_defaults():
    ev = parse_event({"id": "9", "name": "Bare", "categoryNames": None, "organizationName": None})
    assert (ev.description_text, ev.location, ev.starts_on, ev.ends_on) == ("", "", "", "")
    assert ev.categories == [] and ev.organization == ""


@pytest.mark.parametrize("raw", [{"name": "x"}, {"id": 1}, {}])
def test_parse_event_missing_required(raw):
    with pytest.raises(EventSearchError):
        parse_event(raw)


# --- load_events_file -----------------------------------------------------

def test_load_snapshot():
    events = load_events_file(SNAPSHOT)
    assert len(events) == 21
    assert all(e.id and e.name and e.url for e in events)


def test_load_bad_path(tmp_path):
    with pytest.raises(EventSearchError):
        load_events_file(tmp_path / "missing.json")


def test_load_bad_content(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json")
    with pytest.raises(EventSearchError):
        load_events_file(p)
    p.write_text('{"nope": []}')
    with pytest.raises(EventSearchError):
        load_events_file(p)


# --- search ---------------------------------------------------------------

def test_search_params_and_headers():
    client, calls = make_client(json_handler([raw_event(1)]))
    ends = datetime(2026, 11, 2, 15, 42, 7, tzinfo=timezone.utc)
    events = client.search(query="career", category_id=2648, ends_after=ends, take=10)
    assert [e.id for e in events] == ["1"]
    req = calls[0]
    assert req.url.path == "/api/discovery/event/search"
    p = req.url.params
    assert p["endsAfter"] == "2026-11-02T15:00:00Z"
    assert p["status"] == "Approved"
    assert p["orderByField"] == "endsOn"
    assert p["orderByDirection"] == "ascending"
    assert p["take"] == "10" and p["skip"] == "0"
    assert p["query"] == "career" and p["categoryIds"] == "2648"
    assert req.headers["User-Agent"] == USER_AGENT
    assert req.headers["Accept"] == "application/json"


def test_search_omits_optional_params():
    client, calls = make_client(json_handler([]))
    client.search()
    assert "query" not in calls[0].url.params
    assert "categoryIds" not in calls[0].url.params


def test_default_client_headers():
    client = EagleLinkClient()
    assert client._http.headers["User-Agent"] == USER_AGENT
    assert client._http.headers["Accept"] == "application/json"


def test_paging_stops_on_short_page():
    client, calls = make_client(json_handler([raw_event(i) for i in range(1, 6)], count=100))
    events = client.search(take=3, max_pages=3)
    assert len(events) == 5
    assert [c.url.params["skip"] for c in calls] == ["0", "3"]


def test_paging_respects_max_pages_and_count():
    client, calls = make_client(json_handler([raw_event(i) for i in range(1, 11)]))
    assert len(client.search(take=2, max_pages=2)) == 4
    assert len(calls) == 2
    # count exhausted: 4 events, take=2 -> stops after page 2 without a third request
    client, calls = make_client(json_handler([raw_event(i) for i in range(1, 5)]))
    assert len(client.search(take=2, max_pages=3)) == 4
    assert len(calls) == 2


def test_clamping():
    client, calls = make_client(json_handler([raw_event(i) for i in range(200)], count=200))
    client.search(take=500, max_pages=10)
    assert [c.url.params["take"] for c in calls] == ["50"] * 3
    client, calls = make_client(json_handler([raw_event(1)]))
    client.search(take=0, max_pages=0)
    assert calls[0].url.params["take"] == "1" and len(calls) == 1


def test_malformed_event_skipped():
    client, _ = make_client(json_handler([raw_event(1), {"name": "no id"}, raw_event(3)]))
    assert [e.id for e in client.search()] == ["1", "3"]


def test_http_error():
    client, _ = make_client(lambda r: httpx2.Response(500))
    with pytest.raises(EventSearchError, match="500"):
        client.search()


def test_timeout():
    def handler(request):
        raise httpx2.ReadTimeout("slow", request=request)
    client, _ = make_client(handler)
    with pytest.raises(EventSearchError, match="timed out"):
        client.search()


def test_invalid_json_and_missing_value():
    client, _ = make_client(lambda r: httpx2.Response(200, text="<html>"))
    with pytest.raises(EventSearchError, match="non-JSON"):
        client.search()
    client, _ = make_client(lambda r: httpx2.Response(200, json={"items": []}))
    with pytest.raises(EventSearchError, match="value"):
        client.search()


def test_cache_hit_avoids_request():
    client, calls = make_client(json_handler([raw_event(1)]))
    first = client.search(query="x")
    second = client.search(query="x", ends_after=datetime.now(timezone.utc))
    assert [e.id for e in first] == [e.id for e in second]
    assert len(calls) == 1
    client.search(query="y")
    assert len(calls) == 2


def test_cache_expires():
    client, calls = make_client(json_handler([raw_event(1)]), cache_ttl=0)
    client.search()
    client.search()
    assert len(calls) == 2


# --- career_events --------------------------------------------------------

def test_career_events_merge_dedupe_filter():
    def handler(request):
        p = request.url.params
        if p.get("categoryIds") == str(CATEGORY_IDS["recruitment"]):
            value = [raw_event(1, ["Recruitment"]), raw_event(2, ["Recruitment", "Social Event"])]
        else:
            assert p["query"] == "career"
            value = [raw_event(3, ["Community Service"]), raw_event(2, ["Other"]),
                     raw_event(4, ["Community Service", "Training/Workshop"]), raw_event(5)]
        return httpx2.Response(200, json={"@odata.count": len(value), "value": value})

    client, calls = make_client(handler)
    events = client.career_events()
    assert [e.id for e in events] == ["1", "2", "4", "5"]
    assert events[1].categories == ["Recruitment", "Social Event"]  # first wins
    assert len(calls) == 2
