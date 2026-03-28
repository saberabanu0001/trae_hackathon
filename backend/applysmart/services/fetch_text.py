from __future__ import annotations

import re
from typing import Any

import httpx


def strip_html_to_text(html: str, max_chars: int = 80_000) -> str:
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()[:max_chars]


async def fetch_page_text(url: str, *, timeout_s: float = 20.0) -> tuple[str | None, dict[str, Any]]:
    headers = {
        "User-Agent": "ApplySmartProfileBot/0.1 (+https://example.com)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    }
    meta: dict[str, Any] = {"url": url}
    try:
        async with httpx.AsyncClient(timeout=timeout_s, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            meta["status"] = resp.status_code
            if resp.status_code >= 400:
                return None, meta
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype in ("text/plain", "text/markdown"):
                return resp.text[:80_000], meta
            if "html" in ctype or ctype == "":
                return strip_html_to_text(resp.text), meta
            return None, meta
    except Exception as e:
        meta["error"] = str(e)[:200]
        return None, meta
