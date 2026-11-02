"""Resume-to-event matcher tests; no network (LLM is a fake)."""

import pytest

from ai import LLMError
from eventsearch import Event, match_events, rerank_with_llm
from eventsearch.matcher import resume_terms
from integration import load_resume

RESUME = load_resume({
    "education": [{"degree": "Software Engineering", "institution": "FGCU"}],
    "skills": ["Python", "C++", "SQL"],
    "experience": [{"role": "Warehouse Associate", "description": "SAP operations"}],
})


def event(id, name, description="", categories=(), organization=""):
    return Event(id=str(id), name=name, description_text=description,
                 categories=list(categories), organization=organization,
                 starts_on=f"2026-11-{int(id):02d}T10:00:00+00:00")


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.messages = reply, error, None

    def chat(self, messages, **opts):
        self.messages = messages
        if self.error:
            raise self.error
        return self.reply


def test_resume_terms_split_phrases_and_skip_stopwords():
    terms = resume_terms(RESUME)
    assert terms["software engineering"] == 1.0
    assert terms["software"] == 0.5
    assert "engineering" not in terms
    assert terms["c++"] == 1.0


def test_skill_in_name_outranks_generic_career_event():
    events = [
        event(1, "Resume Workshop", "Bring your resume", ["Training/Workshop"]),
        event(2, "Python and SQL Hack Night", "Build with Python", ["Competition"]),
    ]
    matches = match_events(RESUME, events)
    assert [m.event.id for m in matches] == ["2", "1"]
    assert "python" in matches[0].reasons[0]


def test_term_boundaries():
    events = [event(1, "C++ Study Group"), event(2, "Pythonic snakes exhibit"), event(3, "Ccc meeting")]
    ids = [m.event.id for m in match_events(RESUME, events)]
    assert ids == ["1"]


def test_community_service_only_and_irrelevant_events_dropped():
    events = [
        event(1, "Career beach cleanup", categories=["Community Service"]),
        event(2, "Dance night", categories=["Dance"]),
        event(3, "Career Expo", categories=["Recruitment", "Community Service"]),
    ]
    assert [m.event.id for m in match_events(RESUME, events)] == ["3"]


def test_category_tag_alone_is_weak():
    events = [event(1, "Hatter Tournament", categories=["Recruitment"]),
              event(2, "Career Expo", categories=["Recruitment"])]
    matches = match_events(RESUME, events)
    assert [m.event.id for m in matches] == ["2", "1"]
    assert matches[1].score < 1


def test_top_n_and_tie_break_by_date():
    events = [event(i, "Career talk") for i in (5, 3, 4)]
    matches = match_events(RESUME, events, top_n=2)
    assert [m.event.id for m in matches] == ["3", "4"]


def test_empty_events():
    assert match_events(RESUME, []) == []


def test_rerank_uses_llm_scores_and_ignores_unknown_ids():
    matches = match_events(RESUME, [event(1, "Career Expo"), event(2, "Python Night")])
    reply = ('Sure: [{"id": "1", "score": 9, "reason": "Meet employers."},'
             ' {"id": "99", "score": 10, "reason": "made up"}]')
    client = FakeClient(reply)
    reranked = rerank_with_llm(client, RESUME, matches)
    assert [m.event.id for m in reranked] == ["1", "2"]
    assert reranked[0].reasons == ["Meet employers."]
    assert reranked[1].score == 0.0  # skipped by the model, keeps keyword reasons
    assert reranked[1].reasons
    assert "untrusted data" in client.messages[0]["content"]
    assert "<data>" in client.messages[1]["content"]


def test_rerank_clamps_scores():
    matches = match_events(RESUME, [event(1, "Career Expo")])
    reranked = rerank_with_llm(FakeClient('[{"id": "1", "score": 42}]'), RESUME, matches)
    assert reranked[0].score == 10.0


def test_rerank_unparseable_reply_raises():
    matches = match_events(RESUME, [event(1, "Career Expo")])
    with pytest.raises(LLMError, match="parse"):
        rerank_with_llm(FakeClient("I think the expo is best."), RESUME, matches)


def test_rerank_propagates_api_failure():
    matches = match_events(RESUME, [event(1, "Career Expo")])
    with pytest.raises(LLMError):
        rerank_with_llm(FakeClient(error=LLMError("down")), RESUME, matches)


def test_rerank_empty_matches_skips_llm():
    client = FakeClient("[]")
    assert rerank_with_llm(client, RESUME, []) == []
    assert client.messages is None
