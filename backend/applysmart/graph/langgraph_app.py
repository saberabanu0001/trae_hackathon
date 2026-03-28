from __future__ import annotations

from typing import Any, Callable, Dict

from langgraph.graph import END, StateGraph

from applysmart.agents import (
    critic_agent,
    drafting_agent,
    followup_agent,
    opportunity_agent,
    planning_agent,
    profile_agent,
    scoring_agent,
)
from applysmart.models.core import ApplySmartState
from applysmart.services.rerank import apply_critic_demotion


StateDict = Dict[str, Any]


import inspect

def _adapt(agent_fn: Callable[[ApplySmartState], ApplySmartState]) -> Callable[[StateDict], StateDict]:
    async def _wrapped(state: StateDict) -> StateDict:
        parsed = ApplySmartState.model_validate(state)
        if inspect.iscoroutinefunction(agent_fn):
            updated = await agent_fn(parsed)
        else:
            updated = agent_fn(parsed)
        return updated.model_dump()

    return _wrapped


def _veto_handler(state: StateDict) -> StateDict:
    parsed = ApplySmartState.model_validate(state)
    critic = parsed.critic
    if critic is None or critic.action != "block":
        return parsed.model_dump()
    blocked_title = critic.affected_title
    updated = apply_critic_demotion(parsed, reason=critic.reason)
    trace = list(updated.meta.get("critic_trace", []))
    trace.append({"event": "demoted", "title": blocked_title})
    updated = updated.model_copy(
        update={
            "critic": None,
            "meta": {**updated.meta, "critic_trace": trace},
        }
    )
    return updated.model_dump()


def _route_after_critic(state: StateDict) -> str:
    parsed = ApplySmartState.model_validate(state)
    critic = parsed.critic
    veto_count = int(parsed.meta.get("veto_count", 0))
    if critic is not None and critic.action == "block" and veto_count < 8:
        return "veto_handler"
    return "planning"


def build_app():
    g = StateGraph(StateDict)

    g.add_node("profile", _adapt(profile_agent))
    g.add_node("opportunity", _adapt(opportunity_agent))
    g.add_node("scoring", _adapt(scoring_agent))
    g.add_node("critic", _adapt(critic_agent))
    g.add_node("veto_handler", _veto_handler)
    g.add_node("planning", _adapt(planning_agent))
    g.add_node("drafting", _adapt(drafting_agent))
    g.add_node("followup", _adapt(followup_agent))

    g.set_entry_point("profile")
    g.add_edge("profile", "opportunity")
    g.add_edge("opportunity", "scoring")
    g.add_edge("scoring", "critic")

    g.add_conditional_edges("critic", _route_after_critic)
    g.add_edge("veto_handler", "scoring")

    g.add_edge("planning", "drafting")
    g.add_edge("drafting", "followup")
    g.add_edge("followup", END)

    return g.compile()

