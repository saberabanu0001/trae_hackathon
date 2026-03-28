from __future__ import annotations

from datetime import date

from applysmart.models.core import (
    ApplySmartState,
    Bucket,
    Opportunity,
    ScoreBreakdown,
    ScoredOpportunity,
)
from applysmart.services.critic_helpers import effective_requires_ielts


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _eligibility_score(profile_gpa: float, has_ielts: bool, opp: Opportunity) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 1.0

    if opp.minimum_gpa is not None and profile_gpa < opp.minimum_gpa:
        score *= 0.2
        reasons.append(
            f"GPA below minimum (~{profile_gpa:.2f}/4.0 vs {opp.minimum_gpa:.2f}, program scale)."
        )

    need_ielts = effective_requires_ielts(opp)
    if need_ielts is True and not has_ielts:
        score *= 0.2
        reasons.append("IELTS required but profile indicates no IELTS.")

    return _clamp01(score), reasons


def _urgency_score(opp: Opportunity) -> float:
    if opp.deadline is None:
        return 0.5
    days = (opp.deadline - date.today()).days
    # closer deadline => higher urgency (but not necessarily better)
    if days <= 0:
        return 0.0
    if days < 14:
        return 1.0
    if days < 60:
        return 0.7
    return 0.4


def _funding_score(profile_budget: int, opp: Opportunity) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if opp.fully_funded is True:
        return 1.0, ["Fully funded."]
    if opp.estimated_fees_usd is None:
        return 0.5, []
    if profile_budget >= opp.estimated_fees_usd:
        return 0.7, ["Budget appears sufficient for fees."]
    return 0.2, ["Budget may be insufficient for program fees."]


def scoring_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None:
        return state

    scored: list[ScoredOpportunity] = []

    # DNA-based fit calculation (Task 4 improvement)
    dna = profile.dna
    tech_depth = dna.technical_depth.score if dna else 50.0
    res_fit = dna.research_track_fit.score if dna else 50.0
    eng_fit = dna.engineering_track_fit.score if dna else 50.0

    for opp in state.opportunities:
        need_ielts = effective_requires_ielts(opp)
        eligibility, eligibility_reasons = _eligibility_score(
            profile_gpa=profile.gpa_as_us_four_point(),
            has_ielts=profile.has_ielts,
            opp=opp,
        )
        urgency = _urgency_score(opp)
        funding, funding_reasons = _funding_score(profile_budget=profile.budget_usd, opp=opp)

        # Smart fit heuristic using DNA
        is_research = "research" in (opp.title + (opp.snippet or "")).lower()
        fit_score = res_fit if is_research else eng_fit
        
        # Bonus for target country match
        if opp.country == profile.target_country:
            fit_score = min(100.0, fit_score + 15.0)
            
        confidence = 0.6 if opp.raw.get("source") == "cached_demo" else 0.4

        breakdown = ScoreBreakdown(
            fit=_clamp01(fit_score / 100.0),
            eligibility=_clamp01(eligibility),
            urgency=_clamp01(urgency),
            funding=_clamp01(funding),
            confidence=_clamp01(confidence),
        )

        total = _clamp01(
            0.30 * breakdown.fit
            + 0.35 * breakdown.eligibility
            + 0.10 * breakdown.urgency
            + 0.15 * breakdown.funding
            + 0.10 * breakdown.confidence
        )

        # Hackathon: optional pin so Critic demo can show #1 veto + rerank.
        if opp.raw.get("demo_pin_top"):
            total = max(total, 0.96)

        penalty = float(opp.raw.get("critic_score_penalty") or 0)
        total = _clamp01(max(0.0, total - penalty))

        # bucket by total
        if total >= 0.75 and eligibility > 0.8:
            bucket = Bucket.safe
        elif total >= 0.50 or eligibility > 0.5:
            bucket = Bucket.target
        else:
            bucket = Bucket.reach

        # Generate personalized match and eligibility strings
        match_insight = "Matches your profile DNA."
        low_title = opp.title.lower()
        if "erasmus" in low_title and "ai" in (opp.title + (opp.snippet or "")).lower():
            match_insight = "AI focus aligns with your multi-agent research."
        elif "gks" in low_title or "korea" in low_title:
            if profile.target_country == "South Korea":
                match_insight = "Good Korea fit because you are already targeting South Korea."
            else:
                match_insight = "Strong academic fit for Korea's government scholarship."
        elif opp.country == profile.target_country:
            match_insight = f"Direct match for your target country {profile.target_country}."
        elif breakdown.fit > 0.8:
            match_insight = f"Strong alignment with your {profile.major} background and projects."

        eligibility_status = "Eligible"
        if eligibility < 0.4:
            eligibility_status = "Blocked"
        elif eligibility < 0.9:
            eligibility_status = "Partially Blocked"

        eligibility_reason = "No major blockers found."
        if eligibility_reasons:
            eligibility_reason = eligibility_reasons[0]
        elif not profile.has_ielts and need_ielts is True:
            eligibility_reason = "IELTS is missing and may be required for this program."

        scored.append(
            ScoredOpportunity(
                opportunity=opp,
                total_score=total,
                bucket=bucket,
                breakdown=breakdown,
                reasons=[match_insight, eligibility_status, eligibility_reason],
            )
        )

    scored.sort(key=lambda s: s.total_score, reverse=True)
    return state.model_copy(update={"scored": scored})

