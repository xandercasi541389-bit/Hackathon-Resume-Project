# Resume Parser (C++)

Reads a resume (`.txt`, `.pdf`, `.docx`), fills the `Resume` struct from `../Resume.h`,
and prints it as JSON on stdout. Heuristic, no external C++ libraries.

## Build and run
```bash
make                 # -> ./resume_parser (C++17)
make test            # unit tests in tests/
./resume_parser samples/sample_resume.pdf          # JSON on stdout
./resume_parser my_resume.docx --raw               # also include rawText
```
Errors go to stderr with exit code 1 (missing file, unsupported type, no text).

Requirements: a C++17 compiler, `unzip` (DOCX), and `pdftotext` from poppler for PDF
(`brew install poppler` / `apt install poppler-utils`). Tools are run without a shell,
so paths with spaces are fine.

## JSON output
Keys are exactly the `Resume.h` field names (`rawText` only with `--raw`):
```json
{
  "fileName": "", "name": "", "email": "", "phone": "", "location": "", "summary": "",
  "skills": [],
  "education": [{"institution": "", "degree": "", "major": "", "graduationDate": ""}],
  "experience": [{"company": "", "position": "", "startDate": "", "endDate": "", "responsibilities": []}],
  "projects": [{"name": "", "description": "", "technologies": []}],
  "certifications": []
}
```
A single date (e.g. `Summer 2025`) sets `startDate` and leaves `endDate` empty.
`graduationDate` keeps an `Expected` prefix when the resume has one.

## Using it from Python
The AI module (`../LLM Integration`) reads this JSON directly:
```python
import subprocess
from integration import load_resume
out = subprocess.run(["../Resume Parser/resume_parser", path], capture_output=True, text=True, check=True)
resume = load_resume(out.stdout)
```
Personal fields (name, email, phone, location) are kept out of LLM prompts.

## Files
| File | Purpose |
|---|---|
| `text_extract.*` | File -> plain text (TXT, `pdftotext -layout`, DOCX XML) |
| `parser.*` | Text -> `Resume`: contact info, section headings, entries, two-column layouts |
| `json_writer.*` | `Resume` -> JSON |
| `main.cpp` | CLI |
| `samples/` | Fake sample resume in all three formats |

`JobPosting`, `ResumeEvaluation` and `JobMatch` in `Resume.h` are not implemented here.
