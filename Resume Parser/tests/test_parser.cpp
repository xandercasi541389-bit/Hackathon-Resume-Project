// Pattern tests for parseResumeText. Plain checks, non-zero exit on failure.
// Each check has a name saying which pattern it covers; see
// .agent-reports/parser-tests.md for the expectation choices.
#include <chrono>
#include <iostream>
#include <string>
#include <vector>

#include "parser.h"

static int g_checks = 0, g_failed = 0;

static void eq(const std::string& name, const std::string& got, const std::string& want) {
    ++g_checks;
    if (got != want) {
        ++g_failed;
        std::cerr << "FAIL " << name << "\n  got:      [" << got << "]\n  expected: [" << want << "]\n";
    }
}

static void ok(const std::string& name, bool cond, const std::string& detail = "") {
    ++g_checks;
    if (!cond) {
        ++g_failed;
        std::cerr << "FAIL " << name << (detail.empty() ? "" : "\n  " + detail) << "\n";
    }
}

static bool has(const std::string& s, const std::string& sub) { return s.find(sub) != std::string::npos; }

static std::string digits(const std::string& s) {
    std::string d;
    for (char c : s)
        if (c >= '0' && c <= '9') d += c;
    return d;
}

static std::string join(const std::vector<std::string>& v) {
    std::string out;
    for (const auto& s : v) out += (out.empty() ? "[" : " | [") + s + "]";
    return out;
}

static bool listHas(const std::vector<std::string>& v, const std::string& item) {
    for (const auto& s : v)
        if (s == item) return true;
    return false;
}

static Resume parse(const std::string& text) { return parseResumeText(text, "t.txt"); }

// ------------------------------------------------------------------ contact

static void testContact() {
    const std::string tail = "\n\nEducation\nFlorida Gulf Coast University\n";
    // Phone formats. Expectation: the phone field holds the same 10 digits
    // (a leading country code 1 is allowed); formatting is not prescribed.
    struct { const char* label; const char* text; } phones[] = {
        {"phone (239) 555-0100", "(239) 555-0100"},
        {"phone 239.555.0100", "239.555.0100"},
        {"phone +1 239-555-0100", "+1 239-555-0100"},
    };
    for (const auto& p : phones) {
        Resume r = parse(std::string("Jane Doe\n") + p.text + " | jane@fgcu.edu" + tail);
        std::string d = digits(r.phone);
        ok(p.label, d == "2395550100" || d == "12395550100", "got phone [" + r.phone + "]");
        eq(std::string(p.label) + " (email on same line)", r.email, "jane@fgcu.edu");
    }

    Resume m = parse("Jane Doe\nmailto:jane@fgcu.edu\n(239) 555-0100" + tail);
    eq("email mailto: prefix stripped", m.email, "jane@fgcu.edu");

    Resume sep = parse("Jane Doe\nFort Myers, FL | (239) 555-0100 | jane@fgcu.edu | linkedin.com/in/janedoe" + tail);
    eq("contact '|' line: email", sep.email, "jane@fgcu.edu");
    eq("contact '|' line: location", sep.location, "Fort Myers, FL");
    ok("contact '|' line: phone", digits(sep.phone) == "2395550100", "got [" + sep.phone + "]");
    eq("contact '|' line: name", sep.name, "Jane Doe");

    Resume bul = parse("Jane Doe\nFort Myers, FL \xE2\x80\xA2 239-555-0100 \xE2\x80\xA2 jane@fgcu.edu" + tail);
    eq("contact bullet-dot line: email", bul.email, "jane@fgcu.edu");
    eq("contact bullet-dot line: location", bul.location, "Fort Myers, FL");
    ok("contact bullet-dot line: phone", digits(bul.phone) == "2395550100", "got [" + bul.phone + "]");

    Resume nm = parse("Jane Q. Doe\njane@fgcu.edu" + tail);
    eq("name is first line", nm.name, "Jane Q. Doe");

    Resume url = parse("https://github.com/janedoe\nJane Doe\njane@fgcu.edu" + tail);
    ok("URL line not taken as name", !has(url.name, "github") && !has(url.name, "http"),
       "got name [" + url.name + "]");
    eq("name found after URL line", url.name, "Jane Doe");

    Resume url2 = parse("linkedin.com/in/janedoe\nJane Doe\n" + tail);
    ok("bare linkedin URL not taken as name", !has(url2.name, "linkedin"), "got name [" + url2.name + "]");

    Resume loc = parse("Jane Doe\njane@fgcu.edu\nFort Myers, FL" + tail);
    eq("location 'Fort Myers, FL' on own line", loc.location, "Fort Myers, FL");
}

