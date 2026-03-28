from __future__ import annotations

import re
from datetime import date

from applysmart.models.core import Opportunity, Profile


def snippet_text(opp: Opportunity) -> str:
    parts: list[str] = []
    s = opp.raw.get("snippet")
    if isinstance(s, str):
        parts.append(s)
    sr = opp.raw.get("search_raw")
    if isinstance(sr, dict):
        for k in ("snippet", "title", "content"):
            v = sr.get(k)
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts).lower()


def effective_requires_ielts(opp: Opportunity) -> bool | None:
    if opp.requires_ielts is not None:
        return opp.requires_ielts
    t = snippet_text(opp)
    if not t.strip():
        return None
    if re.search(r"\bielts\b.{0,50}\b(not required|optional|waived|exempt)\b", t):
        return False
    if re.search(r"\b(ielts required|required.*ielts|ielts score|ielts academic)\b", t):
        return True
    if re.search(r"\bwithout ielts\b", t):
        return False
    return None


def eligibility_failures(
    profile: Profile, opp: Opportunity, *, has_drafted_materials: bool
) -> list[str]:
    """Human-readable hard failures for the top-ranked opportunity (Critic WOW copy)."""
    failures: list[str] = []
    ielts = effective_requires_ielts(opp)
    if ielts is True and not profile.has_ielts:
        failures.append("IELTS required but profile has no IELTS.")

    if opp.minimum_gpa is not None:
        gpa4 = profile.gpa_as_us_four_point()
        if gpa4 < opp.minimum_gpa:
            failures.append(
                f"GPA below stated minimum (~{gpa4:.2f}/4.0 vs {opp.minimum_gpa:.2f}; "
                f"your {profile.gpa:.2f}/{profile.gpa_scale_max:g})."
            )

    if opp.deadline is not None and not has_drafted_materials:
        days = (opp.deadline - date.today()).days
        if days >= 0 and days < 14:
            failures.append(f"Deadline in {days} days (<14) with no drafted materials.")

    return failures
