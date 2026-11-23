"""HTTP-level flow: resume upload -> fact tracking -> conflicts -> resolution -> experience -> resume recommendation.
Runs against an in-memory MongoDB with a stubbed LLM (pip install mongomock-motor)."""
import io
import os

import pytest

pytest.importorskip("mongomock_motor")
docx = pytest.importorskip("docx")


def _docx(text: str) -> bytes:
    d = docx.Document(); d.add_paragraph(text * 3); b = io.BytesIO(); d.save(b); return b.getvalue()


def test_profile_intelligence_flow(tmp_path, monkeypatch):
    os.environ["SECRET_KEY"] = "x" * 20
    from mongomock_motor import AsyncMongoMockClient
    from app.config import settings
    from app.database import mongodb
    from app.services.llm_service import llm
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "secret_key", "x" * 20)
    monkeypatch.setattr(mongodb, "_client", AsyncMongoMockClient(tz_aware=True))
    nxt = {}

    async def fake(system, user, **k):
        return nxt["v"] if "extract" in system.lower() else {"index": None}
    monkeypatch.setattr(llm, "chat_json", fake)
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"name": "A", "email": "a@x.com", "password": "password123"}).json()["token"]}
        nxt["v"] = {"full_name": "Asha Rao", "email": "a@x.com", "phone": "+91 98765 43210", "current_designation": "Python Developer", "desired_role": "Python Developer",
                    "skills": ["Python"], "employment": [{"company": "Acme", "title": "Engineer", "start_date": "Jan 2020", "end_date": "Dec 2021"}]}
        r = c.post("/api/resumes", headers=H, files={"file": ("py.docx", _docx("Python Django backend REST "))}, data={"category": "Backend", "keywords": "django"}).json()
        assert r["label"] == "Python Developer" and r["keywords"] == ["django"]

        p = c.get("/api/profile", headers=H).json()
        assert p["fact_meta"]["email"]["source"] == "resume" and p["summary"]["confirmed"] == 0       # nothing is trusted yet
        p = c.put("/api/profile", headers=H, json={"data": p["data"], "confirm": True}).json()
        assert p["fact_meta"]["email"]["source"] == "user_confirmed"
        p["data"]["phone"] = "+91 11111 22222"
        p = c.put("/api/profile", headers=H, json={"data": p["data"], "confirm": False}).json()
        assert p["fact_meta"]["phone"]["source"] == "user_entered" and p["fact_meta"]["email"]["source"] == "user_confirmed"

        nxt["v"] = {"full_name": "Asha Rao", "email": "a@x.com", "phone": "+91 98765 43210", "current_designation": "Java Developer", "desired_role": "Java Developer",
                    "skills": ["Java"], "employment": [{"company": "Acme", "title": "Engineer", "start_date": "Mar 2020", "end_date": "Dec 2021"},
                                                       {"company": "Delta", "title": "Dev", "start_date": "2022", "end_date": "2023"}]}
        r2 = c.post("/api/resumes", headers=H, files={"file": ("java.docx", _docx("Java Spring Boot Hibernate "))}, data={"label": "Java Developer"}).json()
        assert r2["conflicts"] >= 4
        found = {x["label"]: x for x in c.get("/api/profile/conflicts", headers=H).json()["conflicts"]}
        assert found["Phone number"]["severity"] == "high" and found["Acme: start date"]["profile"] == "Jan 2020"
        res = [{"id": found["Phone number"]["id"], "choice": "profile"}, {"id": found["Acme: start date"]["id"], "choice": "resume"},
               {"id": found["Employer “Delta”"]["id"], "choice": "resume"}]
        p = c.post("/api/profile/conflicts/resolve", headers=H, json={"resolutions": res}).json()
        assert [e["company"] for e in p["data"]["employment"]] == ["Acme", "Delta"] and p["data"]["employment"][0]["start_date"] == "Mar 2020"
        assert p["fact_meta"]["phone"]["source"] == "user_confirmed"                    # keeping my value = confirming it
        left = {x["label"] for x in c.get("/api/profile/conflicts", headers=H).json()["conflicts"]}
        assert "Phone number" not in left and "Acme: start date" not in left            # rulings are remembered

        e = c.get("/api/profile/experience", headers=H).json()
        assert e["complete"] and e["professional_years"] == 3.83 and e["warnings"]
        assert c.post("/api/resumes/recommend", headers=H, json={"title": "Java Backend Engineer", "description": "Spring Boot, Hibernate"}).json()["label"] == "Java Developer"
        assert c.post("/api/resumes/recommend", headers=H, json={"title": "Senior Python Developer", "description": "Django REST"}).json()["label"] == "Python Developer"
