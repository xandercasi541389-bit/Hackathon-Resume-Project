"""EagleLink event search and resume-to-event matching.

The HTTP client lives in eventsearch.eaglelink_client (import it directly).
"""

from .matcher import match_events, rerank_with_llm
from .models import Event, EventMatch, event_url

__all__ = ["Event", "EventMatch", "event_url", "match_events", "rerank_with_llm"]
