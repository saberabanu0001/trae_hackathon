from __future__ import annotations

import asyncio
from typing import Any

from applysmart.models.core import Profile
from applysmart.services.fetch_text import fetch_page_text
from applysmart.services.github_public import fetch_public_github, parse_github_username
from applysmart.services.profile_extract_heuristic import (
    extract_languages_from_text,
    extract_resume_bullets,
)


async def ingest_profile_sources(profile: Profile) -> tuple[Profile, dict[str, Any]]:
    """
    Pull public GitHub + optional portfolio pages + best-effort LinkedIn URL fetch.
    Merges heuristics into Profile fields used for opportunity matching & auto-CV.
    """
    ingest: dict[str, Any] = {"sources": [], "warnings": []}

    gh_user = parse_github_username(profile.github_url or "")
    gh_payload: dict[str, Any] | None = None
    tasks = []

    if gh_user:
        ingest["sources"].append("github_api")

        async def _gh() -> None:
            nonlocal gh_payload
            gh_payload = await fetch_public_github(gh_user)

        tasks.append(asyncio.create_task(_gh()))

    portfolio_texts: dict[str, str] = {}

    async def _fetch_portfolio(u: str) -> None:
        text, meta = await fetch_page_text(u)
        portfolio_texts[u] = text or ""
        if text is None:
            ingest["warnings"].append(f"portfolio_fetch:{meta.get('status') or meta.get('error')}")

    for url in profile.portfolio_urls[:5]:
        if not url or not url.startswith("http"):
            continue
        ingest["sources"].append(f"portfolio:{url[:48]}")
        tasks.append(asyncio.create_task(_fetch_portfolio(url)))

    linkedin_text: str | None = None
    if profile.linkedin_url and profile.linkedin_url.startswith("http"):
        ingest["sources"].append("linkedin_url_attempt")

        async def _li() -> None:
            nonlocal linkedin_text
            text, meta = await fetch_page_text(profile.linkedin_url or "")
            linkedin_text = text
            if text is None or (text and len(text) < 200):
                ingest["warnings"].append(
                    "linkedin_limited: public fetch often blocked; paste highlights or resume."
                )

        tasks.append(asyncio.create_task(_li()))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- Merge GitHub ---
    languages_count: dict[str, int] = {}
    projects: list[str] = []
    topics: list[str] = []

    if gh_payload and not gh_payload.get("error"):
        p = gh_payload.get("profile") or {}
        gh_name = p.get("name")
        if gh_name and (not profile.full_name.strip() or profile.full_name == "Demo Student"):
            profile = profile.model_copy(update={"full_name": str(gh_name)})

        bio = (p.get("bio") or "").strip()
        loc = (p.get("location") or "").strip()
        blog = (p.get("blog") or "").strip()

        for repo in gh_payload.get("repos") or []:
            if not isinstance(repo, dict):
                continue
            lang = repo.get("language")
            if isinstance(lang, str) and lang:
                languages_count[lang] = languages_count.get(lang, 0) + 1
            desc = (repo.get("description") or "").strip()
            name = repo.get("name") or ""
            line = f"{name}: {desc}" if desc else str(name)
            if line:
                projects.append(line)
            for tp in repo.get("topics") or []:
                if isinstance(tp, str) and tp:
                    topics.append(tp)

        strengths: list[str] = []
        if projects:
            strengths.append(f"Public GitHub activity: {len(projects)} recent repositories considered.")
        stars = sum(int(r.get("stargazers_count") or 0) for r in (gh_payload.get("repos") or []) if isinstance(r, dict))
        if stars > 0:
            strengths.append(f"Sampled repositories show ~{stars} total stars (weak community signal / popularity hint).")

        ri = list({t.replace("-", " ") for t in topics})[:12]
        if bio:
            ri.insert(0, bio[:240])

        langs_sorted = [k for k, _ in sorted(languages_count.items(), key=lambda kv: (-kv[1], kv[0]))]

        consistency = profile.consistency_summary or ""
        if gh_name and profile.full_name and gh_name.split()[0].lower() not in profile.full_name.lower():
            consistency = (
                (consistency + " ")
                + f"Display name on GitHub ({gh_name}) differs from profile name ({profile.full_name}); verify identity."
            ).strip()

        profile = profile.model_copy(
            update={
                "languages": _uniq_keep_order(profile.languages + langs_sorted),
                "projects": _uniq_keep_order(profile.projects + projects)[:30],
                "research_interests": _uniq_keep_order(profile.research_interests + ri),
                "strengths": _uniq_keep_order(profile.strengths + strengths),
                "consistency_summary": consistency or None,
                "interests": _uniq_keep_order(profile.interests + ri[:5]),
                "ingest_meta": {**profile.ingest_meta, "github": {"user": gh_user, "public_repos": p.get("public_repos")}},
            }
        )
    elif gh_user and gh_payload and gh_payload.get("error"):
        ingest["warnings"].append(f"github:{gh_payload.get('error')}")

    # --- Resume + page text ---
    blob_parts: list[str] = []
    if profile.resume_text:
        blob_parts.append(profile.resume_text)
    blob_parts.extend(portfolio_texts.values())
    if linkedin_text:
        blob_parts.append(linkedin_text)

    big = "\n".join(blob_parts)
    if big.strip():
        langs = extract_languages_from_text(big)
        profile = profile.model_copy(
            update={
                "languages": _uniq_keep_order(profile.languages + langs),
            }
        )
        bullets = extract_resume_bullets(profile.resume_text or big)
        if bullets:
            profile = profile.model_copy(
                update={
                    "strengths": _uniq_keep_order(profile.strengths + bullets[:8]),
                }
            )

    ingest["warnings"] = list(dict.fromkeys(ingest["warnings"]))
    profile = profile.model_copy(update={"ingest_meta": {**profile.ingest_meta, "last_ingest": ingest}})
    return profile, ingest


def _uniq_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = x.strip()
        if not k:
            continue
        key = k.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(k)
    return out
