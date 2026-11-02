#include "InterviewSession.h"

InterviewSession::InterviewSession(
    const std::string& role)
{
    targetRole = role;
    currentQuestion = 0;

    generateQuestions();
}

void InterviewSession::generateQuestions()
{
    questions.clear();

    if (targetRole == "Software Engineer")
    {
        questions.push_back(
            "Explain the difference between a stack and a queue.");

        questions.push_back(
            "What is object-oriented programming?");

        questions.push_back(
            "What is the difference between a pointer and a reference?");

        questions.push_back(
            "How would you design a REST API?");

        questions.push_back(
            "Describe a challenging project you worked on.");
    }
    else
    {
        questions.push_back(
            "Tell me about yourself.");

        questions.push_back(
            "Why are you interested in this position?");

        questions.push_back(
            "Describe a challenge you have overcome.");

        questions.push_back(
            "How do you work in a team environment?");

        questions.push_back(
            "Where do you see yourself in five years?");
    }
}

std::string InterviewSession::getCurrentQuestion() const
{
    if (currentQuestion < questions.size())
    {
        return questions[currentQuestion];
    }

    return "";
}

void InterviewSession::submitAnswer(
    const std::string& answer)
{
    answers.push_back(answer);
    currentQuestion++;
}

bool InterviewSession::hasMoreQuestions() const
{
    return currentQuestion < questions.size();
}

int InterviewSession::getQuestionCount() const
{
    return questions.size();
}

InterviewResult InterviewSession::evaluateInterview()
{
    InterviewResult result;

    int score = 0;

    for (const auto& answer : answers)
    {
        if (answer.length() > 100)
        {
            score += 2;
        }
        else if (answer.length() > 50)
        {
            score += 1;
        }
    }

    result.totalScore = score;

    if (score >= 8)
    {
        result.overallFeedback =
            "Excellent interview performance.";
    }
    else if (score >= 5)
    {
        result.overallFeedback =
            "Good performance with room for improvement.";
    }
    else
    {
        result.overallFeedback =
            "Consider practicing technical explanations.";
    }

    result.weakAreas.push_back(
        "Technical Communication");

    return result;
}