from __future__ import annotations

import base64
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
        headers["Authorization"] = f"token {token}" # Use 'token' or 'Bearer' for GitHub PAT

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
            params={"per_page": 30, "sort": "updated"},
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
            
            repo_data = {
                "name": repo.get("name"),
                "description": repo.get("description"),
                "language": repo.get("language"),
                "size": repo.get("size"),
                "updated_at": repo.get("updated_at"),
                "topics": repo.get("topics") or [],
                "html_url": repo.get("html_url"),
                "stargazers_count": repo.get("stargazers_count"),
                "readme_content": None
            }
            
            # Fetch README for top 5 repos by stars or recency
            if len(out["repos"]) < 5:
                repo_name = repo.get("name")
                readme_resp = await client.get(f"https://api.github.com/repos/{username}/{repo_name}/readme")
                if readme_resp.status_code == 200:
                    readme_json = readme_resp.json()
                    content_b64 = readme_json.get("content", "")
                    if content_b64:
                        try:
                            decoded = base64.b64decode(content_b64).decode("utf-8", errors="ignore")
                            repo_data["readme_content"] = decoded[:2000] # Limit to 2000 chars
                        except Exception:
                            pass
            
            out["repos"].append(repo_data)

    return out
