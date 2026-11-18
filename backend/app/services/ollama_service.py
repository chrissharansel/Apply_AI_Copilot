import asyncio
import json
import re
import time

import httpx

from ..config import settings


class LLMError(RuntimeError):
    pass


def parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _has_model(names: set[str], wanted: str) -> bool:
    base = wanted.split(":")[0]
    return wanted in names or (":" not in wanted and any(n.split(":")[0] == base for n in names))


class OllamaService:
    """Thin client. Llama only reasons and writes; it never touches the browser or the database."""

    def __init__(self) -> None:
        self._embed_down_until = 0.0

    @property
    def base(self) -> str:
        return settings.ollama_base_url.rstrip("/")

    async def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        async with httpx.AsyncClient(timeout=timeout or settings.ollama_timeout) as c:
            r = await c.post(self.base + path, json=payload)
            r.raise_for_status()
            return r.json()

    async def chat_json(self, system: str, user: str, temperature: float = 0.1,
                        max_tokens: int = 1500) -> dict:
        last: Exception | None = None
        for _ in range(3):
            try:
                data = await self._post("/api/chat", {
                    "model": settings.ollama_model, "stream": False, "format": "json",
                    "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": max_tokens},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                })
            except httpx.HTTPError as e:
                last = e
                await asyncio.sleep(1.5)
                continue
            parsed = parse_json(data.get("message", {}).get("content", ""))
            if isinstance(parsed, dict):
                return parsed
            user += "\n\nYour previous reply was not valid JSON. Reply with exactly one JSON object."
        raise LLMError(f"Ollama did not return usable output ({last or 'invalid JSON'}). "
                       f"Is Ollama running with '{settings.ollama_model}' pulled?")

    async def embed(self, text: str) -> list[float] | None:
        if time.time() < self._embed_down_until:
            return None
        try:
            data = await self._post("/api/embed", {"model": settings.ollama_embed_model, "input": text}, 30)
            return data["embeddings"][0]
        except Exception:
            self._embed_down_until = time.time() + 60   # lexical matching fallback for a minute
            return None

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(self.base + "/api/tags")
                r.raise_for_status()
            names = {m["name"] for m in r.json().get("models", [])}
            return {"ok": True, "model": settings.ollama_model,
                    "model_available": _has_model(names, settings.ollama_model),
                    "embed_model": settings.ollama_embed_model,
                    "embed_available": _has_model(names, settings.ollama_embed_model)}
        except Exception as e:
            return {"ok": False, "error": str(e), "model": settings.ollama_model}


ollama = OllamaService()
