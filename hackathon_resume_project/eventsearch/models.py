"""Data shapes shared by the EagleLink client and the resume-to-event matcher."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

EAGLELINK_BASE_URL = "https://getinvolved.fgcu.edu"


def event_url(event_id: str | int) -> str:
    return f"{EAGLELINK_BASE_URL}/event/{event_id}"


@dataclass
class Event:
    id: str
    name: str
    description_text: str = ""  # HTML stripped
    starts_on: str = ""  # ISO 8601 as returned by the API
    ends_on: str = ""
    location: str = ""
    categories: list[str] = field(default_factory=list)
    organization: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EventMatch:
    event: Event
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"event": self.event.to_dict(), "score": self.score, "reasons": self.reasons}