// ----------------------------------------------------------------- headings

static const char* kHdrBody = "Python, C++\n";

static void testHeadings() {
    // Each variant must route "Python, C++" into skills.
    const char* skillHeadings[] = {"SKILLS", "Skills", "Skills:", "Skills & Interests", "TECHNICAL SKILLS",
                                   "Technical Skills:"};
    for (const char* h : skillHeadings) {
        Resume r = parse(std::string("Jane Doe\n\n") + h + "\n" + kHdrBody);
        ok(std::string("skills heading '") + h + "'", listHas(r.skills, "Python") && listHas(r.skills, "C++"),
           "skills: " + join(r.skills));
    }
    const char* expHeadings[] = {"EXPERIENCE", "Work Experience", "WORK EXPERIENCE", "Professional Experience",
                                 "Experience:"};
    for (const char* h : expHeadings) {
        Resume r = parse(std::string("Jane Doe\n\n") + h +
                         "\nSoftware Intern | Arthrex | May 2025 - Aug 2025\n- Wrote code\n");
        ok(std::string("experience heading '") + h + "'",
           r.experience.size() == 1 && r.experience[0].company == "Arthrex",
           "entries: " + std::to_string(r.experience.size()));
    }
    const char* eduHeadings[] = {"EDUCATION", "Education", "Education:"};
    for (const char* h : eduHeadings) {
        Resume r = parse(std::string("Jane Doe\n\n") + h + "\nFlorida Gulf Coast University\n");
        ok(std::string("education heading '") + h + "'",
           r.education.size() == 1 && r.education[0].institution == "Florida Gulf Coast University");
    }

    // Ignored sections must terminate the previous section.
    Resume a = parse("Jane Doe\n\nSkills\nPython, C++\n\nAwards\nDean's List Spring 2024\nHackathon Winner\n");
    ok("Awards stops skills: no award lines in skills",
       !listHas(a.skills, "Hackathon Winner") && !has(join(a.skills), "Dean"), "skills: " + join(a.skills));

    Resume b = parse("Jane Doe\n\nSkills\nPython\n\nActivities\nChess Club, Robotics Team\n");
    ok("Activities stops skills", !listHas(b.skills, "Robotics Team") && !listHas(b.skills, "Chess Club"),
       "skills: " + join(b.skills));

    Resume c = parse("Jane Doe\n\nSkills\nPython\n\nRelevant Coursework\nData Structures, Algorithms\n");
    ok("Relevant Coursework stops skills",
       !listHas(c.skills, "Data Structures") && !listHas(c.skills, "Algorithms"), "skills: " + join(c.skills));

    Resume d = parse("Jane Doe\n\nExperience\nSoftware Intern | Arthrex | May 2025 - Aug 2025\n- Wrote code\n"
                     "\nAwards\n- Dean's List\n- Hackathon Winner\n");
    ok("Awards stops experience: one entry", d.experience.size() == 1, "entries: " + std::to_string(d.experience.size()));
    if (!d.experience.empty())
        ok("Awards stops experience: bullets not absorbed", d.experience[0].responsibilities.size() == 1,
           "responsibilities: " + join(d.experience[0].responsibilities));

    Resume e = parse("Jane Doe\n\nExperience\nSoftware Intern | Arthrex | May 2025 - Aug 2025\n- Wrote code\n"
                     "\nActivities\n- Chess Club\n");
    if (!e.experience.empty())
        ok("Activities stops experience", e.experience[0].responsibilities.size() == 1,
           "responsibilities: " + join(e.experience[0].responsibilities));

    Resume f = parse("Jane Doe\n\nExperience\nSoftware Intern | Arthrex | May 2025 - Aug 2025\n- Wrote code\n"
                     "\nRelevant Coursework\n- Algorithms\n");
    if (!f.experience.empty())
        ok("Relevant Coursework stops experience", f.experience[0].responsibilities.size() == 1,
           "responsibilities: " + join(f.experience[0].responsibilities));
}

