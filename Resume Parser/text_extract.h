#pragma once

#include <string>

// Extract plain text from a .txt, .pdf (needs pdftotext) or .docx (needs unzip)
// file. Throws std::runtime_error with a clear message on any failure.
std::string extractText(const std::string& path);

// Convert WordprocessingML (word/document.xml) to plain text.
std::string docxXmlToText(const std::string& xml);
