from __future__ import annotations

import asyncio

from applysmart.models.core import ApplySmartState, Profile, ProfileGaps
from applysmart.services.profile_ingest import ingest_profile_sources


def profile_agent(state: ApplySmartState) -> ApplySmartState:
    """
    Profile Agent: form fields + optional public sources (GitHub, portfolio URLs,
    best-effort LinkedIn page, resume text). Produces structured fields for matching
    and auto-CV generation.
    """
    profile = state.profile or Profile()

    has_sources = bool(
        (profile.github_url and profile.github_url.strip())
        or (profile.linkedin_url and profile.linkedin_url.strip())
        or profile.portfolio_urls
        or (profile.resume_text and profile.resume_text.strip())
    )

    if has_sources:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                profile, _ = asyncio.run(ingest_profile_sources(profile))
            except Exception:
                pass

    missing: list[str] = []
    notes: list[str] = list(profile.ingest_meta.get("last_ingest", {}).get("warnings", []) or [])

    if not profile.full_name.strip():
        missing.append("full_name")
    if not profile.major.strip():
        missing.append("major")
    if profile.gpa <= 0:
        missing.append("gpa")

    if not profile.github_url and profile.degree_level in ("master", "phd") and "computer" in profile.major.lower():
        notes.append("Tip: add a public GitHub URL — strongest signal for CS/engineering profiles.")

    if not profile.resume_text and not profile.portfolio_urls:
        notes.append("Tip: upload a resume or add a portfolio link to improve extracted strengths.")

    if not profile.has_ielts:
        notes.append("No IELTS on profile; prioritize opportunities that do not require it.")
    if profile.budget_usd == 0:
        notes.append("Budget is $0; prioritize fully-funded programs.")

    return state.model_copy(
        update={"profile": profile, "gaps": ProfileGaps(missing=missing, notes=notes)}
    )
