from __future__ import annotations

from applysmart.models.core import ApplySmartState, Opportunity


def _matches_blocked(opp: Opportunity, blocked: Opportunity) -> bool:
    if blocked.url and opp.url and opp.url == blocked.url:
        return True
    return opp.title == blocked.title


def apply_critic_demotion(state: ApplySmartState, reason: str) -> ApplySmartState:
    """
    Persist demotion on the *opportunities* list so the next Scoring pass sees it.
    Strips demo_pin_top (hackathon pin) and adds a cumulative score penalty in raw.
    """
    if not state.scored:
        return state

    blocked = state.scored[0].opportunity
    veto_count = int(state.meta.get("veto_count", 0))

    new_opps: list[Opportunity] = []
    for o in state.opportunities:
        if not _matches_blocked(o, blocked):
            new_opps.append(o)
            continue
        raw = dict(o.raw)
        raw.pop("demo_pin_top", None)
        prev = float(raw.get("critic_score_penalty") or 0)
        raw["critic_score_penalty"] = prev + 0.55
        raw["critic_last_demotion"] = reason[:500]
        new_opps.append(o.model_copy(update={"raw": raw}))

    return state.model_copy(
        update={
            "opportunities": new_opps,
            "meta": {**state.meta, "veto_count": veto_count + 1},
        }
    )
