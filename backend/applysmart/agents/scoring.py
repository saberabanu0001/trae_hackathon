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

    for opp in state.opportunities:
        eligibility, eligibility_reasons = _eligibility_score(
            profile_gpa=profile.gpa_as_us_four_point(),
            has_ielts=profile.has_ielts,
            opp=opp,
        )
        urgency = _urgency_score(opp)
        funding, funding_reasons = _funding_score(profile_budget=profile.budget_usd, opp=opp)

        # simple fit heuristic for scaffold
        fit = 0.7 if (opp.country == profile.target_country or opp.fully_funded) else 0.5
        confidence = 0.6 if opp.raw.get("source") == "cached_demo" else 0.4

        breakdown = ScoreBreakdown(
            fit=_clamp01(fit),
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
        if total >= 0.75:
            bucket = Bucket.safe
        elif total >= 0.55:
            bucket = Bucket.target
        else:
            bucket = Bucket.reach

        reasons = []
        reasons.extend(eligibility_reasons)
        reasons.extend(funding_reasons)

        scored.append(
            ScoredOpportunity(
                opportunity=opp,
                total_score=total,
                bucket=bucket,
                breakdown=breakdown,
                reasons=reasons,
            )
        )

    scored.sort(key=lambda s: s.total_score, reverse=True)
    return state.model_copy(update={"scored": scored})

