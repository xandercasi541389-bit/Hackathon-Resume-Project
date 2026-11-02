// resume_parser: resume file (.txt/.pdf/.docx) -> Resume JSON on stdout.
//
//   resume_parser <file> [--raw]
//
// --raw also includes the extracted text (rawText). Errors go to stderr with exit code 1,
// so callers (e.g. the Python module) can pipe stdout straight into a JSON loader.

#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>

#include "json_writer.h"
#include "parser.h"
#include "text_extract.h"

int main(int argc, char** argv) {
    std::string path;
    bool includeRaw = false;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--raw") == 0) includeRaw = true;
        else if (std::strcmp(argv[i], "-h") == 0 || std::strcmp(argv[i], "--help") == 0) path.clear(), argc = 0;
        else path = argv[i];
    }
    if (path.empty()) {
        std::cerr << "usage: resume_parser <resume.txt|.pdf|.docx> [--raw]\n";
        return 1;
    }
    try {
        std::string text = extractText(path);
        std::string fileName = path.substr(path.find_last_of('/') + 1);
        std::cout << toJson(parseResumeText(text, fileName), includeRaw);
    } catch (const std::exception& e) {
        std::cerr << "resume_parser: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
