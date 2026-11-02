import json
from pathlib import Path

import pytest

from integration import (CompanyProfile, ResumeAnalysis, ValidationError,
                         load_company, load_resume)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def company_dict():
    return json.loads((FIXTURES / "sample_company.json").read_text(encoding="utf-8"))


def resume_dict():
    return json.loads((FIXTURES / "sample_resume.json").read_text(encoding="utf-8"))


# ---- company ----
def test_company_from_dict():
    c = load_company(company_dict())
    assert isinstance(c, CompanyProfile)
    assert c.company_name == "Arthrex"
    assert c.industry == "Medical Devices"
    assert "Engineering" in c.relevant_departments
    assert c.extra == {}


def test_company_from_file_str_and_path():
    p = FIXTURES / "sample_company.json"
    assert load_company(p).company_name == "Arthrex"
    assert load_company(str(p)).company_name == "Arthrex"


def test_company_from_json_string():
    assert load_company('  {"company_name": "Acme"}').company_name == "Acme"


def test_company_nulls_and_extra_keys():
    c = load_company({"company_name": "Acme", "industry": None, "business_activities": None,
                      "website": "acme.test"})
    assert c.industry == "" and c.business_activities == []
    assert c.extra == {"website": "acme.test"}


@pytest.mark.parametrize("bad", [{}, {"company_name": ""}, {"company_name": "  "},
                                 {"company_name": None}])
def test_company_missing_name(bad):
    with pytest.raises(ValidationError, match="company_name"):
        load_company(bad)


def test_company_bad_json_and_missing_file(tmp_path):
    with pytest.raises(ValidationError, match="Invalid JSON"):
        load_company('{"company_name": ')
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(ValidationError, match="Invalid JSON"):
        load_company(bad)
    with pytest.raises(ValidationError, match="Cannot read"):
        load_company(tmp_path / "nope.json")


def test_company_wrong_types():
    with pytest.raises(ValidationError, match="business_activities"):
        load_company({"company_name": "A", "business_activities": "x"})
    with pytest.raises(ValidationError, match=r"relevant_departments\[0\]"):
        load_company({"company_name": "A", "relevant_departments": [1]})
    with pytest.raises(ValidationError, match="industry"):
        load_company({"company_name": "A", "industry": 5})
    with pytest.raises(ValidationError):
        load_company(123)


def test_company_prompt_text_omits_empty():
    full = load_company(company_dict()).to_prompt_text()
    assert "Company: Arthrex" in full and "Relevant departments:" in full
    assert load_company({"company_name": "Acme"}).to_prompt_text() == "Company: Acme"


# ---- resume ----
def test_resume_valid():
    r = load_resume(FIXTURES / "sample_resume.json")
    assert isinstance(r, ResumeAnalysis)
    assert r.education[0].institution == "FGCU"
    assert "C++" in r.skills
    assert r.experience[0].role == "Warehouse Associate"
    assert r.projects[0].name == "AI Assistant"


def test_resume_from_dict_and_json_string():
    assert load_resume(resume_dict()).skills
    assert load_resume(json.dumps(resume_dict())).skills


def test_resume_minimal():
    r = load_resume(FIXTURES / "sample_resume_minimal.json")
    assert r.skills == ["Python", "SQL"]
    assert r.education == [] and r.experience == [] and r.projects == []


def test_resume_nulls_and_extra_keys():
    r = load_resume({"skills": ["Go"], "education": None, "projects": None, "gpa": 3.9,
                     "experience": [{"role": "Dev", "company": "X", "description": None}]})
    assert r.extra == {"gpa": 3.9}
    assert r.experience[0].company == "X"
    assert r.experience[0].extra == {}
    assert r.experience[0].description == ""


def test_resume_string_items_coerced():
    r = load_resume({"education": ["BS Computer Science"], "experience": ["Intern at X"],
                     "projects": ["Chat bot"]})
    assert r.education[0].degree == "BS Computer Science"
    assert r.experience[0].description == "Intern at X"
    assert r.projects[0].description == "Chat bot"


@pytest.mark.parametrize("empty", [{}, {"skills": []}, {"skills": None, "education": []},
                                   {"other": "x"}])
def test_resume_empty(empty):
    with pytest.raises(ValidationError, match="at least one"):
        load_resume(empty)


def test_resume_bad_json_and_missing_file(tmp_path):
    with pytest.raises(ValidationError, match="Invalid JSON"):
        load_resume("{oops")
    with pytest.raises(ValidationError, match="Cannot read"):
        load_resume(tmp_path / "missing.json")
    arr = tmp_path / "arr.json"
    arr.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValidationError, match="JSON object"):
        load_resume(arr)


