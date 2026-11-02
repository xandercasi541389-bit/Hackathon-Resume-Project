import json

import pytest

from integration import load_resume
from jobs import JobDataError, JobMatch, JobPosting, load_jobs, match_jobs
from jobs.matcher import resume_skill_terms, skill_matches


def job(id="j1", title="Dev", company="Acme", **kw):
    return JobPosting(id=id, title=title, company=company, **kw)


def resume(**kw):
    data = {"skills": ["Python"], **kw}
    return load_resume(data)


RAW = {"id": "a", "title": "Intern", "company": "Arthrex, Inc.",
       "required_skills": ["C++"], "preferred_skills": [" SQL ", ""], "bogus": 1}


# ---- loading ----

def test_load_from_file_with_jobs_key(tmp_path):
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps({"jobs": [RAW]}), encoding="utf-8")
    [j] = load_jobs(p)
    assert (j.id, j.company, j.required_skills, j.preferred_skills) == (
        "a", "Arthrex, Inc.", ["C++"], ["SQL"])
    assert j.type == "" and not hasattr(j, "bogus")


def test_load_from_bare_list_file_str_path(tmp_path):
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps([RAW]), encoding="utf-8")
    assert [j.id for j in load_jobs(str(p))] == ["a"]


def test_load_from_list_of_dicts():
    assert load_jobs([RAW])[0].title == "Intern"
    assert load_jobs([]) == []


@pytest.mark.parametrize("bad", [
    {"title": "t", "company": "c"},
    {"id": "1", "title": "", "company": "c"},
    {"id": "1", "title": "t", "company": "  "},
    {"id": 1, "title": "t", "company": "c"},
    {"id": "1", "title": "t", "company": "c", "required_skills": "python"},
    {"id": "1", "title": "t", "company": "c", "preferred_skills": ["a", 3]},
    {"id": "1", "title": "t", "company": "c", "location": 5},
    "not a dict",
])
def test_invalid_entries(bad):
    with pytest.raises(JobDataError):
        load_jobs([bad])


def test_duplicate_id():
    a = {"id": "1", "title": "t", "company": "c"}
    with pytest.raises(JobDataError, match="duplicate"):
        load_jobs([a, dict(a)])


