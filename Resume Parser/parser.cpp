// Heuristic resume text -> Resume parser. No external libraries.
//
// Pipeline: normalise text -> split two-column layouts -> split into trimmed
// lines -> route each line to the current section -> parse each section.
// Contact details come from the lines before the first heading (or a
// "Contact" section). Every rule is intentionally simple; unknown content is
// skipped rather than guessed.

#include "parser.h"

#include <algorithm>
#include <cctype>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <utility>

namespace {

enum class Section { Header, Contact, Summary, Education, Experience, Skills, Projects, Certifications, Ignored };

struct Line {
    std::string text;
    bool bullet;
};

// ---------------------------------------------------------------- text utils

std::string trim(const std::string& s) {
    const char* ws = " \t\n\r\f\v";
    size_t b = s.find_first_not_of(ws);
    if (b == std::string::npos) return "";
    size_t e = s.find_last_not_of(ws);
    return s.substr(b, e - b + 1);
}

std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

void replaceAll(std::string& s, const std::string& from, const std::string& to) {
    for (size_t pos = 0; (pos = s.find(from, pos)) != std::string::npos; pos += to.size())
        s.replace(pos, from.size(), to);
}

// Map typographic characters from PDF/DOCX extraction onto ASCII equivalents.
std::string normalise(std::string text) {
    replaceAll(text, "\r\n", "\n");
    replaceAll(text, "\r", "\n");
    replaceAll(text, "\f", "\n");
    replaceAll(text, "\t", "   ");
    replaceAll(text, "\xC2\xA0", " ");          // no-break space
    replaceAll(text, "\xE2\x80\x8B", "");       // zero-width space
    replaceAll(text, "\xE2\x80\x93", "-");      // en dash
    replaceAll(text, "\xE2\x80\x94", "-");      // em dash
    replaceAll(text, "\xE2\x80\x98", "'");      // curly single quotes
    replaceAll(text, "\xE2\x80\x99", "'");
    replaceAll(text, "\xE2\x80\x9C", "\"");     // curly double quotes
    replaceAll(text, "\xE2\x80\x9D", "\"");
    replaceAll(text, "\xEF\xAC\x80", "ff");     // ligatures
    replaceAll(text, "\xEF\xAC\x81", "fi");
    replaceAll(text, "\xEF\xAC\x82", "fl");
    replaceAll(text, "\xEF\xAC\x83", "ffi");
    replaceAll(text, "\xEF\xAC\x84", "ffl");
    return text;
}

// Bullet glyphs seen in extracted resumes; checked at the start of a line.
const std::vector<std::string> kBullets = {
    "\xE2\x80\xA2", "\xE2\x97\x8F", "\xE2\x96\xAA", "\xE2\x96\xA0", "\xE2\x97\xA6", "\xE2\x96\xBA",
    "\xE2\x9E\xA2", "\xEF\x82\xB7", "\xEF\x82\xA7", "\xE2\x80\xA3", "\xE2\x81\x83", "- ", "* ", "o ", "> "};

bool stripBullet(std::string& line) {
    for (const auto& b : kBullets) {
        if (line.compare(0, b.size(), b) == 0) {
            line = trim(line.substr(b.size()));
            return true;
        }
    }
    return false;
}

std::vector<std::string> splitAny(const std::string& s, const std::vector<std::string>& seps) {
    std::vector<std::string> out;
    size_t start = 0;
    while (start <= s.size()) {
        size_t best = std::string::npos, bestLen = 0;
        for (const auto& sep : seps) {
            size_t p = s.find(sep, start);
            if (p < best) { best = p; bestLen = sep.size(); }
        }
        std::string part = trim(s.substr(start, best == std::string::npos ? std::string::npos : best - start));
        if (!part.empty()) out.push_back(part);
        if (best == std::string::npos) break;
        start = best + bestLen;
    }
    return out;
}

bool startsLower(const std::string& s) {
    return !s.empty() && std::islower(static_cast<unsigned char>(s[0]));
}

size_t wordCount(const std::string& s) {
    std::istringstream in(s);
    std::string w;
    size_t n = 0;
    while (in >> w) ++n;
    return n;
}

void appendSentence(std::string& target, const std::string& text) {
    if (text.empty()) return;
    target += (target.empty() ? "" : " ") + text;
}

// Remove empty brackets and separators left behind after cutting out dates/locations.
std::string clean(std::string s) {
    // Keeps runs of 3+ spaces: they separate right-aligned fields until the line is split.
    s = std::regex_replace(s, std::regex("\\(\\s*\\)|\\[\\s*\\]"), "");
    const std::string junk = " \t,;|-:/";
    size_t b = s.find_first_not_of(junk);
    if (b == std::string::npos) return "";
    size_t e = s.find_last_not_of(junk);
    return s.substr(b, e - b + 1);
}

void pushUnique(std::vector<std::string>& v, std::set<std::string>& seen, const std::string& item) {
    std::string t = trim(item);
    while (!t.empty() && (t.back() == '.' || t.back() == ',')) t.pop_back();
    if (!t.empty() && seen.insert(lower(t)).second) v.push_back(t);
}

// ---------------------------------------------------------------- patterns

const std::string kMonth =
    "(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    "sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\\.?,?";
const std::string kSeason = "(?:spring|summer|fall|autumn|winter)";
const std::string kDate =
    "(?:" + kMonth + "\\s+\\d{4}|" + kSeason + "\\s+'?\\d{2,4}|\\d{1,2}/\\d{4}|\\b(?:19|20)\\d{2}\\b)";
const std::regex kDateRange(
    "(" + kDate + ")\\s*(?:-|to|~)\\s*(" + kDate + "|present|current|now|ongoing)", std::regex::icase);
const std::regex kSingleDate(
    "(?:(?:expected|anticipated|exp\\.)\\s+)?" + kDate + "(?:\\s*\\((?:expected|anticipated)\\))?",
    std::regex::icase);
const std::regex kGraduatedPrefix("^(?:graduated|graduating|class of)\\s+", std::regex::icase);
const std::regex kEmail("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}");
const std::regex kPhone("(?:\\+?1[\\s.-]?)?(?:\\(\\d{3}\\)|\\d{3})[\\s.-]?\\d{3}[\\s.-]?\\d{4}(?!\\d)");
const std::regex kUrl("(?:https?://|www\\.|linkedin\\.com|github\\.com)\\S*", std::regex::icase);

const std::string kStateCodes =
    "AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|"
    "NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY";
const std::string kStateNames =
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|"
    "Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|"
    "Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    "New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
    "South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|"
    "Wisconsin|Wyoming";
// "City, ST" or "City, State", optionally followed by a ZIP code.
const std::string kCityState =
    "([A-Z][A-Za-z.']*(?: [A-Z][A-Za-z.']*){0,3}),\\s*(" + kStateCodes + "|" + kStateNames +
    ")\\b(?! +[A-Z][a-z])(?:\\s+\\d{5}(?:-\\d{4})?)?";  // not "Florida Gulf Coast University"
const std::regex kLocationSearch(kCityState);
const std::regex kLocationOnly("^" + kCityState + "$");
const std::regex kLocationInText("(?:,\\s*|\\s+-\\s+|\\s*\\|\\s*)?\\b" + kCityState);

const std::regex kInstitution(
    "\\b(?:university|college|institute|school|academy|polytechnic|FGCU|UCF|USF|FIU|FAU|FSU|UNF|UWF|"
    "UF|MIT)\\b",
    std::regex::icase);
const std::regex kDegree(
    "\\b(?:bachelor(?:'?s)?|master(?:'?s)?|associate(?:'?s)?|doctor(?:ate)?|ph\\.?d\\.?|bsc|bba|mba|"
    "b\\.s\\.?|b\\.a\\.?|m\\.s\\.?|m\\.a\\.?|a\\.a\\.?|a\\.s\\.?|bs|ba|ms|aa|"
    "high school diploma|diploma)(?=[\\s,.]|$)",
    std::regex::icase);
const std::regex kPositionWord(
    "\\b(?:intern|engineer|developer|programmer|assistant|analyst|associate|manager|technician|tutor|"
    "representative|specialist|coordinator|cashier|barista|server|clerk|lead|director|consultant|"
    "president|vice president|treasurer|secretary|officer|researcher|scientist|designer|administrator|"
    "supervisor|agent|mentor|instructor|teacher|founder|chair|volunteer|advisor|ambassador)s?\\b",
    std::regex::icase);
const std::regex kLabelPrefix("^([A-Za-z&/ ]{2,30}):\\s*(.*)$");

bool isLocationOnly(const std::string& s) { return std::regex_match(s, kLocationOnly); }

std::string removeLocation(const std::string& s) { return std::regex_replace(s, kLocationInText, ""); }

// ---------------------------------------------------------------- headings

const std::map<std::string, Section>& headingTable() {
    static const std::map<std::string, Section> table = [] {
        std::map<std::string, Section> t;
        auto add = [&t](Section s, std::initializer_list<const char*> keys) {
            for (const char* k : keys) t[k] = s;
        };
        add(Section::Contact, {"contact", "contact information", "contact info"});
        add(Section::Summary, {"summary", "professional summary", "career summary", "summary of qualifications",
                               "objective", "career objective", "profile", "professional profile", "about",
                               "about me"});
        add(Section::Education, {"education", "academic background", "academics", "educational background",
                                 "education and training"});
        add(Section::Experience, {"experience", "work experience", "professional experience",
                                  "relevant experience", "related experience", "employment",
                                  "employment history", "work history", "internships", "internship experience",
                                  "leadership experience", "research experience"});
        add(Section::Skills, {"skills", "technical skills", "core skills", "key skills", "skills and interests",
                              "skills and tools", "computer skills", "core competencies", "technologies",
                              "technical proficiencies", "tools"});
        add(Section::Projects, {"projects", "academic projects", "personal projects", "selected projects",
                                "relevant projects", "technical projects", "project experience"});
        add(Section::Certifications, {"certifications", "certificates", "licenses", "licenses and certifications",
                                      "certifications and licenses", "professional certifications",
                                      "certifications and training", "certifications and awards"});
        // Recognised so their content isn't attributed to the previous section.
        add(Section::Ignored, {"awards", "honors", "honors and awards", "awards and honors",
                               "awards and achievements", "activities", "extracurricular activities",
                               "extracurriculars", "campus involvement", "involvement", "leadership",
                               "leadership and activities", "volunteer", "volunteer experience", "volunteering",
                               "community service", "references", "relevant coursework", "coursework",
                               "interests", "hobbies", "languages", "publications", "affiliations",
                               "memberships", "professional affiliations"});
        return t;
    }();
    return table;
}

std::string headingKey(const std::string& line) {
    std::string key;
    for (char c : lower(line)) {
        if (std::isalpha(static_cast<unsigned char>(c)) || c == ' ') key += c;
        else if (c == '&') key += " and ";
    }
    std::istringstream words(key);
    std::string word, out;
    while (words >> word) out += (out.empty() ? "" : " ") + word;
    return out;
}

bool isHeadingText(const std::string& s) {
    return s.size() <= 45 && s.find(',') == std::string::npos && headingTable().count(headingKey(s));
}

// Returns true if `line` is a section heading. "Skills: Python, C++" also counts;
// the text after the colon is returned in `rest`.
bool matchHeading(const std::string& line, Section& section, std::string& rest) {
    rest.clear();
    if (line.size() > 45) return false;
    const auto& table = headingTable();
    if (isHeadingText(line)) {
        section = table.at(headingKey(line));
        return true;
    }
    // Inline form only for top-level names: "Languages:" or "Technologies:" are
    // sub-labels inside a section, not new sections.
    static const std::set<std::string> inlineHeadings = {
        "skills", "technical skills", "certifications", "summary", "objective"};
    std::smatch m;
    if (std::regex_match(line, m, kLabelPrefix) && inlineHeadings.count(headingKey(m[1])) &&
        !trim(m[2]).empty()) {
        section = table.at(headingKey(m[1]));
        rest = trim(m[2]);
        return true;
    }
    return false;
}

// ---------------------------------------------------------------- two columns

// pdftotext -layout puts a sidebar and the main column on the same lines. If a
// heading appears after a 3+ space gap, cut every line at that column and emit
// the left column first, then the right one.
std::string splitColumns(const std::string& text) {
    std::vector<std::string> lines;
    std::istringstream in(text);
    for (std::string l; std::getline(in, l);) lines.push_back(l);

    size_t column = 0;
    static const std::regex gap(" {3,}(\\S)");
    for (const auto& l : lines) {
        for (auto it = std::sregex_iterator(l.begin(), l.end(), gap); it != std::sregex_iterator(); ++it) {
            size_t pos = static_cast<size_t>(it->position(1));
            std::string right = trim(l.substr(pos));
            size_t nextGap = right.find("   ");
            if (nextGap != std::string::npos) right = right.substr(0, nextGap);
            if (!trim(l.substr(0, pos)).empty() && isHeadingText(right)) {
                column = pos;
                break;
            }
        }
        if (column) break;
    }
    if (!column) return text;

    std::string left, right;
    for (const auto& l : lines) {
        // Only cut where the line actually has a gap at the column.
        bool cut = l.size() > column && column >= 3 && l.compare(column - 3, 3, "   ") == 0;
        left += trim(cut ? l.substr(0, column) : l) + "\n";
        if (cut) right += trim(l.substr(column)) + "\n";
    }
    return left + "\n" + right;
}

// ---------------------------------------------------------------- dates

struct Dates {
    std::string start, end;
};

// Cut the first date range (or single date) out of `s`.
Dates takeDates(std::string& s) {
    Dates d;
    std::smatch m;
    if (std::regex_search(s, m, kDateRange)) {
        d.start = trim(m[1]);
        d.end = trim(m[2]);
        s = m.prefix().str() + " " + m.suffix().str();
    } else if (std::regex_search(s, m, kSingleDate)) {
        d.start = trim(m.str());
        s = m.prefix().str() + " " + m.suffix().str();
    }
    // A "Graduated"/"Class of" left just before the cut belongs to the date.
    s = std::regex_replace(s, std::regex("\\b(?:graduated|graduating|class of)\\s*$", std::regex::icase), "");
    s = clean(s);
    return d;
}

// ---------------------------------------------------------------- sections

void parseContact(const std::vector<std::string>& lines, Resume& r) {
    for (const auto& line : lines) {
        std::smatch m;
        if (r.email.empty() && std::regex_search(line, m, kEmail)) r.email = m.str();
        if (r.phone.empty() && std::regex_search(line, m, kPhone)) r.phone = trim(m.str());
        if (r.location.empty()) {
            for (const auto& part : splitAny(line, {"|", "   ", "\xE2\x80\xA2", "\xC2\xB7", " - "})) {
                if (std::regex_search(part, kEmail) || std::regex_search(part, kUrl)) continue;
                if (std::regex_search(part, m, kLocationSearch)) {
                    r.location = m[1].str() + ", " + m[2].str();
                    break;
                }
            }
        }
    }
    static const std::set<std::string> notNames = {"resume", "curriculum vitae", "cv"};
    for (const auto& line : lines) {
        std::string first = splitAny(line, {"|", "   ", "\xE2\x80\xA2"}).front();
        if (std::regex_search(first, kEmail) || std::regex_search(first, kPhone) ||
            std::regex_search(first, kUrl) || isLocationOnly(first) || isHeadingText(first) ||
            notNames.count(headingKey(first)) || std::regex_search(first, std::regex("\\d")))
            continue;
        r.name = first;
        break;
    }
}

void parseList(const std::string& line, std::vector<std::string>& out, std::set<std::string>& seen,
               bool splitComma) {
    std::string text = line;
    std::smatch m;
    if (std::regex_match(text, m, kLabelPrefix) && wordCount(m[1]) <= 4) text = m[2];  // "Languages: Python"
    std::vector<std::string> seps = {";", "|", "\xE2\x80\xA2", "\xC2\xB7", "   "};
    if (splitComma) seps.push_back(",");
    for (const auto& item : splitAny(text, seps)) {
        if (std::regex_match(item, std::regex("\\(?\\d{4}\\)?"))) continue;  // stray year
        if (splitComma && item.size() > 40) continue;                        // a sentence, not a skill
        pushUnique(out, seen, item);
    }
}

void parseEducationLine(std::string line, std::vector<Education>& out) {
    if (std::regex_search(line, std::regex("^(?:relevant )?coursework|^gpa|^honors|^minor|^concentration",
                                           std::regex::icase)))
        return;
    Dates d = takeDates(line);
    std::string date = d.end.empty() ? d.start : d.end;  // graduation = end of a range
    Education* touched = nullptr;
    bool degreeHere = false;
    for (const auto& seg : splitAny(line, {" | ", "|", " - ", "   ", ", "})) {
        std::string text = clean(seg);
        bool hasDegree = std::regex_search(text, kDegree);
        bool hasInst = !hasDegree && std::regex_search(text, kInstitution);
        if (hasInst || hasDegree) {
            bool fresh = out.empty() || (hasInst && !out.back().institution.empty()) ||
                         (hasDegree && !out.back().degree.empty());
            if (fresh) out.emplace_back();
        } else if (degreeHere && touched && touched->major.empty() && !isLocationOnly(text) &&
                   !std::regex_search(text, std::regex("gpa", std::regex::icase))) {
            touched->major = text;  // "Bachelor of Science, Computer Science"
            continue;
        } else {
            continue;
        }
        Education& e = out.back();
        touched = &e;
        if (hasInst) {
            e.institution = text;
            continue;
        }
        degreeHere = true;
        std::smatch m;
        std::regex_search(text, m, kDegree);
        std::string degree = m.str(), after = trim(m.suffix().str());
        std::string lowAfter = lower(after);
        if (lowAfter.rfind("of ", 0) == 0) {  // "Bachelor of Science in X"
            size_t in = lowAfter.find(" in ");
            e.degree = trim(degree + " " + after.substr(0, in));
            if (in != std::string::npos) e.major = clean(after.substr(in + 4));
        } else {
            e.degree = degree;
            e.major = clean(lowAfter.rfind("in ", 0) == 0 ? after.substr(3) : after);
        }
    }
    if (!date.empty()) {
        if (!touched && !out.empty()) touched = &out.back();
        if (touched && touched->graduationDate.empty())
            touched->graduationDate = std::regex_replace(date, kGraduatedPrefix, "");
    }
}

// Turn the non-bullet header lines of one entry into position/company/dates.
Experience buildExperience(const std::vector<std::string>& header) {
    Experience x;
    std::vector<std::string> fields;
    for (std::string line : header) {
        Dates d = takeDates(line);
        if (x.startDate.empty() && !d.start.empty()) {
            x.startDate = d.start;
            x.endDate = d.end;
        }
        line = clean(removeLocation(line));
        std::vector<std::string> parts = splitAny(line, {" | ", "|", " - ", "   ", " @ ", " at ", ", "});
        for (auto& p : parts) {
            p = clean(p);
            if (!p.empty() && !isLocationOnly(p) && !std::regex_match(p, std::regex(kStateCodes)))
                fields.push_back(p);
        }
    }
    // Prefer the field that reads like a job title as the position.
    auto isTitle = [](const std::string& f) { return std::regex_search(f, kPositionWord); };
    auto title = std::find_if(fields.begin(), fields.end(), isTitle);
    if (title != fields.end() && title != fields.begin() && !isTitle(fields.front())) {
        x.position = *title;
        fields.erase(title);
        if (!fields.empty()) x.company = fields.front();
    } else {
        if (!fields.empty()) x.position = fields[0];
        if (fields.size() > 1) x.company = fields[1];
    }
    return x;
}

bool hasDate(const std::string& s) { return std::regex_search(s, kSingleDate); }

void parseExperience(const std::vector<Line>& lines, std::vector<Experience>& out) {
    std::vector<std::string> header;
    bool headerHasDate = false, lastWasBullet = false;
    auto flush = [&]() {
        if (!header.empty()) out.push_back(buildExperience(header));
        header.clear();
        headerHasDate = false;
    };
    for (const auto& [text, bullet] : lines) {
        if (bullet) {
            flush();
            if (out.empty()) out.emplace_back();
            out.back().responsibilities.push_back(text);
            lastWasBullet = true;
            continue;
        }
        // A wrapped bullet continues in lowercase.
        if (lastWasBullet && startsLower(text) && !out.empty() && !out.back().responsibilities.empty()) {
            appendSentence(out.back().responsibilities.back(), text);
            continue;
        }
        lastWasBullet = false;
        if (isLocationOnly(text)) continue;  // "Naples, FL" on its own line
        // Entries without bullets: a second dated line starts the next entry.
        if (headerHasDate && hasDate(text)) flush();
        header.push_back(text);
        headerHasDate = headerHasDate || hasDate(text);
    }
    flush();
}

void parseProjects(const std::vector<Line>& lines, std::vector<Project>& out) {
    static const std::regex techLine("^(?:technologies|tech stack|tech|tools|built with)\\s*:\\s*(.*)$",
                                     std::regex::icase);
    for (const auto& [line, bullet] : lines) {
        std::smatch m;
        if (std::regex_match(line, m, techLine)) {
            if (out.empty()) out.emplace_back();
            std::set<std::string> seen;
            for (const auto& t : out.back().technologies) seen.insert(lower(t));
            parseList(m[1], out.back().technologies, seen, true);
            continue;
        }
        bool plain = line.find('|') == std::string::npos && line.find('(') == std::string::npos &&
                     line.find(" - ") == std::string::npos;
        // A plain line under a "Name | tech" header, or one that reads like a sentence, is a description.
        bool plainSentence = plain && (line.back() == '.' || wordCount(line) > 6 ||
                                       (!out.empty() && !out.back().technologies.empty()));
        if (bullet || (!out.empty() && (startsLower(line) || (out.back().description.empty() && plainSentence)))) {
            if (out.empty()) out.emplace_back();
            appendSentence(out.back().description, line);
            continue;
        }
        Project p;
        std::string text = line;
        takeDates(text);
        std::string rest;
        std::smatch paren;
        if (std::regex_search(text, paren, std::regex("\\(([^)]*)\\)\\s*$"))) {  // "Name (C++, SQLite)"
            rest = paren[1];
            text = clean(paren.prefix().str());
        }
        std::vector<std::string> parts = splitAny(text, {" | ", "|", " - ", ": "});
        if (!parts.empty()) p.name = clean(parts[0]);
        if (parts.size() > 1 && rest.empty()) rest = parts[1];
        // A short comma list reads as technologies; a sentence reads as a description.
        if (!rest.empty()) {
            if (rest.find(',') != std::string::npos || wordCount(rest) <= 3) {
                std::set<std::string> seen;
                parseList(rest, p.technologies, seen, true);
            } else {
                p.description = rest;
            }
        }
        out.push_back(p);
    }
}

}  // namespace