// ---------------------------------------------------------------- education

static Education edu1(const std::string& body) {
    Resume r = parse("Jane Doe\n\nEducation\n" + body);
    ok("education parsed an entry for: " + body.substr(0, 40), r.education.size() >= 1);
    return r.education.empty() ? Education{} : r.education[0];
}

static void testEducation() {
    const std::string fgcu = "Florida Gulf Coast University";
    // Expectation for graduationDate: the date text without the word "Expected"
    // (we only require it to contain the month/year, so either form passes).
    {
        Education e = edu1(fgcu + ", Fort Myers, FL \xE2\x80\x94 B.S. Software Engineering, Expected May 2027\n");
        eq("edu pattern 1: institution", e.institution, fgcu);
        eq("edu pattern 1: degree", e.degree, "B.S.");
        eq("edu pattern 1: major", e.major, "Software Engineering");
        ok("edu pattern 1: graduationDate", has(e.graduationDate, "May 2027"), "got [" + e.graduationDate + "]");
    }
    {
        Education e = edu1(fgcu + "          Fort Myers, FL\n"
                           "Bachelor of Science in Software Engineering          Expected May 2027\n");
        eq("edu pattern 2: institution", e.institution, fgcu);
        eq("edu pattern 2: degree", e.degree, "Bachelor of Science");
        eq("edu pattern 2: major", e.major, "Software Engineering");
        ok("edu pattern 2: graduationDate", has(e.graduationDate, "May 2027"), "got [" + e.graduationDate + "]");
    }
    {
        Education e = edu1("Bachelor of Science, Computer Science | " + fgcu + " | May 2026\n");
        eq("edu pattern 3: institution", e.institution, fgcu);
        eq("edu pattern 3: degree", e.degree, "Bachelor of Science");
        eq("edu pattern 3: major", e.major, "Computer Science");
        eq("edu pattern 3: graduationDate", e.graduationDate, "May 2026");
    }
    {
        Education e = edu1("B.S. in Computer Science, " + fgcu + " (Expected 05/2027)\n");
        eq("edu pattern 4: institution", e.institution, fgcu);
        eq("edu pattern 4: degree", e.degree, "B.S.");
        eq("edu pattern 4: major", e.major, "Computer Science");
        ok("edu pattern 4: graduationDate", has(e.graduationDate, "05/2027"), "got [" + e.graduationDate + "]");
    }
    {
        // Year only; no major given -> major stays empty.
        Education e = edu1("Associate of Arts, Miami Dade College, 2022\n");
        eq("edu pattern 7: institution", e.institution, "Miami Dade College");
        eq("edu pattern 7: degree", e.degree, "Associate of Arts");
        eq("edu pattern 7: major", e.major, "");
        eq("edu pattern 7: graduationDate", e.graduationDate, "2022");
    }
    {
        // Range: graduationDate is the END of the range. FGCU is an institution keyword.
        Education e = edu1("BS Computer Science \xE2\x80\x94 FGCU, Aug 2023 \xE2\x80\x93 May 2027\n");
        eq("edu pattern 8: institution", e.institution, "FGCU");
        eq("edu pattern 8: degree", e.degree, "BS");
        eq("edu pattern 8: major", e.major, "Computer Science");
        eq("edu pattern 8: graduationDate", e.graduationDate, "May 2027");
    }
}

// --------------------------------------------------------------- experience

