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
            title="Erasmus Mundus (EMJMD) — Demo",
            country="EU",
            url="https://example.com/erasmus-demo",
            deadline=today + timedelta(days=10),
            fully_funded=True,
            requires_ielts=True,
            minimum_gpa=3.5,
            estimated_fees_usd=0,
            raw={"source": "cached_demo"},
        ),
        Opportunity(
            title="Korea GKS Graduate Scholarship — Demo",
            country="South Korea",
            url="https://example.com/gks-demo",
            deadline=today + timedelta(days=180),
            fully_funded=True,
            requires_ielts=False,
            minimum_gpa=2.8,
            estimated_fees_usd=0,
            raw={"source": "cached_demo"},
        ),
        Opportunity(
            title="DAAD Germany Fully Funded — Demo",
            country="Germany",
            url="https://example.com/daad-demo",
            deadline=today + timedelta(days=95),
            fully_funded=True,
            requires_ielts=False,
            minimum_gpa=3.0,
            estimated_fees_usd=0,
            raw={"source": "cached_demo"},
        ),
    ]

    profile = state.profile
    if profile is None:
        return state.model_copy(update={"opportunities": cached})

    try:
        query, live = asyncio.run(search_opportunities(profile, max_results=8))
    except RuntimeError:
        query, live = "", []
    except Exception:
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
