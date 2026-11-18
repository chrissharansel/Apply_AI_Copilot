import asyncio
import pytest

from app.agents.answer_generator import match_option, to_bool
from app.agents.form_analyzer import annotate, profile_value
from app.services.knowledge_service import SENSITIVE, categorize, is_stale, normalize
from app.services.resume_service import coerce_profile
from app.utils.validators import validate_job_url, validate_resume_upload


def test_categories():
    assert categorize("Are you legally authorized to work in the United States?") == "work_authorization"
    assert categorize("Will you now or in the future require sponsorship?") == "sponsorship"
    assert categorize("Are you willing to relocate?") == "relocation"
    assert categorize("What is your expected CTC?") == "salary_expectation"
    assert categorize("Favourite colour?") == "other"
    assert {"work_authorization", "gender", "salary_expectation", "legal_declaration"} <= SENSITIVE


def test_normalize_matches_paraphrase_tokens():
    assert normalize("Are you willing to relocate?") == normalize("Are you willing to relocate")


def test_match_option():
    opts = [{"id": "1", "label": "Yes"}, {"id": "2", "label": "No"}]
    assert match_option("yes", opts)["id"] == "1"
    assert match_option("I am not currently authorized and require sponsorship", opts) is None  # left to LLM / user
    assert to_bool("I agree") is True


def test_annotate_and_profile():
    f = annotate([{"id": "a", "kind": "text", "label": "First Name *", "required": True, "options": []},
                  {"id": "b", "kind": "radio", "label": "Are you authorized to work in the US?", "required": True, "options": []}])
    assert f[0]["profile_key"] == "first_name" and not f[0]["sensitive"]
    assert f[1]["sensitive"] and f[1]["profile_key"] is None
    assert profile_value({"full_name": "Asha K Rao"}, "last_name") == "K Rao"


def test_coerce_profile_is_forgiving():
    d = coerce_profile({"full_name": "A", "skills": "Python, SQL", "total_experience_years": "5 years",
                        "projects": [{"name": "X", "technologies": ["a", "b"]}], "education": "junk"})
    assert d["skills"] == ["Python", "SQL"] and d["total_experience_years"] == 5.0
    assert d["projects"][0]["technologies"] == ["a", "b"] and d["education"] == []


@pytest.mark.parametrize("url", ["http://localhost/x", "http://127.0.0.1:8000", "http://169.254.169.254/latest",
                                 "http://10.0.0.5/jobs", "ftp://example.com", "http://[::1]/", "javascript:alert(1)"])
def test_ssrf_blocked(url):
    with pytest.raises(ValueError):
        asyncio.run(validate_job_url(url))


def test_resume_validation():
    with pytest.raises(ValueError):
        validate_resume_upload("a.exe", b"MZ", 5)
    with pytest.raises(ValueError):
        validate_resume_upload("a.pdf", b"not a pdf", 5)
    assert validate_resume_upload("a.pdf", b"%PDF-1.4", 5) == ".pdf"


def test_lexical_matching_and_json_parsing():
    from app.services.knowledge_service import lex_score, normalize as n
    from app.services.llm_service import parse_json
    assert lex_score(n("Are you willing to relocate?"), n("Are you willing to relocate")) == 1.0
    assert lex_score(n("Are you open to relocation?"), n("Are you willing to relocate?")) > lex_score(n("Favourite colour?"), n("Are you willing to relocate?"))
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! Here you go: {"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}
    assert parse_json("no json here") is None