static Experience exp1(const std::string& body, const std::string& label) {
    Resume r = parse("Jane Doe\n\nExperience\n" + body);
    ok(label + ": exactly one entry", r.experience.size() == 1,
       "entries: " + std::to_string(r.experience.size()));
    return r.experience.empty() ? Experience{} : r.experience[0];
}

static void checkExp(const std::string& label, const Experience& x, const std::string& pos,
                     const std::string& co, const std::string& start, const std::string& end) {
    eq(label + ": position", x.position, pos);
    eq(label + ": company", x.company, co);
    eq(label + ": startDate", x.startDate, start);
    eq(label + ": endDate", x.endDate, end);
}

static void testExperience() {
    checkExp("exp pattern 1", exp1("Software Intern | Arthrex | May 2025 \xE2\x80\x93 Aug 2025\n", "exp pattern 1"),
             "Software Intern", "Arthrex", "May 2025", "Aug 2025");

    checkExp("exp pattern 2",
             exp1("Arthrex, Naples, FL                                   May 2025 \xE2\x80\x93 Aug 2025\n"
                  "Software Engineering Intern\n",
                  "exp pattern 2"),
             "Software Engineering Intern", "Arthrex", "May 2025", "Aug 2025");

    {
        // Single date: startDate set; endDate must be empty or equal to startDate.
        Experience x = exp1("Software Engineering Intern\nArthrex \xE2\x80\x94 Naples, FL | Summer 2025\n", "exp pattern 3");
        eq("exp pattern 3: position", x.position, "Software Engineering Intern");
        eq("exp pattern 3: company", x.company, "Arthrex");
        eq("exp pattern 3: startDate", x.startDate, "Summer 2025");
        ok("exp pattern 3: endDate empty or same as start", x.endDate.empty() || x.endDate == "Summer 2025",
           "got [" + x.endDate + "]");
    }

    checkExp("exp pattern 4",
             exp1("Teaching Assistant, Florida Gulf Coast University (Aug 2024 \xE2\x80\x93 Present)\n", "exp pattern 4"),
             "Teaching Assistant", "Florida Gulf Coast University", "Aug 2024", "Present");

    checkExp("exp pattern 5",
             exp1("Barista \xE2\x80\x94 Starbucks, Fort Myers, FL \xE2\x80\x94 06/2023 \xE2\x80\x93 08/2024\n", "exp pattern 5"),
             "Barista", "Starbucks", "06/2023", "08/2024");

    checkExp("exp pattern 6",
             exp1("Research Assistant at FGCU Whitaker Center, Jan 2024 \xE2\x80\x93 Current\n", "exp pattern 6"),
             "Research Assistant", "FGCU Whitaker Center", "Jan 2024", "Current");

    checkExp("exp pattern 10",
             exp1("Software Intern\nMay 2025 \xE2\x80\x93 Aug 2025\nArthrex\n", "exp pattern 10"),
             "Software Intern", "Arthrex", "May 2025", "Aug 2025");

    // Separators.
    checkExp("exp en dash separator",
             exp1("Developer | Acme | Jan 2020 \xE2\x80\x93 Dec 2021\n", "exp en dash"), "Developer", "Acme",
             "Jan 2020", "Dec 2021");
    checkExp("exp 'to' separator", exp1("Developer | Acme | Jan 2020 to Dec 2021\n", "exp to"), "Developer",
             "Acme", "Jan 2020", "Dec 2021");
    checkExp("exp hyphen separator", exp1("Developer | Acme | Jan 2020 - Dec 2021\n", "exp hyphen"), "Developer",
             "Acme", "Jan 2020", "Dec 2021");

    // Right-aligned dates after 3+ spaces on a "Title, Company" line.
    checkExp("exp right-aligned dates",
             exp1("Software Developer, Acme Corp          Jan 2020 \xE2\x80\x93 Dec 2021\n", "exp right-aligned"),
             "Software Developer", "Acme Corp", "Jan 2020", "Dec 2021");

    // Bullet glyphs.
    {
        Experience x = exp1("Developer | Acme | Jan 2020 - Dec 2021\n"
                            "\xE2\x80\xA2 Built the API\n"
                            "\xE2\x97\x8F Wrote the tests\n"
                            "- Deployed to prod\n"
                            "* Mentored interns\n",
                            "exp bullets");
        ok("exp bullets: four responsibilities", x.responsibilities.size() == 4, join(x.responsibilities));
        if (x.responsibilities.size() == 4) {
            eq("exp bullet '\xE2\x80\xA2' stripped", x.responsibilities[0], "Built the API");
            eq("exp bullet '\xE2\x97\x8F' stripped", x.responsibilities[1], "Wrote the tests");
            eq("exp bullet '-' stripped", x.responsibilities[2], "Deployed to prod");
            eq("exp bullet '*' stripped", x.responsibilities[3], "Mentored interns");
        }
    }

    // Wrapped bullet: lowercase continuation joins the previous responsibility.
    {
        Experience x = exp1("Developer | Acme | Jan 2020 - Dec 2021\n"
                            "\xE2\x80\xA2 Built a REST API that serves\n"
                            "  student schedules daily\n"
                            "\xE2\x80\xA2 Fixed bugs\n",
                            "exp wrapped bullet");
        ok("exp wrapped bullet: two responsibilities", x.responsibilities.size() == 2, join(x.responsibilities));
        if (!x.responsibilities.empty())
            eq("exp wrapped bullet: continuation appended", x.responsibilities[0],
               "Built a REST API that serves student schedules daily");
    }

    // Two entries stay separate.
    {
        Resume r = parse("Jane Doe\n\nExperience\n"
                         "Developer | Acme | Jan 2022 - Dec 2022\n- Did a thing\n"
                         "Intern | Beta | Jun 2021 - Aug 2021\n- Did another\n");
        ok("exp two entries", r.experience.size() == 2, "entries: " + std::to_string(r.experience.size()));
        if (r.experience.size() == 2) {
            eq("exp two entries: second company", r.experience[1].company, "Beta");
            ok("exp two entries: one bullet each",
               r.experience[0].responsibilities.size() == 1 && r.experience[1].responsibilities.size() == 1);
        }
    }
}