Resume parseResumeText(const std::string& text, const std::string& fileName) {
    Resume r;
    r.fileName = fileName;
    r.rawText = text;

    std::vector<std::string> contact;
    std::vector<Line> experience, projects;
    std::set<std::string> skillSeen, certSeen;
    Section section = Section::Header;

    std::istringstream in(splitColumns(normalise(text)));
    std::string raw;
    while (std::getline(in, raw)) {
        std::string line = trim(raw);
        if (line.empty()) continue;

        Section next;
        std::string rest;
        if (matchHeading(line, next, rest)) {
            section = next;
            if (rest.empty()) continue;
            line = rest;
        }
        bool bullet = stripBullet(line);
        if (line.empty()) continue;

        switch (section) {
            case Section::Header:
            case Section::Contact: contact.push_back(line); break;
            case Section::Summary: appendSentence(r.summary, line); break;
            case Section::Education: parseEducationLine(line, r.education); break;
            case Section::Experience: experience.push_back({line, bullet}); break;
            case Section::Skills: parseList(line, r.skills, skillSeen, true); break;
            case Section::Projects: projects.push_back({line, bullet}); break;
            case Section::Certifications: parseList(line, r.certifications, certSeen, false); break;
            case Section::Ignored: break;
        }
    }
    parseContact(contact, r);
    parseExperience(experience, r.experience);
    parseProjects(projects, r.projects);
    return r;
}
