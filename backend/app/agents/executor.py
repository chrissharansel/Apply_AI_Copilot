"""Performs browser actions. Executes only what the planner decided, and verifies every write by reading it back.
Strategies per control: native inputs, native/multi selects, searchable & custom (ARIA/React) dropdowns,
ARIA radios/checkboxes/switches, masked inputs, date pickers, contenteditable rich text, file uploads."""
import asyncio
import re

from .observer import LIST_OPTIONS_JS, PICK_OPTION_JS, SHOWS_JS


def _n(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


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


def same(got, want, maxlength=None) -> bool:
    a, b = _n(got), _n(want)
    if a == b:
        return True
    if len(_digits(want)) >= 7 and _digits(got) == _digits(want):        # masked phone/number formats
        return True
    return len(a) > 20 and b.startswith(a)                               # site-enforced maxlength truncation


class Executor:
    def __init__(self, page, resume_path: str | None):
        self.page, self.resume_path = page, resume_path

    # ------------------------------------------------------------------ dropdown helpers
    async def _each_frame(self, js: str, arg=None):
        for frame in self.page.frames:
            try:
                r = await frame.evaluate(js, arg) if arg is not None else await frame.evaluate(js)
            except Exception:
                continue
            if r:
                yield frame, r

    async def _visible_options(self) -> list[str]:
        out: list[str] = []
        async for _, r in self._each_frame(LIST_OPTIONS_JS):
            out += r
        return list(dict.fromkeys(out))

    async def read_options(self, agent_id: str) -> list[str]:
        """Open a custom dropdown, read its choices, close it. Async-search boxes yield [] (handled by typing later)."""
        loc = await locate(self.page, agent_id)
        if loc is None:
            return []
        try:
            await loc.scroll_into_view_if_needed(timeout=2000)
            await loc.click(timeout=3000)
            await asyncio.sleep(0.5)
            opts = await self._visible_options()
            if not opts:
                await loc.press("ArrowDown")
                await asyncio.sleep(0.4)
                opts = await self._visible_options()
            await self.page.keyboard.press("Escape")
            return opts
        except Exception:
            try:
                await self.page.keyboard.press("Escape")
            except Exception:
                pass
            return []

    async def _pick_option(self, loc, label: str) -> bool:
        tag = await loc.evaluate("e => e.tagName.toLowerCase()")
        await loc.click(timeout=4000)
        if tag == "input":                                           # searchable dropdown: type to filter
            try:
                await loc.fill("")
                await loc.press_sequentially(label[:40], delay=25)
            except Exception:
                pass
        await asyncio.sleep(0.6)
        hit = None
        async for frame, r in self._each_frame(PICK_OPTION_JS, label):
            hit = frame
            break
        if hit is None and tag == "input":                           # nothing matched: let the widget choose its first hit
            await loc.press("ArrowDown")
            await loc.press("Enter")
        elif hit is not None:
            await hit.locator('[data-agent-opt="1"]').first.click(timeout=4000)
            await hit.evaluate("() => document.querySelectorAll('[data-agent-opt]').forEach(e => e.removeAttribute('data-agent-opt'))")
        await asyncio.sleep(0.3)
        ok = await loc.evaluate(SHOWS_JS, label)
        try:
            await self.page.keyboard.press("Escape")
        except Exception:
            pass
        return bool(ok)

    # ------------------------------------------------------------------ main entry
    async def fill(self, item: dict) -> dict:
        kind, v = item["kind"], item.get("value")
        try:
            if kind == "radio" or kind == "checkbox_group":
                return await self._choice_group(item)
            loc = await locate(self.page, item["field_id"])
            if loc is None:
                return {"ok": False, "error": "Field disappeared from the page"}
            try:
                await loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            custom = item.get("custom", "native")

            if kind == "file":
                if not self.resume_path:
                    return {"ok": False, "error": "No resume file available"}
                await loc.set_input_files(self.resume_path)
                return {"ok": await loc.evaluate("e => !!(e.files && e.files.length)")}
            if kind == "select":
                try:
                    await loc.select_option(value=item["option_ids"][0])
                except Exception:
                    await loc.select_option(label=str(v))
                return {"ok": await loc.evaluate("(e, w) => [...e.selectedOptions].some(o => o.value === w || o.text.trim() === w)", item["option_ids"][0]) or
                        await loc.evaluate("(e, w) => [...e.selectedOptions].some(o => o.text.trim() === w)", str(v))}
            if kind == "multiselect":
                await loc.select_option(value=item["option_ids"])
                chosen = await loc.evaluate("e => [...e.selectedOptions].map(o => o.value)")
                return {"ok": set(chosen) == set(item["option_ids"])}
            if kind == "checkbox":
                want = bool(item.get("bool", item.get("value") == "Checked"))
                if custom == "aria_checkbox":
                    return {"ok": await self._aria_toggle(loc, want)}
                await loc.set_checked(want, force=True)
                return {"ok": await loc.is_checked() == want}
            if kind == "combobox":
                labels = item["option_ids"] if item.get("multi") and item.get("option_ids") else [str(v)]
                for lab in labels:
                    if not await self._pick_option(loc, lab):
                        return {"ok": False, "error": f"Couldn't select “{lab}” in the dropdown"}
                return {"ok": True}
            if kind == "richtext":
                await loc.click()
                await self.page.keyboard.press("Control+A")
                await self.page.keyboard.insert_text(str(v))
                got = await loc.evaluate("e => e.innerText")
                return {"ok": same(got, v)}
            return await self._text(loc, str(v), kind)
        except Exception as e:
            return {"ok": False, "error": str(e).splitlines()[0][:160]}

    async def _text(self, loc, v: str, kind: str) -> dict:
        await loc.fill(v)
        got = await loc.input_value()
        if not same(got, v):                                         # masked / React-controlled inputs: type like a human
            await loc.click()
            await loc.fill("")
            await loc.press_sequentially(v, delay=12)
            got = await loc.input_value()
        if kind == "date" and not same(got, v):
            return {"ok": False, "error": f"Date field kept “{got}”"}
        try:
            await loc.blur()                                         # trigger blur validation / date-picker commit
        except Exception:
            pass
        return {"ok": same(got, v)}

    async def _aria_toggle(self, loc, want: bool) -> bool:
        cur = (await loc.get_attribute("aria-checked")) == "true"
        if cur != want:
            await loc.click(timeout=4000)
            await asyncio.sleep(0.2)
        return ((await loc.get_attribute("aria-checked")) == "true") == want

    async def _choice_group(self, item: dict) -> dict:
        wanted = set(item["option_ids"])
        for o in item["options"]:
            loc = await locate(self.page, o["id"])
            if loc is None:
                return {"ok": False, "error": "Option not found"}
            on = o["id"] in wanted
            if item["kind"] == "radio" and not on:
                continue
            tag = await loc.evaluate("e => e.tagName.toLowerCase()")
            if tag != "input":                                       # ARIA radio / checkbox
                if not await self._aria_toggle(loc, on):
                    return {"ok": False, "error": "Selection did not stick"}
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
