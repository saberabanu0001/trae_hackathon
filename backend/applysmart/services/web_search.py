from __future__ import annotations

import os
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


def get_default_search_client() -> WebSearchClient | None:
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        return SerperClient(serper_key)

    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        return TavilyClient(tavily_key)

    return None

