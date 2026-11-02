#ifndef INTERVIEW_SESSION_H
#define INTERVIEW_SESSION_H

#include <string>
#include <vector>

struct InterviewResult
{
    int totalScore;
    std::string overallFeedback;
    std::vector<std::string> weakAreas;
};

class InterviewSession
{
private:
    std::string targetRole;

    std::vector<std::string> questions;
    std::vector<std::string> answers;

    int currentQuestion;

public:
    InterviewSession(const std::string& role);

    void generateQuestions();

    std::string getCurrentQuestion() const;

    void submitAnswer(const std::string& answer);

    bool hasMoreQuestions() const;

    InterviewResult evaluateInterview();

    int getQuestionCount() const;
};

#endif