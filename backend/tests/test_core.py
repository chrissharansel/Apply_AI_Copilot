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


# ----------------------------------------------------------------------------- v2: links, semantic mapping, dates
def _f(label="", **kw):
    return {"id": "x", "kind": "text", "label": label, "required": False, "options": [], "name": "", "domid": "",
            "placeholder": "", "ariaLabel": "", "autocomplete": "", "hint": "", "section": "", **kw}


def test_semantic_phone_variants_all_map_to_phone():
    from app.agents.form_analyzer import profile_key_for_field as k
    assert k(_f("Mobile Number")) == k(_f("Contact Number")) == k(_f("Phone")) == "phone"
    assert k(_f("", autocomplete="tel")) == "phone"
    assert k(_f("", placeholder="Your WhatsApp no")) == "phone"
    assert k(_f("Contact", name="phone_number")) == "phone"            # developer-chosen name
    assert k(_f("Given name")) == "first_name" and k(_f("Surname")) == "last_name"


def test_fields_about_other_people_are_not_filled_with_my_data():
    from app.agents.form_analyzer import profile_key_for_field as k
    assert k(_f("Referrer full name")) is None
    assert k(_f("Reference email", name="email")) is None
    assert k(_f("Emergency contact phone")) is None


def test_dates():
    from app.agents.answer_generator import date_format_from_hint, format_date, parse_date
    assert date_format_from_hint("DD/MM/YYYY") == "%d/%m/%Y"
    assert date_format_from_hint("mm-dd-yyyy") == "%m-%d-%Y"
    assert date_format_from_hint("Pick a date") is None
    assert format_date(parse_date("15 Jan 2027"), "%d/%m/%Y") == "15/01/2027"
    assert parse_date("immediately") is None                           # never invent a date


def test_classify_links_by_domain():
    from app.services.resume_service import classify_links
    c = classify_links([{"url": "https://www.linkedin.com/in/asha-rao-123/", "text": "LinkedIn"},
                        {"url": "https://github.com/asharao", "text": "GitHub"},
                        {"url": "https://github.com/asharao/shopfast", "text": "ShopFast"},
                        {"url": "https://asha.dev", "text": "Portfolio"}, {"url": "mailto:a@b.co", "text": ""},
                        {"url": "https://leetcode.com/asha", "text": ""}], "also see github.com/other-person")
    assert c["linkedin"].endswith("/in/asha-rao-123") and c["github"] == "https://github.com/asharao"
    assert c["portfolio"] == "https://asha.dev" and c["email"] == "a@b.co"
    assert {o["label"] for o in c["other_links"]} >= {"ShopFast", "LeetCode"}


def test_clickable_labels_in_pdf_and_docx_are_extracted(tmp_path):
    """Regression: 'LinkedIn'/'GitHub' labels are hyperlinks; the URL is not in the visible text."""
    from pathlib import Path
    from app.services.resume_service import classify_links, extract
    docx = pytest.importorskip("docx")
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    d = docx.Document()
    p = d.sections[0].header.paragraphs[0]                              # contact info in the header
    rid = p.part.relate_to("https://www.linkedin.com/in/asha-rao-123", RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid)
    r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = "LinkedIn"; r.append(t); h.append(r); p._p.append(h)
    d.add_paragraph("Senior engineer"); f = tmp_path / "r.docx"; d.save(str(f))
    text, links = extract(Path(f), ".docx")
    assert "linkedin.com" not in text and classify_links(links, text)["linkedin"].endswith("/in/asha-rao-123")

    rl = pytest.importorskip("reportlab.pdfgen.canvas")
    c = rl.Canvas(str(tmp_path / "r.pdf")); c.drawString(72, 744, "GitHub"); c.linkURL("https://github.com/asharao", (72, 740, 110, 754)); c.save()
    text, links = extract(tmp_path / "r.pdf", ".pdf")
    assert "github.com" not in text and links[0]["text"] == "GitHub" and classify_links(links, text)["github"] == "https://github.com/asharao"


# ----------------------------------------------------------------------------- v3: experience, facts, conflicts, resume match
EMP = [{"company": "Acme", "title": "Software Engineer", "start_date": "Jan 2020", "end_date": "Dec 2021", "description": "Python, Django"},
       {"company": "Beta Labs", "title": "Backend Developer", "start_date": "06/2021", "end_date": "Present", "description": "Go and Python services"},
       {"company": "Gamma", "title": "Software Engineering Intern", "start_date": "Jun 2019", "end_date": "Aug 2019"}]


def test_experience_union_internship_and_current_role():
    from datetime import date
    from app.services import experience as ex
    c = ex.calculate(EMP, date(2026, 11, 19))
    assert c["professional_years"] == 6.92          # overlapping Acme/Beta months counted once (not 7.83)
    assert c["internship_years"] == 0.25 and c["total_years"] == 7.17
    assert c["current_role_years"] == 5.5 and c["complete"]
    bad = ex.calculate([{"company": "X", "title": "Dev", "start_date": "someday"}], date(2026, 1, 1))
    assert not bad["complete"] and bad["warnings"]


