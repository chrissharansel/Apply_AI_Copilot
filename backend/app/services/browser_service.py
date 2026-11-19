"""Owns Playwright. One isolated context per agent session. Every request is checked against the SSRF policy."""
import asyncio
import time
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings
from ..utils.validators import host_is_public


class BrowserManager:
    def __init__(self) -> None:
        self.pw = None
        self.browsers: dict[bool, object] = {}              # headless flag -> browser (launched lazily)
        self.sessions: dict[str, tuple] = {}

    async def _ensure(self, headless: bool):
        from playwright.async_api import async_playwright
        if self.pw is None:
            self.pw = await async_playwright().start()
        if headless not in self.browsers:
            self.browsers[headless] = await self.pw.chromium.launch(headless=headless)
        return self.browsers[headless]

    async def _guard(self, route) -> None:
        url = route.request.url
        if url.startswith(("data:", "blob:", "about:")):
            return await route.continue_()
        p = urlparse(url)
        if p.scheme not in ("http", "https", "ws", "wss") or not p.hostname or not await host_is_public(p.hostname):
            return await route.abort("blockedbyclient")
        await route.continue_()

    async def new_page(self, sid: str, headless: bool | None = None):
        browser = await self._ensure(settings.headless if headless is None else headless)
        await self.close(sid)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block",
                                             accept_downloads=False)
        await ctx.route("**/*", self._guard)
        page = await ctx.new_page()
        page.set_default_timeout(15000)

        async def on_dialog(d):                              # never block on JS dialogs; confirm() is declined
            await (d.accept() if d.type == "alert" else d.dismiss())
        page.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))
        self.sessions[sid] = (ctx, page)
        return page

    def get(self, sid: str):
        s = self.sessions.get(sid)
        return s[1] if s else None

    async def close(self, sid: str) -> None:
        s = self.sessions.pop(sid, None)
        if s:
            try:
                await s[0].close()
            except Exception:
                pass

    async def screenshot(self, sid: str) -> str | None:
        page = self.get(sid)
        if not page:
            return None
        folder = Path(settings.storage_dir) / "screenshots" / sid
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "latest.png"
        try:
            await page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return None

    async def shutdown(self) -> None:
        for sid in list(self.sessions):
            await self.close(sid)
        for b in self.browsers.values():
            await b.close()
        if self.pw:
            await self.pw.stop()
        self.browsers, self.pw = {}, None


bm = BrowserManager()
