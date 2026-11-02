"""Fixed interview questions and length-based scoring ported from the team's C++
InterviewSession (InterviewSession.cpp on main, by Jessica Vazquez-Costeno).

Used as the opening question of each interview and as the offline fallback when
no LLM is available, so the Python engine behaves like the C++ one without an API.
Keep these in sync with InterviewSession.cpp.
"""

from __future__ import annotations

TECHNICAL_QUESTIONS = [  # InterviewSession.cpp: targetRole == "Software Engineer"
    "Explain the difference between a stack and a queue.",
    "What is object-oriented programming?",
    "What is the difference between a pointer and a reference?",
    "How would you design a REST API?",
    "Describe a challenging project you worked on.",
]

HR_QUESTIONS = [  # InterviewSession.cpp: any other role
    "Tell me about yourself.",
    "Why are you interested in this position?",
    "Describe a challenge you have overcome.",
    "How do you work in a team environment?",
    "Where do you see yourself in five years?",
]


def questions_for(kind: str) -> list[str]:
    return list(TECHNICAL_QUESTIONS if kind == "technical" else HR_QUESTIONS)


def offline_evaluation(answers: list[str]) -> dict:
    """InterviewSession::evaluateInterview(): 2 points for answers over 100 characters,
    1 point over 50. Returns the C++ InterviewResult fields."""
    score = sum(2 if len(a) > 100 else 1 if len(a) > 50 else 0 for a in answers)
    if score >= 8:
        feedback = "Excellent interview performance."
    elif score >= 5:
        feedback = "Good performance with room for improvement."
    else:
        feedback = "Consider practicing technical explanations."
    return {"totalScore": score, "overallFeedback": feedback, "weakAreas": ["Technical Communication"]}
