from __future__ import annotations

from applysmart.models.core import ApplySmartState, CriticDecision
from applysmart.services.critic_helpers import eligibility_failures


def _append_trace(meta: dict, entry: dict) -> dict:
    trace = list(meta.get("critic_trace", []))
    trace.append(entry)
    return {**meta, "critic_trace": trace}


def critic_agent(state: ApplySmartState) -> ApplySmartState:
    """
    Critic veto (hackathon WOW):
    - Evaluates #1 ranked opportunity for IELTS (structured + snippet), GPA floor, tight deadline.
    - Emits a single BLOCK with a count of failures when any hard rule trips.
    """
    profile = state.profile
    if profile is None or not state.scored:
        return state

    top = state.scored[0]
    has_drafted = state.drafts is not None
    failures = eligibility_failures(
        profile, top.opportunity, has_drafted_materials=has_drafted
    )

    # Budget FLAG (non-blocking): program fees may exceed declared budget
    meta = dict(state.meta)
    if (
        top.opportunity.estimated_fees_usd is not None
        and profile.budget_usd < top.opportunity.estimated_fees_usd
    ):
        flags = list(meta.get("critic_flags", []))
        flags.append(
            {
                "kind": "budget",
                "title": top.opportunity.title,
                "note": "Declared budget may be insufficient for fees (user may have other funding).",
            }
        )
        meta = {**meta, "critic_flags": flags}

    if failures:
        n = len(failures)
        reason = (
            f"Blocked: {n} eligibility issue(s). " + " ".join(failures)
        )
        meta = _append_trace(
            meta,
            {
                "action": "block",
                "title": top.opportunity.title,
                "failures": failures,
            },
        )
        return state.model_copy(
            update={
                "critic": CriticDecision(
                    action="block",
                    affected_title=top.opportunity.title,
                    reason=reason,
                ),
                "meta": meta,
            }
        )

    # WARN: all reach
    if all(s.bucket.value == "reach" for s in state.scored):
        meta = _append_trace(
            meta,
            {"action": "warn", "reason": "all_reach"},
        )
        return state.model_copy(
            update={
                "critic": CriticDecision(
                    action="warn",
                    reason="All opportunities are Reach. Add Safe options or confirm you want to proceed.",
                ),
                "meta": meta,
            }
        )

    return state.model_copy(
        update={
            "critic": CriticDecision(action="pass", reason="No veto conditions met."),
            "meta": meta,
        }
    )