// ----------------------------------------------------------------- projects

static void testProjects() {
    {
        Resume r = parse("Jane Doe\n\nProjects\nEvent Finder | Python, Flask\n- Matches students to events\n");
        ok("project 'Name | Python, Flask': one project", r.projects.size() == 1);
        if (r.projects.size() == 1) {
            eq("project 'Name | tech': name", r.projects[0].name, "Event Finder");
            ok("project 'Name | tech': technologies", r.projects[0].technologies.size() == 2 &&
                   listHas(r.projects[0].technologies, "Python") && listHas(r.projects[0].technologies, "Flask"),
               join(r.projects[0].technologies));
            eq("project 'Name | tech': bullet -> description", r.projects[0].description,
               "Matches students to events");
        }
    }
    {
        Resume r = parse("Jane Doe\n\nProjects\nResume Parser (C++, SQLite)\n- Extracts fields from resumes\n");
        ok("project 'Name (C++, SQLite)': one project", r.projects.size() == 1);
        if (r.projects.size() == 1) {
            eq("project 'Name (tech)': name", r.projects[0].name, "Resume Parser");
            ok("project 'Name (tech)': technologies", r.projects[0].technologies.size() == 2 &&
                   listHas(r.projects[0].technologies, "C++") && listHas(r.projects[0].technologies, "SQLite"),
               join(r.projects[0].technologies));
            eq("project 'Name (tech)': description", r.projects[0].description, "Extracts fields from resumes");
        }
    }
    {
        Resume r = parse("Jane Doe\n\nProjects\nCampus Map\nTechnologies: React, Node.js, MongoDB\n"
                         "- Interactive map of campus\n- Supports search by building\n");
        ok("project 'Technologies:' line: one project", r.projects.size() == 1,
           "projects: " + std::to_string(r.projects.size()));
        if (r.projects.size() == 1) {
            eq("project 'Technologies:' line: name", r.projects[0].name, "Campus Map");
            ok("project 'Technologies:' line: technologies",
               r.projects[0].technologies.size() == 3 && listHas(r.projects[0].technologies, "React") &&
                   listHas(r.projects[0].technologies, "Node.js") && listHas(r.projects[0].technologies, "MongoDB"),
               join(r.projects[0].technologies));
            eq("project bullets joined with space -> description", r.projects[0].description,
               "Interactive map of campus Supports search by building");
        }
    }
}

