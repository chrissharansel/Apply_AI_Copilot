"""Performs browser actions. Executes only what the planner decided; verifies every write by reading it back."""
import asyncio
import re


def _n(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


async def locate(page, agent_id: str):
    sel = f'[data-agent-id="{agent_id}"]'
    for frame in page.frames:
        try:
            loc = frame.locator(sel)
            if await loc.count():
                return loc.first
        except Exception:
            continue
    return None


class Executor:
    def __init__(self, page, resume_path: str | None):
        self.page, self.resume_path = page, resume_path

    async def fill(self, item: dict) -> dict:
        kind, v = item["kind"], item.get("value")
        try:
            if kind in ("radio", "checkbox_group"):
                return await self._choice_group(item)
            loc = await locate(self.page, item["field_id"])
            if loc is None:
                return {"ok": False, "error": "Field disappeared from the page"}
            try:
                await loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            if kind == "file":
                if not self.resume_path:
                    return {"ok": False, "error": "No resume file available"}
                await loc.set_input_files(self.resume_path)
                ok = await loc.evaluate("e => !!(e.files && e.files.length)")
                return {"ok": ok}
            if kind == "select":
                await loc.select_option(value=item["option_ids"][0])
                got = await loc.evaluate("e => e.value")
                return {"ok": got == item["option_ids"][0]}
            if kind == "checkbox":
                want = bool(item.get("bool", item.get("value") == "Checked"))
                await loc.set_checked(want, force=True)
                return {"ok": await loc.is_checked() == want}
            if kind == "combobox":
                await loc.fill(str(v))
                await asyncio.sleep(0.6)
                await loc.press("ArrowDown")
                await loc.press("Enter")
                shown = await loc.evaluate("e => (e.value || '') + ' ' + ((e.closest('div') || {}).innerText || '')")
                return {"ok": _n(str(v))[:12] in _n(shown)}
            await loc.fill(str(v))                                  # text, textarea, email, tel, number, date
            got = await loc.input_value()
            a, b = _n(got), _n(v)
            return {"ok": a == b or (len(a) > 20 and b.startswith(a))}   # tolerate site-enforced maxlength
        except Exception as e:
            return {"ok": False, "error": str(e).splitlines()[0][:160]}

    async def _choice_group(self, item: dict) -> dict:
        wanted = set(item["option_ids"])
        for o in item["options"]:
            loc = await locate(self.page, o["id"])
            if loc is None:
                return {"ok": False, "error": "Option not found"}
            on = o["id"] in wanted
            if item["kind"] == "radio" and not on:
                continue
            try:
                await loc.set_checked(on, force=True)
            except Exception:
                await loc.evaluate("e => e.click()")
            if await loc.is_checked() != on:
                return {"ok": False, "error": "Selection did not stick"}
        return {"ok": True}

    async def click(self, agent_id: str, *, submit: bool = False, approved: bool = False) -> None:
        if submit and not approved:
            raise PermissionError("Refusing to submit without explicit user approval")
        loc = await locate(self.page, agent_id)
        if loc is None:
            raise RuntimeError("Button not found on the page")
        try:
            await loc.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        await loc.click(timeout=10000)
