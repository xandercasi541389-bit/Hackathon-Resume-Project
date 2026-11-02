#pragma once

#include <string>

#include "Resume.h"

// Heuristically fill a Resume from plain resume text (already extracted from
// TXT/PDF/DOCX). Never throws on odd input; unknown content is skipped.
Resume parseResumeText(const std::string& text, const std::string& fileName);
