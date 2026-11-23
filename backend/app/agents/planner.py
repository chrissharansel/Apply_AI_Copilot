"""Deterministic decision logic: for each field -> fill / ask / skip / keep, and WHERE the value came from.
The LLM (Copilot CLI) is consulted only for (a) free-text drafting and (b) mapping a saved answer onto dropdown options."""
import re
from datetime import datetime

from ..services import experience as exp
from ..services import facts
from ..services import knowledge_service as kb
from .answer_generator import (format_date, generate_free_text, llm_pick_option, match_option, parse_date, to_bool)
from .form_analyzer import GENERATIVE_RE, OPTIONAL_FREE_RE, PREF_KEYS, profile_value

RESUME_RE = re.compile(r"\b(resume|cv|curriculum)\b", re.I)
MULTI = ("checkbox_group", "multiselect")


class Planner:
    def __init__(self, user_id: str, profile: dict, job: dict, resume_name: str = "resume", opts: dict | None = None, fmeta: dict | None = None):
        self.uid, self.profile, self.job, self.resume_name = user_id, profile, job, resume_name
        self.fmeta = fmeta                      # fact path -> {source, confidence, updated_at}; None = legacy (trust everything)
        self.calc = exp.calculate(profile.get("employment") or [])
        self.opts = {"ai_answers": "auto", "tone": "professional", "writing_notes": "", "job_notes": "", "max_words": 150,
                     "semantic_reuse": True, **(opts or {})}
        self._facts: list[dict] | None = None

    def _item(self, f: dict, **kw) -> dict:
        base = {"key": f["key"], "field_id": f["id"], "label": f["label"], "kind": f["kind"], "required": f["required"],
                "category": f["category"], "sensitive": f["sensitive"], "options": f["options"], "maxlength": f.get("maxlength"),
                "multi": f.get("multi", False), "custom": f.get("custom", "native"), "date_format": f.get("date_format"),
                "profile_key": f.get("profile_key"), "fact": None, "action": "ask", "status": "planned", "source": None, "value": None, "option_ids": [], "confidence": 0.0,
                "flags": ["sensitive"] if f["sensitive"] else [], "suggestion": None, "note": None, "kb_entry_id": None}
        base.update(kw)
        return base

    async def resolve(self, f: dict, raw) -> dict | None:
        """Map a raw answer onto this specific control. None = could not map reliably (then we ask, never guess)."""
        kind, opts = f["kind"], f.get("options") or []
        if raw is None or raw == "" or raw == []:
            return None
        as_list = raw if isinstance(raw, list) else [p.strip() for p in re.split(r"[;,]", str(raw)) if p.strip()]
        if kind in ("select", "radio") or (kind == "combobox" and opts and not f.get("multi")):
            o = match_option(str(raw), opts) or await llm_pick_option(f["label"], str(raw), opts)
            return {"value": o["label"], "option_ids": [o["id"]]} if o else None
        if kind in MULTI or (kind == "combobox" and f.get("multi")):
            if not opts:
                return {"value": ", ".join(as_list), "option_ids": as_list}
            picked = [match_option(p, opts) for p in as_list]
            if not picked or any(p is None for p in picked):
                return None
            return {"value": ", ".join(p["label"] for p in picked), "option_ids": [p["id"] for p in picked]}
        if kind == "checkbox":
            b = to_bool(raw)
            return None if b is None else {"value": "Checked" if b else "Unchecked", "option_ids": [], "bool": b}
        text = ", ".join(map(str, raw)) if isinstance(raw, list) else str(raw).strip()
        if kind == "date":
            d = parse_date(text)
            if not d:
                return None                                  # "immediately", "2 weeks"... -> ask for an actual date
            return {"value": format_date(d, f.get("date_format")), "option_ids": []}
        return {"value": text, "option_ids": []} if text else None

    async def _plan_experience(self, f: dict, pk: str) -> dict | None:
        info = exp.years_for(self.profile, self.calc, pk)
        if not info:
            return None
        unit, opts = f.get("exp_unit", "years"), f.get("options") or []
        if f["kind"] in ("select", "radio", "combobox") and opts:
            o = exp.numeric_option(info["years"], opts)
            r = {"value": o["label"], "option_ids": [o["id"]]} if o else None
        else:
            r = await self.resolve(f, exp.format_years(info["years"], f["kind"], f.get("step", ""), unit))
        if not r:
            return None
        why = f"{info['years']:.1f} years, {info['note']}"
        ok = not info["estimate"] and (self.fmeta is None or all(facts.trusted(self.fmeta.get(p), p) for p in info["fact_paths"]))
        if ok:
            return self._item(f, action="fill", source="calculated", confidence=0.9, note=why, flags=["calculated"], **r)
        return self._ask(f, suggestion=r["value"], note=why + (" (an estimate, please confirm)" if info["estimate"] else " (some of that history isn't confirmed yet)"))

    def _ask(self, f: dict, suggestion=None, note=None, **kw) -> dict:
        opts = [o["label"] for o in f["options"]]
        if f["kind"] == "checkbox":
            opts = ["Yes", "No"]
        return self._item(f, action="ask", suggestion=suggestion, note=note, ask_options=opts, **kw)

    async def plan(self, f: dict, collected: dict, respect_existing: bool = False) -> dict:
        kind, label = f["kind"], f["label"]
        # 0. Already answered by the user in this session (persisted -> survives restarts)
        c = collected.get(f["key"])
        if c:
            if c.get("manual_done"):
                return self._item(f, action="skip", status="manual", source="user", note="You completed this in the browser")
            if c.get("skip"):
                return self._item(f, action="skip", status="skipped", source="user", note="Skipped by you")
            r = await self.resolve(f, c["value"])
            if r:
                return self._item(f, action="fill", source="user", confidence=1.0, **r)
            return self._ask(f, note="I couldn't match your answer to the available options", remap=True)

        # 0b. After a pause the user may have typed things themselves: never overwrite them
        if respect_existing and f.get("value") and kind not in ("file",) and not f["sensitive"]:
            return self._item(f, action="keep", status="kept", source="prefilled", value=f["value"], flags=["prefilled"], confidence=0.5)

        # 1. Files
        if kind == "file":
            if RESUME_RE.search(label + " " + f.get("name", "")):
                return self._item(f, action="fill", source="resume_file", value=self.resume_name, confidence=1.0)
            return self._item(f, action="manual", manual=True, kind="manual",
                              note=f"Please attach “{label}” yourself in the browser window.")

        suggestion, note, fact = None, None, None
        # 2a. Experience: calculated from employment/internship records, in the category the question asks for
        pk = f.get("profile_key")
        if pk and (pk == "total_experience" or pk.startswith("exp:")):
            if res := await self._plan_experience(f, pk):
                return res

        # 2b. Identity facts from the profile. Only facts the user has CONFIRMED are typed in automatically;
        #     resume-only / unconfirmed facts become suggestions the user approves with one click.
        elif pk and not f["sensitive"]:
            v = profile_value(self.profile, pk)
            if v and (r := await self.resolve(f, v)):
                path = facts.fact_path(self.profile, pk)
                meta = (self.fmeta or {}).get(path) if path else None
                if self.fmeta is None or path is None or facts.trusted(meta, path):
                    return self._item(f, action="fill", source="profile", confidence=(meta or {}).get("confidence", 1.0), **r)
                suggestion, note, fact = v, facts.explain(meta, path), path

        # 3. Persistent knowledge base: only user-verified & fresh answers are auto-used
        m = await kb.find_answer(self.uid, label, f["category"])
        if m:
            if not self.opts["semantic_reuse"] and m["match_type"] != "exact":
                m["auto_use"] = False
            if m["auto_use"] and (r := await self.resolve(f, m["answer"])):
                await kb.touch(m["entry_id"])
                return self._item(f, action="fill", source="knowledge_base", confidence=m["confidence"],
                                  kb_entry_id=m["entry_id"], note=m["reason"], **r)
            if not suggestion:
                suggestion, note = m["answer"], m["reason"]

        # 4. Profile preference values (notice period, salary ...): auto-fill if non-sensitive, else only suggest
        pk = PREF_KEYS.get(f["category"])
        if pk and (pv := profile_value(self.profile, pk)):
            if not f["sensitive"] and not suggestion and (r := await self.resolve(f, pv)):
                return self._item(f, action="fill", source="profile", confidence=0.9, **r)
            suggestion, note = suggestion or pv, note or "from your profile"

        # 5. AI-written free text (never sensitive; optional via settings). Always flagged for review.
        if not f["sensitive"] and kind in ("text", "textarea", "richtext") and (GENERATIVE_RE.search(label) or f.get("llm_generative")):
            if OPTIONAL_FREE_RE.search(label) and not f["required"]:
                return self._item(f, action="skip", status="skipped", note="Optional free-text field left blank")
            if self.opts["ai_answers"] == "auto":
                if self._facts is None:
                    self._facts = await kb.verified_facts(self.uid)
                txt = await generate_free_text(self.profile, self.job, f, self._facts, self.opts)
                if txt:
                    return self._item(f, action="fill", source="ai_generated", value=txt, confidence=0.6, flags=["ai_generated", "needs_review"])
                note = "I couldn't draft this one automatically"
            else:
                note = "Free-text answer (you chose to write these yourself; you can ask me to draft it)"

        # 6. Value already on the page (e.g. account prefill) and not sensitive -> keep, flagged
        if f.get("value") and not f["sensitive"]:
            return self._item(f, action="keep", status="kept", source="prefilled", value=f["value"], flags=["prefilled"], confidence=0.5)

        return self._ask(f, suggestion=suggestion, note=note, fact=fact)
