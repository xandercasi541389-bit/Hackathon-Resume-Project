#include "json_writer.h"

#include <cstdio>

namespace {

std::string quote(const std::string& s) {
    std::string out = "\"";
    for (char ch : s) {
        unsigned char c = static_cast<unsigned char>(ch);
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof buf, "\\u%04X", c);
                    out += buf;
                } else {
                    out += ch;
                }
        }
    }
    out += '"';
    return out;
}

std::string pad(int level) { return std::string(static_cast<std::size_t>(level) * 2, ' '); }

void stringField(std::string& o, int lvl, const char* key, const std::string& v, bool last) {
    o += pad(lvl) + quote(key) + ": " + quote(v) + (last ? "\n" : ",\n");
}

void stringArray(std::string& o, int lvl, const char* key, const std::vector<std::string>& v,
                 bool last) {
    o += pad(lvl) + quote(key) + ": ";
    if (v.empty()) {
        o += "[]";
    } else {
        o += "[\n";
        for (std::size_t i = 0; i < v.size(); ++i) {
            o += pad(lvl + 1) + quote(v[i]) + (i + 1 < v.size() ? ",\n" : "\n");
        }
        o += pad(lvl) + "]";
    }
    o += last ? "\n" : ",\n";
}

}  // namespace

std::string toJson(const Resume& r, bool includeRaw) {
    std::string o = "{\n";
    stringField(o, 1, "fileName", r.fileName, false);
    stringField(o, 1, "name", r.name, false);
    stringField(o, 1, "email", r.email, false);
    stringField(o, 1, "phone", r.phone, false);
    stringField(o, 1, "location", r.location, false);
    stringField(o, 1, "summary", r.summary, false);
    stringArray(o, 1, "skills", r.skills, false);

    o += pad(1) + "\"education\": ";
    if (r.education.empty()) {
        o += "[]";
    } else {
        o += "[\n";
        for (std::size_t i = 0; i < r.education.size(); ++i) {
            const Education& e = r.education[i];
            o += pad(2) + "{\n";
            stringField(o, 3, "institution", e.institution, false);
            stringField(o, 3, "degree", e.degree, false);
            stringField(o, 3, "major", e.major, false);
            stringField(o, 3, "graduationDate", e.graduationDate, true);
            o += pad(2) + (i + 1 < r.education.size() ? "},\n" : "}\n");
        }
        o += pad(1) + "]";
    }
    o += ",\n";

    o += pad(1) + "\"experience\": ";
    if (r.experience.empty()) {
        o += "[]";
    } else {
        o += "[\n";
        for (std::size_t i = 0; i < r.experience.size(); ++i) {
            const Experience& e = r.experience[i];
            o += pad(2) + "{\n";
            stringField(o, 3, "company", e.company, false);
            stringField(o, 3, "position", e.position, false);
            stringField(o, 3, "startDate", e.startDate, false);
            stringField(o, 3, "endDate", e.endDate, false);
            stringArray(o, 3, "responsibilities", e.responsibilities, true);
            o += pad(2) + (i + 1 < r.experience.size() ? "},\n" : "}\n");
        }
        o += pad(1) + "]";
    }
    o += ",\n";

    o += pad(1) + "\"projects\": ";
    if (r.projects.empty()) {
        o += "[]";
    } else {
        o += "[\n";
        for (std::size_t i = 0; i < r.projects.size(); ++i) {
            const Project& p = r.projects[i];
            o += pad(2) + "{\n";
            stringField(o, 3, "name", p.name, false);
            stringField(o, 3, "description", p.description, false);
            stringArray(o, 3, "technologies", p.technologies, true);
            o += pad(2) + (i + 1 < r.projects.size() ? "},\n" : "}\n");
        }
        o += pad(1) + "]";
    }
    o += ",\n";

    stringArray(o, 1, "certifications", r.certifications, !includeRaw);
    if (includeRaw) stringField(o, 1, "rawText", r.rawText, true);
    o += "}\n";
    return o;
}
