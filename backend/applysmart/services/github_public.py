from __future__ import annotations

import os
import re
from typing import Any

import httpx


_GH_USER = re.compile(r"github\.com/(?P<user>[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})")


def parse_github_username(url_or_handle: str) -> str | None:
    s = (url_or_handle or "").strip()
    if not s:
        return None
    if "/" not in s and "github.com" not in s:
        return s.lstrip("@")
    m = _GH_USER.search(s)
    return m.group("user") if m else None


async def fetch_public_github(
    username: str,
    *,
    timeout_s: float = 25.0,
    max_repos: int = 15,
) -> dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ApplySmart-ProfileAgent/0.1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: dict[str, Any] = {"username": username, "profile": None, "repos": [], "error": None}

    async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as client:
        u = await client.get(f"https://api.github.com/users/{username}")
        if u.status_code != 200:
            out["error"] = f"github user HTTP {u.status_code}"
            return out
        profile = u.json()
        out["profile"] = {
            "login": profile.get("login"),
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "company": profile.get("company"),
            "blog": profile.get("blog"),
            "location": profile.get("location"),
            "public_repos": profile.get("public_repos"),
            "html_url": profile.get("html_url"),
        }

        r = await client.get(
            f"https://api.github.com/users/{username}/repos",
            params={"per_page": max(1, min(max_repos, 30)), "sort": "updated"},
        )
        if r.status_code != 200:
            out["error"] = f"github repos HTTP {r.status_code}"
            return out
        repos = r.json()
        if not isinstance(repos, list):
            out["error"] = "github repos unexpected shape"
            return out

        for repo in repos[:max_repos]:
            if not isinstance(repo, dict):
                continue
            out["repos"].append(
                {
                    "name": repo.get("name"),
                    "description": repo.get("description"),
                    "language": repo.get("language"),
                    "topics": repo.get("topics") or [],
                    "html_url": repo.get("html_url"),
                    "stargazers_count": repo.get("stargazers_count"),
                }
            )

    return out
