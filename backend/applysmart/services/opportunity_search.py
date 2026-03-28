from __future__ import annotations

from applysmart.models.core import Opportunity, Profile
from applysmart.services.opportunity_extract import enrich_urls
from applysmart.services.web_search import SearchResult, WebSearchClient, get_default_search_client


def build_query(profile: Profile) -> str:
    # Keep this simple and stable for demos.
    parts = [
        "fully funded scholarship",
        profile.degree_level,
        profile.major,
        profile.nationality,
        profile.target_country,
    ]
    if not profile.has_ielts:
        parts.append("no IELTS")
    return " ".join(p for p in parts if p)


def _result_to_opportunity(r: SearchResult) -> Opportunity:
    # For hackathon: turn a search result into a minimally useful opportunity card.
    return Opportunity(
        title=r.title,
        url=r.url,
        country=None,
        deadline=None,
        fully_funded=None,
        requires_ielts=None,
        minimum_gpa=None,
        estimated_fees_usd=None,
        raw={
            "source": f"live:{r.source}",
            "snippet": r.snippet,
            "search_raw": r.raw,
        },
    )


async def search_opportunities(
    profile: Profile, *, max_results: int = 8, enrich_top_n: int = 3
) -> tuple[str, list[Opportunity]]:
    query = build_query(profile)
    client: WebSearchClient | None = get_default_search_client()
    if client is None:
        return query, []

    results = await client.search(query, max_results=max_results)
    opps = [_result_to_opportunity(r) for r in results]

    # Enrich top-N URLs with extracted structured fields (deadline/IELTS/funding hints).
    urls = [o.url for o in opps[: max(0, enrich_top_n)] if o.url]
    if urls:
        extracted = await enrich_urls(urls, max_concurrency=4)
        enriched: list[Opportunity] = []
        for o in opps:
            if not o.url or o.url not in extracted:
                enriched.append(o)
                continue
            d = extracted[o.url]
            enriched.append(
                o.model_copy(
                    update={
                        "deadline": d.deadline,
                        "requires_ielts": d.requires_ielts,
                        "fully_funded": d.fully_funded,
                        "minimum_gpa": d.minimum_gpa,
                        "raw": {**o.raw, "extracted": d.__dict__},
                    }
                )
            )
        opps = enriched

    return query, opps

