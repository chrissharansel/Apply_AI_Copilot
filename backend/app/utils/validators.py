"""SSRF protection: the browser may only reach public internet hosts."""
import asyncio
import ipaddress
import time
from pathlib import Path
from urllib.parse import urlparse

_CACHE: dict[str, tuple[float, bool]] = {}


def _ip_public(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


async def host_is_public(host: str) -> bool:
    host = host.strip("[]").lower()
    hit = _CACHE.get(host)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        if host == "localhost" or host.endswith((".local", ".internal", ".localhost", ".lan")):
            ips = []
        else:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None)
                ips = list({i[4][0] for i in infos})
            except OSError:
                ips = []
    ok = bool(ips) and all(_ip_public(i) for i in ips)
    _CACHE[host] = (time.time(), ok)
    return ok


async def validate_job_url(url: str) -> str:
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Enter a full job application link starting with http:// or https://")
    if p.username or p.password:
        raise ValueError("Links with embedded credentials are not allowed.")
    if not await host_is_public(p.hostname):
        raise ValueError("That address is private or can't be resolved. Only public websites are allowed.")
    return url


def validate_resume_upload(filename: str, data: bytes, max_mb: int) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise ValueError("Upload a PDF or DOCX file.")
    if len(data) > max_mb * 1024 * 1024:
        raise ValueError(f"File is larger than {max_mb} MB.")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("This file isn't a valid PDF.")
    if ext == ".docx" and not data.startswith(b"PK"):
        raise ValueError("This file isn't a valid DOCX.")
    return ext
