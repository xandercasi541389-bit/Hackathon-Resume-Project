// Tests for text_extract and json_writer. Plain checks, non-zero exit on failure.
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include <sys/stat.h>
#include <unistd.h>

#include "json_writer.h"
#include "text_extract.h"

static int g_checks = 0, g_failed = 0, g_skipped = 0;

#define CHECK(cond)                                                              \
    do {                                                                         \
        ++g_checks;                                                              \
        if (!(cond)) {                                                           \
            ++g_failed;                                                          \
            std::cerr << "FAIL " << __FILE__ << ":" << __LINE__ << ": " #cond "\n"; \
        }                                                                        \
    } while (0)

#define CHECK_EQ(a, b)                                                           \
    do {                                                                         \
        ++g_checks;                                                              \
        std::string _a = (a), _b = (b);                                          \
        if (_a != _b) {                                                          \
            ++g_failed;                                                          \
            std::cerr << "FAIL " << __FILE__ << ":" << __LINE__ << ": " #a "\n  got:      [" \
                      << _a << "]\n  expected: [" << _b << "]\n";                \
        }                                                                        \
    } while (0)

static bool contains(const std::string& s, const std::string& sub) {
    return s.find(sub) != std::string::npos;
}

static bool throws(const std::string& path) {
    try {
        extractText(path);
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

static void writeFile(const std::string& path, const std::string& data) {
    std::ofstream f(path, std::ios::binary);
    f << data;
}

static bool haveTool(const std::string& name) {
    std::string cmd = "command -v " + name + " >/dev/null 2>&1";
    return std::system(cmd.c_str()) == 0;
}

static void testJson() {
    Resume empty;
    std::string j = toJson(empty);
    for (const char* key : {"fileName", "name", "email", "phone", "location", "summary"}) {
        CHECK(contains(j, std::string("\"") + key + "\": \"\""));
    }
    for (const char* key : {"skills", "education", "experience", "projects", "certifications"}) {
        CHECK(contains(j, std::string("\"") + key + "\": []"));
    }
    CHECK(!contains(j, "rawText"));
    CHECK(j.compare(0, 2, "{\n") == 0);
    CHECK(j.find("  \"fileName\"") != std::string::npos);

    // Key order.
    std::size_t last = 0;
    for (const char* key : {"fileName", "name", "email", "phone", "location", "summary", "skills",
                            "education", "experience", "projects", "certifications"}) {
        std::size_t p = j.find(std::string("\"") + key + "\"");
        CHECK(p != std::string::npos && p >= last);
        last = p;
    }

    // Escaping.
    Resume r;
    r.name = "Say \"hi\" \\ back";
    r.summary = std::string("line1\nline2\ttab\r\b\f") + '\x01' + '\x1f';
    r.location = "Z\xC3\xBCrich \xE2\x80\x93 caf\xC3\xA9";
    j = toJson(r);
    CHECK(contains(j, "\"name\": \"Say \\\"hi\\\" \\\\ back\""));
    CHECK(contains(j, "\"summary\": \"line1\\nline2\\ttab\\r\\b\\f\\u0001\\u001F\""));
    CHECK(contains(j, "\"location\": \"Z\xC3\xBCrich \xE2\x80\x93 caf\xC3\xA9\""));

    // Nested arrays.
    Resume n;
    n.skills = {"C++", "Python"};
    Education ed{"MIT", "BS", "CS", "2020"};
    n.education.push_back(ed);
    Experience e1;
    e1.company = "Acme";
    e1.position = "Dev";
    e1.startDate = "2020";
    e1.endDate = "2022";
    e1.responsibilities = {"Built \"things\"", "Fixed bugs"};
    Experience e2;
    e2.company = "Beta";
    n.experience = {e1, e2};
    Project p;
    p.name = "Proj";
    p.description = "Desc";
    p.technologies = {"Go"};
    n.projects.push_back(p);
    n.certifications = {"AWS"};
    j = toJson(n);
    CHECK(contains(j, "\"skills\": [\n    \"C++\",\n    \"Python\"\n  ]"));
    CHECK(contains(j, "\"institution\": \"MIT\""));
    CHECK(contains(j, "\"graduationDate\": \"2020\""));
    CHECK(contains(j, "\"responsibilities\": [\n        \"Built \\\"things\\\"\",\n        \"Fixed bugs\"\n      ]"));
    CHECK(contains(j, "\"company\": \"Beta\""));
    CHECK(contains(j, "\"responsibilities\": []"));
    CHECK(contains(j, "\"technologies\": [\n        \"Go\"\n      ]"));
    CHECK(contains(j, "\"certifications\": [\n    \"AWS\"\n  ]"));
    CHECK(contains(j, "},\n    {"));

    // includeRaw.
    n.rawText = "raw\ntext";
    j = toJson(n, true);
    CHECK(contains(j, "\"rawText\": \"raw\\ntext\""));
    CHECK(j.find("\"rawText\"") > j.find("\"certifications\""));
    CHECK(!contains(toJson(n, false), "rawText"));
}

static void testDocxXml() {
    CHECK_EQ(docxXmlToText("<w:p><w:r><w:t>Hello</w:t></w:r></w:p><w:p><w:r><w:t>World</w:t></w:r></w:p>"),
             "Hello\nWorld\n");
    CHECK_EQ(docxXmlToText("<w:p><w:r><w:t>a</w:t><w:tab/><w:t>b</w:t></w:r></w:p>"), "a\tb\n");
    CHECK_EQ(docxXmlToText("<w:p><w:r><w:t>a</w:t><w:br/><w:t>b</w:t></w:r></w:p>"), "a\nb\n");
    CHECK_EQ(docxXmlToText("<w:p><w:pPr/><w:r><w:t xml:space=\"preserve\"> x </w:t></w:r></w:p>"), " x \n");
    CHECK_EQ(docxXmlToText("<w:t>A &amp; B &lt;c&gt; &quot;d&quot; &apos;e&apos;</w:t>"),
             "A & B <c> \"d\" 'e'");
    CHECK_EQ(docxXmlToText("<w:t>&#65;&#x42;&#233;&#x2013;&#x1F600;</w:t>"),
             "AB\xC3\xA9\xE2\x80\x93\xF0\x9F\x98\x80");
    CHECK_EQ(docxXmlToText("<w:t>a &bogus; b & c</w:t>"), "a &bogus; b & c");
    // <w:tbl> etc must not be mistaken for <w:tab/> or <w:br/>.
    CHECK_EQ(docxXmlToText("<w:tbl><w:tblPr/><w:brk/></w:tbl>"), "");
}

static void testExtractTxt(const std::string& dir) {
    std::string p = dir + "/plain.txt";
    writeFile(p, "\xEF\xBB\xBFHello\r\nWorld\rEnd\n");
    CHECK_EQ(extractText(p), "Hello\nWorld\nEnd\n");

    // Path with spaces, quote and dollar sign.
    std::string sub = dir + "/dir with space";
    mkdir(sub.c_str(), 0700);
    std::string sp = sub + "/my $r'es\"ume.TXT";
    writeFile(sp, "Jane Doe\n");
    CHECK_EQ(extractText(sp), "Jane Doe\n");

    // Error cases.
    std::string unk = dir + "/file.xyz";
    writeFile(unk, "data");
    CHECK(throws(unk));
    CHECK(throws(dir + "/noext"));
    CHECK(throws(dir + "/does_not_exist.txt"));
    CHECK(throws(dir + "/does_not_exist.pdf"));
    CHECK(throws(dir + "/does_not_exist.docx"));
    std::string empty = dir + "/empty.txt";
    writeFile(empty, "");
    CHECK(throws(empty));
    std::string bom = dir + "/bomonly.txt";
    writeFile(bom, "\xEF\xBB\xBF\n  \n");
    CHECK(throws(bom));
    std::string badDocx = dir + "/bad.docx";
    writeFile(badDocx, "not a zip");
    CHECK(throws(badDocx));
}

static void testExtractDocx(const std::string& dir) {
    if (!haveTool("textutil") || !haveTool("unzip")) {
        ++g_skipped;
        std::cout << "SKIP docx extraction (textutil/unzip not available)\n";
        return;
    }
    std::string sub = dir + "/docx dir";
    mkdir(sub.c_str(), 0700);
    std::string src = sub + "/in.txt", out = sub + "/out file.docx";
    writeFile(src, "Jane Doe\nSoftware Engineer & Tester\n");
    std::string cmd = "textutil -convert docx -output '" + out + "' '" + src + "' >/dev/null 2>&1";
    if (std::system(cmd.c_str()) != 0) {
        ++g_skipped;
        std::cout << "SKIP docx extraction (textutil failed)\n";
        return;
    }
    std::string text = extractText(out);
    CHECK(contains(text, "Jane Doe\n"));
    CHECK(contains(text, "Software Engineer & Tester"));
}

static void testExtractPdf(const std::string& dir) {
    if (!haveTool("pdftotext")) {
        // Still verify the friendly error path when we can make a PDF-named file.
        std::string p = dir + "/fake.pdf";
        writeFile(p, "%PDF-1.4\n");
        try {
            extractText(p);
            CHECK(false);
        } catch (const std::runtime_error& e) {
            CHECK(contains(e.what(), "install poppler (macOS: brew install poppler; "
                                     "Debian/Ubuntu: apt install poppler-utils)"));
        }
        ++g_skipped;
        std::cout << "SKIP pdf extraction (pdftotext not available)\n";
        return;
    }
    if (!haveTool("cupsfilter")) {
        ++g_skipped;
        std::cout << "SKIP pdf extraction (cupsfilter not available)\n";
        return;
    }
    std::string sub = dir + "/pdf dir";
    mkdir(sub.c_str(), 0700);
    std::string src = sub + "/in.txt", out = sub + "/out file.pdf";
    writeFile(src, "Jane Doe\nSoftware Engineer\n");
    std::string cmd = "cupsfilter '" + src + "' > '" + out + "' 2>/dev/null";
    if (std::system(cmd.c_str()) != 0) {
        ++g_skipped;
        std::cout << "SKIP pdf extraction (cupsfilter failed)\n";
        return;
    }
    std::string text = extractText(out);
    CHECK(contains(text, "Jane Doe"));
    CHECK(contains(text, "Software Engineer"));
}

int main() {
    char tmpl[] = "/tmp/test_io_XXXXXX";
    char* d = mkdtemp(tmpl);
    if (!d) {
        std::cerr << "mkdtemp failed\n";
        return 2;
    }
    std::string dir = d;

    testJson();
    testDocxXml();
    testExtractTxt(dir);
    testExtractDocx(dir);
    testExtractPdf(dir);

    std::string cleanup = "rm -rf '" + dir + "'";
    if (std::system(cleanup.c_str()) != 0) std::cerr << "warning: cleanup failed\n";

    std::cout << "test_io: " << (g_checks - g_failed) << "/" << g_checks << " checks passed, "
              << g_failed << " failed, " << g_skipped << " skipped\n";
    return g_failed == 0 ? 0 : 1;
}