// ------------------------------------------------------------ skills & certs

static void testSkillsCerts() {
    {
        Resume r = parse("Jane Doe\n\nSkills\nLanguages: Python, C++\nTools: Git, Docker\n");
        ok("skills 'Languages:' label stripped", listHas(r.skills, "Python") && listHas(r.skills, "C++"),
           join(r.skills));
        ok("skills no label text left", !has(join(r.skills), "Languages") && !has(join(r.skills), "Tools:"),
           join(r.skills));
        ok("skills second labelled line", listHas(r.skills, "Git") && listHas(r.skills, "Docker"), join(r.skills));
    }
    {
        Resume r = parse("Jane Doe\n\nSkills\nPython, python, PYTHON, C++\nc++; Java\n");
        int py = 0, cpp = 0;
        for (const auto& s : r.skills) {
            if (s.size() == 6 && (s[0] == 'p' || s[0] == 'P')) ++py;
            if (s == "C++" || s == "c++") ++cpp;
        }
        ok("skills dedupe case-insensitively: Python once", py == 1, join(r.skills));
        ok("skills dedupe case-insensitively: C++ once", cpp == 1, join(r.skills));
        ok("skills dedupe keeps Java", listHas(r.skills, "Java"), join(r.skills));
    }
    {
        Resume r = parse("Jane Doe\n\nSkills\nPython; Java; SQL\nGit | Docker | Linux\n");
        ok("skills ';' separator", listHas(r.skills, "Python") && listHas(r.skills, "Java") && listHas(r.skills, "SQL"),
           join(r.skills));
        ok("skills '|' separator", listHas(r.skills, "Git") && listHas(r.skills, "Docker") && listHas(r.skills, "Linux"),
           join(r.skills));
    }
    {
        Resume r = parse("Jane Doe\n\nCertifications\nAWS Cloud Practitioner; CompTIA Security+; Google IT Support\n");
        ok("certs one line with ';': three entries", r.certifications.size() == 3, join(r.certifications));
        ok("certs one line with ';': items", listHas(r.certifications, "AWS Cloud Practitioner") &&
               listHas(r.certifications, "CompTIA Security+") && listHas(r.certifications, "Google IT Support"),
           join(r.certifications));
    }
    {
        Resume r = parse("Jane Doe\n\nCertifications\n\xE2\x80\xA2 AWS Cloud Practitioner\n- CompTIA Security+\n"
                         "* Google IT Support\n");
        ok("certs one per bullet: three entries", r.certifications.size() == 3, join(r.certifications));
        ok("certs one per bullet: bullets stripped", listHas(r.certifications, "AWS Cloud Practitioner") &&
               listHas(r.certifications, "CompTIA Security+") && listHas(r.certifications, "Google IT Support"),
           join(r.certifications));
    }
    {
        // A comma can be part of one cert name; commas must not split certifications.
        Resume r = parse("Jane Doe\n\nCertifications\n- Certified Scrum Master, Level 1\n");
        ok("certs commas not split", r.certifications.size() == 1, join(r.certifications));
    }
}

// --------------------------------------------------------------- robustness

static double seconds(std::chrono::steady_clock::time_point t0) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

