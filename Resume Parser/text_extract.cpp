#include "text_extract.h"

#include <cctype>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <vector>

#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {

const int kExecNotFound = 127;

std::string lowerExtension(const std::string& path) {
    std::size_t slash = path.find_last_of('/');
    std::size_t dot = path.find_last_of('.');
    if (dot == std::string::npos || (slash != std::string::npos && dot < slash)) {
        return "";
    }
    std::string ext = path.substr(dot);
    for (char& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return ext;
}

std::string normaliseNewlines(const std::string& in) {
    std::string out;
    out.reserve(in.size());
    for (std::size_t i = 0; i < in.size(); ++i) {
        if (in[i] == '\r') {
            out += '\n';
            if (i + 1 < in.size() && in[i + 1] == '\n') ++i;
        } else {
            out += in[i];
        }
    }
    return out;
}

bool fileReadable(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    return f.good();
}

// Run argv without a shell, capturing stdout. stderr goes to /dev/null.
// Returns the exit status; 127 if the program could not be executed.
int runCapture(const std::vector<std::string>& args, std::string& output) {
    int fds[2];
    if (pipe(fds) != 0) throw std::runtime_error("pipe() failed");

    pid_t pid = fork();
    if (pid < 0) {
        close(fds[0]);
        close(fds[1]);
        throw std::runtime_error("fork() failed");
    }
    if (pid == 0) {
        close(fds[0]);
        dup2(fds[1], STDOUT_FILENO);
        close(fds[1]);
        int devnull = open("/dev/null", O_WRONLY);
        if (devnull >= 0) {
            dup2(devnull, STDERR_FILENO);
            close(devnull);
        }
        std::vector<char*> argv;
        for (const std::string& a : args) argv.push_back(const_cast<char*>(a.c_str()));
        argv.push_back(nullptr);
        execvp(argv[0], argv.data());
        _exit(kExecNotFound);
    }

    close(fds[1]);
    char buf[65536];
    ssize_t n;
    while ((n = read(fds[0], buf, sizeof buf)) != 0) {
        if (n < 0) {
            if (errno == EINTR) continue;
            break;
        }
        output.append(buf, static_cast<std::size_t>(n));
    }
    close(fds[0]);

    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) throw std::runtime_error("waitpid() failed");
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return -1;
}

void appendUtf8(std::string& out, unsigned long cp) {
    if (cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) cp = 0xFFFD;
    if (cp < 0x80) {
        out += static_cast<char>(cp);
    } else if (cp < 0x800) {
        out += static_cast<char>(0xC0 | (cp >> 6));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out += static_cast<char>(0xE0 | (cp >> 12));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        out += static_cast<char>(0xF0 | (cp >> 18));
        out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    }
}

// Decode the entity body (text between '&' and ';'). Returns false if unknown.
bool decodeEntity(const std::string& body, std::string& out) {
    if (body == "amp") { out += '&'; return true; }
    if (body == "lt") { out += '<'; return true; }
    if (body == "gt") { out += '>'; return true; }
    if (body == "quot") { out += '"'; return true; }
    if (body == "apos") { out += '\''; return true; }
    if (body.size() >= 2 && body[0] == '#') {
        bool hex = (body[1] == 'x' || body[1] == 'X');
        std::string digits = body.substr(hex ? 2 : 1);
        if (digits.empty() || digits.size() > 8) return false;
        for (char c : digits) {
            if (hex ? !std::isxdigit(static_cast<unsigned char>(c))
                    : !std::isdigit(static_cast<unsigned char>(c))) {
                return false;
            }
        }
        appendUtf8(out, std::strtoul(digits.c_str(), nullptr, hex ? 16 : 10));
        return true;
    }
    return false;
}

// True if the tag text (between '<' and '>') is the named element, e.g. "w:tab".
bool tagIs(const std::string& tag, const std::string& name) {
    if (tag.compare(0, name.size(), name) != 0) return false;
    if (tag.size() == name.size()) return true;
    char c = tag[name.size()];
    return c == ' ' || c == '/' || c == '\t' || c == '\n' || c == '\r';
}

}  // namespace

std::string docxXmlToText(const std::string& xml) {
    std::string out;
    std::size_t i = 0;
    while (i < xml.size()) {
        char c = xml[i];
        if (c == '<') {
            std::size_t end = xml.find('>', i);
            if (end == std::string::npos) break;
            std::string tag = xml.substr(i + 1, end - i - 1);
            if (tag == "/w:p") out += '\n';
            else if (tagIs(tag, "w:tab")) out += '\t';
            else if (tagIs(tag, "w:br") || tagIs(tag, "w:cr")) out += '\n';
            i = end + 1;
        } else if (c == '&') {
            std::size_t semi = xml.find(';', i);
            std::string decoded;
            if (semi != std::string::npos && semi - i <= 12 &&
                decodeEntity(xml.substr(i + 1, semi - i - 1), decoded)) {
                out += decoded;
                i = semi + 1;
            } else {
                out += c;
                ++i;
            }
        } else {
            out += c;
            ++i;
        }
    }
    return out;
}

std::string extractText(const std::string& path) {
    const std::string ext = lowerExtension(path);
    if (ext != ".txt" && ext != ".pdf" && ext != ".docx") {
        throw std::runtime_error("unsupported file type '" + ext + "' for " + path +
                                 " (expected .txt, .pdf or .docx)");
    }
    if (!fileReadable(path)) {
        throw std::runtime_error("cannot open file: " + path);
    }

    std::string text;
    if (ext == ".txt") {
        std::ifstream f(path, std::ios::binary);
        std::ostringstream ss;
        ss << f.rdbuf();
        text = ss.str();
        if (text.compare(0, 3, "\xEF\xBB\xBF") == 0) text.erase(0, 3);
        text = normaliseNewlines(text);
    } else if (ext == ".pdf") {
        std::string raw;
        int rc = runCapture({"pdftotext", "-layout", path, "-"}, raw);
        if (rc == kExecNotFound) {
            throw std::runtime_error(
                "pdftotext not found: install poppler (macOS: brew install poppler; "
                "Debian/Ubuntu: apt install poppler-utils)");
        }
        if (rc != 0) throw std::runtime_error("pdftotext failed on " + path);
        text = normaliseNewlines(raw);
    } else {
        std::string xml;
        int rc = runCapture({"unzip", "-p", path, "word/document.xml"}, xml);
        if (rc == kExecNotFound) {
            throw std::runtime_error("unzip not found: install unzip to read .docx files");
        }
        if (rc != 0) {
            throw std::runtime_error("failed to read word/document.xml from " + path +
                                     " (not a valid .docx?)");
        }
        text = normaliseNewlines(docxXmlToText(xml));
    }

    bool blank = true;
    for (char c : text) {
        if (!std::isspace(static_cast<unsigned char>(c))) { blank = false; break; }
    }
    if (blank) throw std::runtime_error("no text could be extracted from " + path);
    return text;
}