def test_which_experience_category_is_asked():
    from app.services.experience import experience_key as k
    assert k("Total years of experience") == "exp:total"
    assert k("Years of professional experience") == "exp:professional"
    assert k("Internship experience (years)") == "exp:internship"
    assert k("How many years of experience do you have with Go?") == "exp:skill:go"
    assert k("Years of Python experience") == "exp:skill:python"
    assert k("Experience in current company (years)") == "exp:current_role"
    assert k("Describe your experience") is None and k("Work experience") is None


def test_numeric_options_and_never_overstating():
    from app.services import experience as ex
    o = [{"id": str(i), "label": l} for i, l in enumerate(["Less than 1 year", "1-3 years", "3-5 years", "5+ years"])]
    assert [ex.numeric_option(y, o)["label"] for y in (0.5, 2.9, 3.0, 6.8)] == ["Less than 1 year", "1-3 years", "3-5 years", "5+ years"]
    assert ex.format_years(6.83, "number") == "6" and ex.format_years(6.83, "text") == "6.8" and ex.format_years(6.83, "text", unit="months") == "81"
    from datetime import date
    c = ex.calculate(EMP, date(2026, 11, 19))
    assert ex.years_for({}, c, "exp:skill:python")["estimate"] is True      # skill years are estimates: only ever suggested
    assert ex.years_for({"experience_mode": "manual", "total_experience_years": 4}, c, "exp:total")["years"] == 4


def test_fact_trust_levels():
    from app.services import facts as F
    old = {"phone": "111"}
    meta = F.update_on_save({}, {}, old, confirm=False)
    assert meta["phone"]["source"] == "user_entered" and not F.trusted(meta["phone"], "phone")       # typed, never confirmed
    assert F.trusted(F.update_on_save({}, {}, old, confirm=True)["phone"], "phone")
    assert not F.trusted(F.entry("resume"), "email") and not F.trusted(F.entry("resume_link"), "linkedin")
    stale = F.entry("user_confirmed"); stale["updated_at"] = stale["updated_at"].replace(year=2020)
    assert not F.trusted(stale, "notice_period") and F.trusted(stale, "full_name")                    # volatile facts expire
    rows = F.describe({"full_name": "A"}, {"full_name": F.entry("resume")})
    assert next(r for r in rows if r["path"] == "full_name")["status"] == "needs_confirmation"
    assert next(r for r in rows if r["path"] == "email")["status"] == "missing"


def test_conflict_detection_and_resolution():
    from app.services import conflicts as cf
    prof = {"full_name": "Asha Rao", "phone": "+91 98765 43210", "email": "a@x.com",
            "employment": [{"company": "Acme Inc", "title": "Engineer", "start_date": "Jan 2020", "end_date": "Dec 2021"}]}
    res = {"full_name": "Asha  Rao", "phone": "+91 90000 11111", "email": "A@X.com",
           "employment": [{"company": "Acme", "title": "Engineer", "start_date": "Mar 2020", "end_date": "Dec 2021"}, {"company": "Delta", "title": "Dev", "start_date": "2022", "end_date": "2023"}]}
    found = {c["id"]: c for c in cf.detect(prof, res)}
    assert {"scalar:phone", "employment:acme:start_date", "employment:delta:*"} <= set(found)
    assert "scalar:email" not in found and "scalar:full_name" not in found and "employment:acme:end_date" not in found   # same value, different formatting
    assert found["scalar:phone"]["severity"] == "high"
    cf.apply(prof, found["employment:acme:start_date"], "resume")
    cf.apply(prof, found["employment:delta:*"], "resume")
    assert prof["employment"][0]["start_date"] == "Mar 2020" and len(prof["employment"]) == 2
    done = {"scalar:phone": {"resume": found["scalar:phone"]["resume"]}}
    assert "scalar:phone" not in {c["id"] for c in cf.detect(prof, res, done)}           # a ruling is remembered for that resume value


def test_resume_recommendation_by_job():
    import asyncio
    from app.services.resume_match import recommend
    py = {"_id": "py", "filename": "py.pdf", "label": "Python Developer", "category": "Backend", "keywords": ["django"],
          "text": "Python Django Flask REST APIs PostgreSQL backend microservices", "parsed": {"skills": ["Python", "Django"]}}
    jv = {"_id": "jv", "filename": "jv.pdf", "label": "Java Developer", "category": "Backend", "keywords": ["spring"],
          "text": "Java Spring Boot Hibernate Maven microservices Kafka", "parsed": {"skills": ["Java", "Spring"]}}
    run = lambda t, d: asyncio.run(recommend("u", {"title": t, "description": d}, [py, jv], use_llm=False))
    assert run("Senior Python Developer", "Build Django REST APIs on PostgreSQL")["best"] == "py"
    r = run("Java Backend Engineer", "Spring Boot microservices with Kafka")
    assert r["best"] == "jv" and "spring" in r["ranking"][0]["matched"]
