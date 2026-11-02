#pragma once

#include <string>

#include "Resume.h"

// Serialise a Resume as pretty-printed JSON. Keys match the struct field names.
// rawText is emitted (last) only when includeRaw is true.
std::string toJson(const Resume& r, bool includeRaw = false);
