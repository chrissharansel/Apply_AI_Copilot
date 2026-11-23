"""End-to-end test of the real orchestrator + Chromium against a synthetic form full of tricky widgets
(react-select style dropdown, MUI style select, ARIA radios/switch, multi-select, masked phone, DD/MM/YYYY date,
contenteditable, shadow DOM, conditional field, 2 pages). LLM and user are simulated; MongoDB is in-memory.

  pip install mongomock-motor reportlab && playwright install chromium
  cd backend/tests/e2e && python -m http.server 8765 &      # serves form.html
  python make_resume.py && python full.py
"""
import asyncio, os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..")); os.environ["SECRET_KEY"] = "x" * 20
from mongomock_motor import AsyncMongoMockClient
from app.database import mongodb
mongodb._client = AsyncMongoMockClient(tz_aware=True)
from app.database.mongodb import get_db
from app.database.models import new_id, now
from app.services import browser_service as B
from app.services.llm_service import llm
from app.agents import orchestrator as O

async def public_ok(h): return True
B.host_is_public = public_ok
async def ensure(self, headless):
    from playwright.async_api import async_playwright
    if self.pw is None: self.pw = await async_playwright().start()
    if headless not in self.browsers: self.browsers[headless] = await self.pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None, args=["--no-sandbox"])
    return self.browsers[headless]
B.BrowserManager._ensure = ensure

calls = []
async def fake_chat(system, user, **k):
    calls.append(system[:40])
    if "Extract job posting" in system: return {"company": "Acme Corp", "job_title": "Backend Engineer", "description": "Build services in Python."}
    if "classify job-application" in system: return {"fields": []}
    if "write job-application answers" in system: return {"answer": "I enjoy building reliable backend services and my Python and Go experience fits this role."}
    if "Pick which option" in system: return {"index": None}
    return {"index": None}
llm.chat_json = fake_chat

ANS = {"Work mode": "Hybrid", "Preferred shift": "Night", "Open to relocation": "yes", "Skills you want": "Python, Go", "Available from": "15 Jan 2027",
       "Were you referred": "No", "authorized": "No", "Cover note": "Happy to chat anytime.", "Reference email": "skip", "Python experience": "5", "LinkedIn": "https://linkedin.com/in/asha-rao-123"}

async def user_sim(sid, events):
    db = get_db(); paused_once = False
    while True:
        s = await db.agent_sessions.find_one({"_id": sid})
        st = s["status"]
        if st == "In Progress" and not paused_once and s.get("step") == 0 and s.get("results"):
            paused_once = True; await db.agent_sessions.update_one({"_id": sid}, {"$set": {"paused": True}}); events.append("PAUSE requested")
            for _ in range(40):
                await asyncio.sleep(0.5)
                if (await db.agent_sessions.find_one({"_id": sid}))["status"] == "Paused": events.append("paused ok"); break
            await asyncio.sleep(1); await db.agent_sessions.update_one({"_id": sid}, {"$set": {"paused": False}}); events.append("continue")
        if st == "Waiting for User Input":
            qs = s["pending_questions"]; upd = {}
            for q in qs:
                if q["status"] != "open": continue
                if q["manual"]: q["status"] = "answered"; upd[f"collected.{q['key']}"] = {"manual_done": True, "skip": True}; events.append(f"manual-done:{q['label']}"); continue
                a = next((v for k, v in ANS.items() if k.lower() in q["label"].lower()), None)
                if a == "skip" and q["can_skip"]: q["status"] = "skipped"; upd[f"collected.{q['key']}"] = {"skip": True}
                elif a: q["status"] = "answered"; upd[f"collected.{q['key']}"] = {"value": a, "skip": False}
                else: q["status"] = "skipped" if q["can_skip"] else "answered"; upd[f"collected.{q['key']}"] = {"skip": True} if q["can_skip"] else {"value": "n/a"}
                events.append(f"Q: {q['label']!r} -> {a}")
            await db.agent_sessions.update_one({"_id": sid}, {"$set": {**upd, "pending_questions": qs}})
        if st == "Ready for Review":
            r = s["review"]; events.append(f"REVIEW missing={r['missing']} warnings={len(r['warnings'])}")
            await db.agent_sessions.update_one({"_id": sid}, {"$set": {"approval": {"approved": True, "edits": {}, "at": now()}}})
        if st in ("Submitted", "Failed", "Requires Manual Intervention", "Cancelled"): return
        await asyncio.sleep(0.7)

async def main():
    db = get_db(); uid = new_id(); sid = new_id(); rid = new_id(); aid = new_id()
    from app.services import facts as F
    pdata = {"full_name": "Asha Rao", "email": "asha@example.com", "phone": "+91 98765 43210", "location": "Bengaluru, Karnataka, India",
             "linkedin": "https://linkedin.com/in/asha-rao-123", "github": "https://github.com/asharao", "postal_code": "560001", "skills": ["Python", "Go"],
             "employment": [{"company": "Acme", "title": "Software Engineer", "start_date": "Jan 2020", "end_date": "Dec 2021", "description": "Python, Django", "kind": "full_time"},
                            {"company": "Beta Labs", "title": "Backend Developer", "start_date": "Jun 2021", "end_date": "Present", "description": "Go and Python", "kind": "full_time"}]}
    meta = F.update_on_save({}, {}, pdata, True)
    meta["linkedin"] = F.entry("resume_link")                       # read from a resume link but never confirmed by the user
    await db.candidate_profiles.insert_one({"_id": new_id(), "user_id": uid, "confirmed": True, "data": pdata, "facts": meta})
    await db.resumes.insert_one({"_id": rid, "user_id": uid, "filename": "Asha_Rao_Resume.pdf", "ext": ".pdf", "version": 1, "active": True, "storage_path": os.path.join(os.path.dirname(__file__), "sample_resume.pdf")})
    await db.applications.insert_one({"_id": aid, "user_id": uid, "status": "Pending", "errors": []})
    await db.agent_sessions.insert_one({"_id": sid, "user_id": uid, "url": "http://127.0.0.1:8765/form.html", "resume_id": rid, "application_id": aid,
        "status": "Pending", "state": "INIT", "collected": {}, "pending_questions": [], "results": [], "job": {}, "options": {"notes": "emphasise Python", "show_browser": False}})
    events = []
    t0 = asyncio.create_task(O.Orchestrator(sid, uid).run())
    await asyncio.wait_for(asyncio.gather(t0, user_sim(sid, events)), 150)
    s = await db.agent_sessions.find_one({"_id": sid})
    print("FINAL:", s["status"], "|", s.get("confirmation", "")[:60], "| error:", s.get("error"))
    print("job:", s["job"]["title"], "@", s["job"]["company"])
    for e in events: print(" ", e)
    print("FIELDS:")
    for r in s["results"]: print(f"  {r['status']:13} {r['kind']:13} {r['label'][:38]:38} {str(r.get('source')):15} {str(r['value'])[:34]!r} {r['flags']}")
    app = await db.applications.find_one({"_id": aid}); print("application:", app["status"], app.get("company"), "|", app.get("job_title"))
    print("LLM calls:", len(calls))
    await B.bm.shutdown()
asyncio.run(main())