def test_bad_json_and_missing_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{nope", encoding="utf-8")
    with pytest.raises(JobDataError, match="bad.json"):
        load_jobs(p)
    with pytest.raises(JobDataError, match="nothere.json"):
        load_jobs(tmp_path / "nothere.json")


def test_wrong_top_level_shapes(tmp_path):
    p = tmp_path / "j.json"
    p.write_text('{"other": []}', encoding="utf-8")
    with pytest.raises(JobDataError):
        load_jobs(p)
    p.write_text('{"jobs": 3}', encoding="utf-8")
    with pytest.raises(JobDataError):
        load_jobs(p)
    with pytest.raises(JobDataError):
        load_jobs(42)


# ---- skill matching ----

def test_exact_terms_and_case():
    r = resume(skills=["Python", "  Machine   Learning "])
    terms = resume_skill_terms(r)
    assert {"python", "machine learning"} <= terms
    assert skill_matches("PYTHON", terms, "")
    assert not skill_matches("Rust", terms, "")


def test_project_technologies_and_certifications():
    r = resume(projects=[{"name": "App", "technologies": ["Docker"]}],
               certifications=["AWS Certified"])
    terms = resume_skill_terms(r)
    assert "docker" in terms and "aws certified" in terms


def test_phrase_in_resume_text():
    r = resume(experience=[{"position": "Intern", "company": "X",
                            "responsibilities": ["Built REST APIs with Flask"]}])
    terms = resume_skill_terms(r)
    text = r.to_prompt_text()
    assert skill_matches("rest apis", terms, text)
    assert skill_matches("Flask", terms, text)
    assert not skill_matches("Django", terms, text)


def test_symbol_boundaries():
    text = "worked in c++, java. also .net and node.js"
    assert skill_matches("C++", set(), text)
    assert skill_matches("java", set(), text)
    assert skill_matches(".NET", set(), text)
    assert skill_matches("Node.js", set(), text)
    assert not skill_matches("C", set(), text)
    assert not skill_matches("C#", set(), text)
    assert not skill_matches("js", set(), text)  # only inside node.js
    assert not skill_matches("net", set(), "asp.net")
    assert skill_matches("C", set(), "knows c and rust")
    assert not skill_matches("C", set(), "knows c# only")
    assert skill_matches("C#", set(), "knows c# only")
    assert not skill_matches("script", set(), "javascript")


@pytest.mark.parametrize("skill,have", [
    ("JS", "javascript"), ("JavaScript", "js"), ("Postgres", "postgresql"),
    ("PostgreSQL", "postgres"), ("Golang", "go"), ("Go", "golang"),
    ("MS SQL", "sql"), ("SQL Server", "sql"), ("ML", "machine learning"),
    ("Machine Learning", "ml"),
])
def test_aliases(skill, have):
    assert skill_matches(skill, {have}, "")


def test_alias_via_resume_text():
    assert skill_matches("js", set(), "built apps in javascript")


# ---- scoring ----

def test_weighting_math():
    r = resume(skills=["Python", "SQL"])
    j = job(required_skills=["Python", "Rust"], preferred_skills=["SQL"])
    [m] = match_jobs(r, [j])
    # matched weight: Python 2 + SQL 1 = 3 of 5
    assert m.skill_match_percent == 60.0
    assert m.matched_skills == ["Python", "SQL"]
    assert m.missing_skills == ["Rust"]


def test_rounding_and_missing_order():
    r = resume(skills=["Python"])
    j = job(required_skills=["A", "Python"], preferred_skills=["B"])
    [m] = match_jobs(r, [j])
    assert m.skill_match_percent == 40.0
    assert m.missing_skills == ["A", "B"]
    j2 = job(required_skills=["Python"], preferred_skills=["x"] * 3 + ["y"] * 3)
    [m2] = match_jobs(r, [j2])
    assert m2.skill_match_percent == round(100 * 2 / 8, 1) == 25.0
    j3 = job(required_skills=["Python", "q", "z"])
    [m3] = match_jobs(r, [j3])
    assert m3.skill_match_percent == 33.3


def test_empty_skills_zero_percent():
    [m] = match_jobs(resume(), [job()])
    assert m.skill_match_percent == 0.0
    assert m.matched_skills == [] and m.missing_skills == []


def test_company_filter():
    r = resume()
    jobs = [job("1", company="Arthrex, Inc."), job("2", company="Other Co"),
            job("3", company="Acme")]
    assert {m.job.id for m in match_jobs(r, jobs, companies=["ARTHREX"])} == {"1"}  # case, substring
    assert {m.job.id for m in match_jobs(r, jobs, companies=["arthrex, inc. medical"])} == {"1"}
    assert {m.job.id for m in match_jobs(r, jobs, companies=["acme", "other"])} == {"2", "3"}
    assert len(match_jobs(r, jobs, companies=None)) == 3
    assert match_jobs(r, jobs, companies=["Nobody"]) == []


def test_ordering_and_top_n():
    r = resume(skills=["Python", "SQL", "Go"])
    jobs = [
        job("a", "B title", required_skills=["Python"]),                 # 100, req 1
        job("b", "A title", required_skills=["Python"]),                 # 100, req 1 (title tie)
        job("c", "C", required_skills=["Python", "SQL"]),                # 100, req 2
        job("d", "D", required_skills=["Python", "Rust"]),               # 50
        job("e", "E", preferred_skills=["Python", "Rust"]),              # 50, req 0
    ]
    ms = match_jobs(r, jobs, top_n=10)
    assert [m.job.id for m in ms] == ["c", "b", "a", "d", "e"]
    assert [m.job.id for m in match_jobs(r, jobs, top_n=2)] == ["c", "b"]
    assert match_jobs(r, jobs, top_n=0) == []


# ---- text / dict output ----

def test_to_prompt_text_omits_empty():
    assert job(title="Dev", company="Acme").to_prompt_text() == "Dev at Acme"
    full = job(type="internship", location="Fort Myers", description="Build things",
               required_skills=["C++"], preferred_skills=["SQL"]).to_prompt_text()
    assert full.splitlines() == [
        "Dev at Acme (internship)", "Location: Fort Myers", "Description: Build things",
        "Required skills: C++", "Preferred skills: SQL"]
    assert "Location" not in job().to_prompt_text()
    assert "skills" not in job().to_prompt_text()


def test_job_match_to_dict_keys():
    d = JobMatch(job(), 50.0, ["a"], ["b"]).to_dict()
    assert set(d) == {"job", "skill_match_percent", "matched_skills", "missing_skills"}
    assert set(d["job"]) == {"id", "title", "company", "type", "location", "url",
                             "description", "required_skills", "preferred_skills",
                             "retrieved_on"}
    json.dumps(d)
