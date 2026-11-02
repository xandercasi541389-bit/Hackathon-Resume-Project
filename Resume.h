#pragma once

#ifndef RESUME_H
#define RESUME_H

#include <string>
#include <vector>
using namespace std;

struct Education {
    string institution;
    string degree;
    string major;
    string graduationDate;
};

struct Experience {
    string company;
    string position;
    string startDate;
    string endDate;
    vector<string> responsibilities;
};

struct Project {
    string name;
    string description;
    vector<string> technologies;
};

struct Resume {
    string fileName;
    string rawText;

    // Personal information
    string name;
    string email;
    string phone;
    string location;
    string summary;

    // Qualifications
    vector<string> skills;
    vector<Education> education;
    vector<Experience> experience;
    vector<Project> projects;
    vector<string> certifications;
};

// Job requirements for comparisons
struct JobPosting {
    string title;
    string description;
    vector<string> requiredSkills;
    vector<string> preferredSkills;
};

// Results of resume evaluation
struct ResumeEvaluation {
    vector<string> strengths;
    vector<string> improvements;
    vector<string> warnings;
};

// Results of job matching
struct JobMatch {
    double skillMatchPercent = 0.0;
    vector<string> matchedSkills;
    vector<string> missingSkills;
};

#endif
