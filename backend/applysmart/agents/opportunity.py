from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta

from applysmart.models.core import ApplySmartState, Opportunity
from applysmart.services.opportunity_search import search_opportunities


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _demo_veto_opportunity(today: date) -> Opportunity:
    return Opportunity(
        title="Erasmus Mundus (EMJMD) — Demo veto (IELTS + GPA floor + tight deadline)",
        country="EU",
        url="https://example.com/applysmart-demo-veto",
        deadline=today + timedelta(days=10),
        fully_funded=True,
        requires_ielts=True,
        minimum_gpa=3.5,
        estimated_fees_usd=0,
        raw={
            "source": "demo_veto",
            "demo_pin_top": True,
        },
    )


def _maybe_prepend_demo_veto(opportunities: list[Opportunity], today: date) -> list[Opportunity]:
    if not _env_truthy("APPLYSMART_DEMO_VETO"):
        return opportunities
    return [_demo_veto_opportunity(today), *opportunities]


def opportunity_agent(state: ApplySmartState) -> ApplySmartState:
    """
    Option A (Search API):
    - If an API key is configured, fetch live web results and rank on those (no cached merge).
    - Falls back to cached demo opportunities if search is unavailable.
    - Set APPLYSMART_DEMO_VETO=1 to pin a guaranteed “bad #1” for Critic + rerank demos.
    """
    today = date.today()

    cached = [
        Opportunity(
            title="Erasmus Mundus Joint Masters (EMJMD)",
            country="EU/Global",
            url="https://example.com/erasmus-mundus",
            deadline=today + timedelta(days=10),
            fully_funded=True,
            requires_ielts=True,
            minimum_gpa=3.5,
            estimated_fees_usd=0,
            snippet="High-prestige fully funded masters programs in Europe for international students.",
            raw={"source": "cached"},
        ),
        Opportunity(
            title="Korea GKS Graduate Scholarship",
            country="South Korea",
            url="https://example.com/gks-scholarship",
            deadline=today + timedelta(days=180),
            fully_funded=True,
            requires_ielts=False,
            minimum_gpa=2.8,
            estimated_fees_usd=0,
            snippet="Government-funded graduate scholarship for international students to study in South Korea.",
            raw={"source": "cached"},
        ),
        Opportunity(
            title="DAAD Germany Development-Related Postgraduate Courses",
            country="Germany",
            url="https://example.com/daad-scholarship",
            deadline=today + timedelta(days=95),
            fully_funded=True,
            requires_ielts=True,
            minimum_gpa=3.0,
            estimated_fees_usd=0,
            snippet="Fully funded masters and PhD scholarships for professionals from developing countries.",
            raw={"source": "cached"},
        ),
        Opportunity(
            title="Australia Awards Scholarship",
            country="Australia",
            url="https://example.com/australia-awards",
            deadline=today + timedelta(days=45),
            fully_funded=True,
            requires_ielts=True,
            minimum_gpa=3.0,
            estimated_fees_usd=0,
            snippet="Prestigious international scholarships funded by the Australian Government for students from partner countries.",
            raw={"source": "cached", "demo_pin_top": True},
        ),
    ]

    profile = state.profile
    if profile is None:
        return state.model_copy(update={"opportunities": cached})

    try:
        # Fixed async execution for both script and FastAPI contexts
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If in a running loop (like FastAPI), we must run this as a task and wait
            # But since this is a LangGraph node, we can just await it directly if we make the agent async
            # For now, let's use a safe synchronous bridge for the demo script
            import nest_asyncio
            nest_asyncio.apply()
            query, live = asyncio.run(search_opportunities(profile, max_results=15))
        else:
            query, live = asyncio.run(search_opportunities(profile, max_results=15))
    except Exception as e:
        print(f"[OpportunityAgent] Search failed: {e}")
        query, live = "", []

    demo_flag = _env_truthy("APPLYSMART_DEMO_VETO")

    if live:
        opportunities = _maybe_prepend_demo_veto(list(live), today)
        return state.model_copy(
            update={
                "opportunities": opportunities,
                "meta": {
                    **state.meta,
                    "opportunity_source": "live",
                    "opportunity_query": query,
                    "opportunity_live_count": len(live),
                    "demo_veto_enabled": demo_flag,
                },
            }
        )

    opportunities = _maybe_prepend_demo_veto(list(cached), today)
    return state.model_copy(
        update={
            "opportunities": opportunities,
            "meta": {
                **state.meta,
                "opportunity_source": "cached_demo",
                "demo_veto_enabled": demo_flag,
            },
        }
    )
