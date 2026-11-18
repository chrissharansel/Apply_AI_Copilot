"""Deterministic decision logic: for each field -> fill / ask / skip / keep, and WHERE the value came from.
The LLM (Copilot CLI) is consulted only for (a) free-text generation and (b) mapping a saved answer onto dropdown options."""
import re

from ..services import knowledge_service as kb
from .answer_generator import generate_free_text, llm_pick_option, match_option, to_bool, to_iso_date
from .form_analyzer import GENERATIVE_RE, OPTIONAL_FREE_RE, PREF_KEYS, profile_value

RESUME_RE = re.compile(r"\b(resume|cv|curriculum)\b", re.I)


class Planner:
    def __init__(self, user_id: str, profile: dict, job: dict, resume_name: str = "resume"):
        self.uid, self.profile, self.job, self.resume_name = user_id, profile, job, resume_name
        self._facts: list[dict] | None = None

    def _item(self, f: dict, **kw) -> dict:
        flags = ["sensitive"] if f["sensitive"] else []
        base = {"key": f["key"], "field_id": f["id"], "label": f["label"], "kind": f["kind"],
                "required": f["required"], "category": f["category"], "sensitive": f["sensitive"],
                "options": f["options"], "maxlength": f.get("maxlength"), "action": "ask", "status": "planned",
                "source": None, "value": None, "option_ids": [], "confidence": 0.0, "flags": flags,
                "suggestion": None, "note": None, "kb_entry_id": None}
        base.update(kw)
        return base

    async def resolve(self, f: dict, raw) -> dict | None:
        """Map a raw answer onto this specific field. None = could not map reliably."""
        kind, opts = f["kind"], f.get("options") or []
        if raw is None or raw == "" or raw == []:
            return None
        if kind in ("select", "radio"):
            o = match_option(str(raw), opts) or await llm_pick_option(f["label"], str(raw), opts)
            return {"value": o["label"], "option_ids": [o["id"]]} if o else None
        if kind == "checkbox_group":
            parts = raw if isinstance(raw, list) else [p for p in re.split(r"[,;]", str(raw)) if p.strip()]
            picked = [match_option(p, opts) for p in parts]
            if not picked or any(p is None for p in picked):
                return None
            return {"value": ", ".join(p["label"] for p in picked), "option_ids": [p["id"] for p in picked]}
        if kind == "checkbox":
            b = to_bool(raw)
            return None if b is None else {"value": "Checked" if b else "Unchecked", "option_ids": [], "bool": b}
        text = ", ".join(map(str, raw)) if isinstance(raw, list) else str(raw).strip()
        if kind == "date":
            text = to_iso_date(text) or text
        return {"value": text, "option_ids": []} if text else None

    def _ask(self, f: dict, suggestion=None, note=None, **kw) -> dict:
        opts = [o["label"] for o in f["options"]]
        if f["kind"] == "checkbox":
            opts = ["Yes", "No"]
        return self._item(f, action="ask", suggestion=suggestion, note=note, ask_options=opts, **kw)

    async def plan(self, f: dict, collected: dict) -> dict:
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

        # 1. Files
        if kind == "file":
            if RESUME_RE.search(label):
                return self._item(f, action="fill", source="resume_file", value=self.resume_name, confidence=1.0)
            return self._item(f, action="manual", manual=True, kind="manual",
                              note=f"Please attach “{label}” yourself in the browser window.")

        # 2. Identity facts straight from the confirmed profile (never for sensitive fields)
        if f.get("profile_key") and not f["sensitive"]:
            v = profile_value(self.profile, f["profile_key"])
            if v and (r := await self.resolve(f, v)):
                return self._item(f, action="fill", source="profile", confidence=1.0, **r)

        # 3. Persistent knowledge base (exact -> semantic), only user-verified & fresh answers are auto-used
        suggestion, note = None, None
        m = await kb.find_answer(self.uid, label, f["category"])
        if m:
            if m["auto_use"] and (r := await self.resolve(f, m["answer"])):
                await kb.touch(m["entry_id"])
                return self._item(f, action="fill", source="knowledge_base", confidence=m["confidence"],
                                  kb_entry_id=m["entry_id"], note=m["reason"], **r)
            suggestion, note = m["answer"], m["reason"]

        # 4. Profile preference values (notice period, salary ...) -> auto-fill if non-sensitive, else suggest
        pk = PREF_KEYS.get(f["category"])
        if pk and (pv := profile_value(self.profile, pk)):
            if not f["sensitive"] and not suggestion and (r := await self.resolve(f, pv)):
                return self._item(f, action="fill", source="profile", confidence=0.9, **r)
            suggestion = suggestion or pv
            note = note or "from your profile"

        # 5. AI-written free text (never for sensitive categories). Clearly labelled, always reviewed.
        if not f["sensitive"] and kind in ("text", "textarea") and (GENERATIVE_RE.search(label) or f.get("llm_generative")):
            if OPTIONAL_FREE_RE.search(label) and not f["required"]:
                return self._item(f, action="skip", status="skipped", note="Optional free-text field left blank")
            facts = self._facts if self._facts is not None else await kb.verified_facts(self.uid)
            self._facts = facts
            txt = await generate_free_text(self.profile, self.job, f, facts)
            if txt:
                return self._item(f, action="fill", source="ai_generated", value=txt, confidence=0.6,
                                  flags=["ai_generated", "needs_review"])
            note = "I couldn't draft this one automatically"

        # 6. Value already present on the page (e.g. account prefill) and not sensitive -> keep, but flag it
        if f.get("value") and not f["sensitive"]:
            return self._item(f, action="keep", status="kept", source="prefilled", value=f["value"],
                              flags=["prefilled"], confidence=0.5)

        return self._ask(f, suggestion=suggestion, note=note)