def test_resume_wrong_types():
    with pytest.raises(ValidationError, match="skills"):
        load_resume({"skills": "Python"})
    with pytest.raises(ValidationError, match=r"skills\[1\]"):
        load_resume({"skills": ["a", 2]})
    with pytest.raises(ValidationError, match="experience"):
        load_resume({"experience": {"role": "x"}})
    with pytest.raises(ValidationError, match=r"experience\[0\]"):
        load_resume({"experience": [42]})
    with pytest.raises(ValidationError, match="role"):
        load_resume({"experience": [{"role": 5}]})


def test_resume_prompt_text_omits_empty():
    assert load_resume({"skills": ["Python", "SQL"]}).to_prompt_text() == "Skills: Python, SQL"
    text = load_resume(resume_dict()).to_prompt_text()
    for header in ("Education:", "Skills:", "Experience:", "Projects:"):
        assert header in text
    assert "None" not in text


def test_resume_keywords_dedup_lowercase():
    r = load_resume({"skills": ["Python", "python", "SQL"],
                     "education": [{"degree": "Software Engineering"}],
                     "experience": [{"role": "SQL"}],
                     "projects": [{"name": "AI Assistant"}]})
    assert r.keywords() == ["python", "sql", "software engineering", "ai assistant"]


# --- Edge cases found in the Sprint 1 audit ---------------------------------

def test_bom_prefixed_file_and_string(tmp_path):
    path = tmp_path / "resume.json"
    path.write_text('﻿{"skills": ["Python"]}', encoding="utf-8")
    assert load_resume(path).skills == ["Python"]
    assert load_resume('﻿\n{"skills": ["Python"]}').skills == ["Python"]


def test_deeply_nested_json_string_is_validation_error():
    deep = '{"skills": ["a"], "x": ' + "[" * 100_000 + "]" * 100_000 + "}"
    with pytest.raises(ValidationError):
        load_resume(deep)


def test_nul_byte_path_is_validation_error():
    with pytest.raises(ValidationError):
        load_resume("bad\x00path.json")


# --- C++ resume parser output (keys follow Resume.h) --------------------------

CPP = FIXTURES / "sample_resume_cpp.json"


def test_cpp_output_maps_struct_fields():
    r = load_resume(CPP)
    assert "Python" in r.skills and "C++" in r.skills
    e = r.education[0]
    assert (e.institution, e.degree, e.major) == (
        "Florida Gulf Coast University", "Bachelor of Science", "Software Engineering")
    assert e.graduation_date == "Expected May 2027"
    x = r.experience[0]
    assert (x.role, x.company, x.start_date, x.end_date) == (
        "Warehouse Associate", "Amazon Fulfillment", "Jun 2024", "Present")
    assert any("SAP" in item for item in x.responsibilities)
    assert r.projects[0].technologies == ["Python", "OpenAI API", "Flask"]
    assert r.certifications == ["CompTIA A+", "AWS Certified Cloud Practitioner"]
    assert r.summary.startswith("Software engineering student")


def test_cpp_personal_details_never_reach_prompt():
    r = load_resume(CPP)
    for key in ("name", "email", "phone", "location", "fileName"):
        assert key in r.extra
        value = r.extra[key]
        assert value and value not in r.to_prompt_text()


def test_cpp_prompt_text_and_keywords():
    r = load_resume(CPP)
    text = r.to_prompt_text()
    assert "Warehouse Associate at Amazon Fulfillment (Jun 2024 - Present)" in text
    assert "  * Operated SAP warehouse management workflows" in text
    assert "Bachelor of Science in Software Engineering" in text
    assert "Certifications: CompTIA A+" in text
    kw = r.keywords()
    for term in ("software engineering", "flask", "sqlite", "comptia a+", "warehouse associate"):
        assert term in kw


def test_cpp_json_from_stdout_string():
    r = load_resume(CPP.read_text(encoding="utf-8"))
    assert r.experience[1].company == "FGCU Information Technology Services"


def test_cpp_position_preferred_and_role_still_supported():
    r = load_resume({"experience": [{"position": "Intern", "role": "Old"}, {"role": "Dev"}]})
    assert [x.role for x in r.experience] == ["Intern", "Dev"]


def test_cpp_list_fields_validated():
    with pytest.raises(ValidationError, match=r"experience\[0\].*responsibilities"):
        load_resume({"experience": [{"responsibilities": "not a list"}]})
    with pytest.raises(ValidationError, match="certifications"):
        load_resume({"skills": ["a"], "certifications": "AWS"})
