from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str | None = None
    source: str = "unknown"
    raw: dict[str, Any] | None = None


class WebSearchClient(Protocol):
    async def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]: ...


class SerperClient:
    """
    Uses `https://google.serper.dev/search`.
    Set env var: `SERPER_API_KEY`.
    """

    def __init__(self, api_key: str, *, timeout_s: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": self._api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": max_results},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in (data.get("organic") or [])[:max_results]:
            url = item.get("link")
            title = item.get("title")
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=str(title),
                    url=str(url),
                    snippet=item.get("snippet"),
                    source="serper",
                    raw=item,
                )
            )
        return results


class TavilyClient:
    """
    Uses `https://api.tavily.com/search`.
    Set env var: `TAVILY_API_KEY`.
    """

    def __init__(self, api_key: str, *, timeout_s: float = 20.0) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in (data.get("results") or [])[:max_results]:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            results.append(
                SearchResult(
                    title=str(title),
                    url=str(url),
                    snippet=item.get("content") or item.get("snippet"),
                    source="tavily",
                    raw=item,
                )
            )
        return results


class DuckDuckGoClient:
    """
    Uses DuckDuckGo's 'lite' search via HTML scrape (no API key required).
    Good fallback for hackathon, though Tavily/Serper are better for structure.
    """
    async def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        results: list[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # DuckDuckGo Lite is easier to parse
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query}
                )
                if resp.status_code != 200:
                    return []
                
                # Crude regex extraction for hackathon speed
                # Pattern: <a class="result__a" href="...">Title</a>
                matches = re.findall(r'<a class="result__a" href="(?P<url>[^"]+)">(?P<title>[^<]+)</a>', resp.text)
                for i, (url, title) in enumerate(matches[:max_results]):
                    # Clean URL (DDG Lite wraps them)
                    if "/l/?kh=-1&uddg=" in url:
                        url = url.split("uddg=")[1].split("&")[0]
                        import urllib.parse
                        url = urllib.parse.unquote(url)
                    
                    results.append(SearchResult(
                        title=title.strip(),
                        url=url,
                        source="duckduckgo"
                    ))
        except Exception:
            pass
        return results


def get_default_search_client() -> WebSearchClient | None:
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        return SerperClient(serper_key)

    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        return TavilyClient(tavily_key)

    # Fallback to DuckDuckGo (no key needed)
    return DuckDuckGoClient()