static void testRobustness() {
    {
        Resume r = parse("");
        ok("empty string: no fields", r.name.empty() && r.email.empty() && r.phone.empty() && r.skills.empty() &&
               r.education.empty() && r.experience.empty() && r.projects.empty() && r.certifications.empty());
        eq("empty string: fileName kept", r.fileName, "t.txt");
    }
    {
        Resume r = parse("Jane Doe\njane@fgcu.edu\n(239) 555-0100\nFort Myers, FL\nI like building software.\n");
        eq("no headings: name", r.name, "Jane Doe");
        eq("no headings: email", r.email, "jane@fgcu.edu");
        ok("no headings: phone", digits(r.phone) == "2395550100", "got [" + r.phone + "]");
        eq("no headings: location", r.location, "Fort Myers, FL");
        ok("no headings: lists empty", r.skills.empty() && r.education.empty() && r.experience.empty());
    }
    {
        Resume r = parse("Jane Doe\r\njane@fgcu.edu\r\n\r\nSkills\r\nPython, C++\r\n\r\nExperience\r\n"
                         "Developer | Acme | Jan 2020 - Dec 2021\r\n- Built things\r\n");
        eq("CRLF: name has no CR", r.name, "Jane Doe");
        eq("CRLF: email has no CR", r.email, "jane@fgcu.edu");
        ok("CRLF: skills", listHas(r.skills, "Python") && listHas(r.skills, "C++"), join(r.skills));
        ok("CRLF: experience", r.experience.size() == 1 && r.experience[0].endDate == "Dec 2021");
        if (!r.experience.empty() && !r.experience[0].responsibilities.empty())
            eq("CRLF: bullet has no CR", r.experience[0].responsibilities[0], "Built things");
    }
    {
        // U+FB01 'fi' ligature must be normalised, in a heading and in content.
        Resume r = parse("Jane Doe\n\nCerti\xEF\xAC\x81" "cations\nAWS Certi\xEF\xAC\x81" "ed Developer\n");
        ok("ligature in heading: Certifications recognised", r.certifications.size() == 1, join(r.certifications));
        if (!r.certifications.empty())
            eq("ligature in content -> 'fi'", r.certifications[0], "AWS Certified Developer");
    }
    {
        // 200 KB of junk, many lines.
        std::string junk;
        unsigned x = 12345;
        while (junk.size() < 200 * 1024) {
            std::string line;
            for (int i = 0; i < 60; ++i) {
                x = x * 1103515245u + 12345u;
                line += static_cast<char>(32 + (x >> 16) % 95);
            }
            junk += line + "\n";
        }
        auto t0 = std::chrono::steady_clock::now();
        Resume r = parse(junk);
        double s = seconds(t0);
        ok("200 KB junk (many lines): finishes in < 10 s", s < 10.0, "took " + std::to_string(s) + " s");
    }
    {
        // 200 KB on one line (regex backtracking hazard).
        std::string one(200 * 1024, 'a');
        for (size_t i = 7; i < one.size(); i += 13) one[i] = ' ';
        auto t0 = std::chrono::steady_clock::now();
        Resume r = parse(one);
        double s = seconds(t0);
        ok("200 KB junk (single line): finishes in < 10 s", s < 10.0, "took " + std::to_string(s) + " s");
    }
    {
        // 200 KB of digits/dates/separators in a Experience section.
        std::string body = "Jane Doe\n\nExperience\n";
        while (body.size() < 200 * 1024) body += "2020 - 2021 | 12/2020 to 05/2021 , , | | 239.555.0100 May\n";
        auto t0 = std::chrono::steady_clock::now();
        Resume r = parse(body);
        double s = seconds(t0);
        ok("200 KB date-like junk in Experience: finishes in < 10 s", s < 10.0, "took " + std::to_string(s) + " s");
    }
}

int main() {
    testContact();
    testHeadings();
    testEducation();
    testExperience();
    testProjects();
    testSkillsCerts();
    testRobustness();

    std::cout << "test_parser: " << (g_checks - g_failed) << "/" << g_checks << " checks passed, " << g_failed
              << " failed\n";
    return g_failed == 0 ? 0 : 1;
}
