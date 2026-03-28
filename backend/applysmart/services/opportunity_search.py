from __future__ import annotations

import asyncio

from applysmart.models.core import Opportunity, Profile
from applysmart.services.opportunity_extract import enrich_urls
from applysmart.services.web_search import SearchResult, WebSearchClient, get_default_search_client


def build_query(profile: Profile) -> str:
    # Use DNA and interests for a more targeted search
    track = "research" if profile.research_interests else "engineering"
    
    parts = [
        "fully funded scholarship",
        profile.degree_level,
        profile.major,
        profile.nationality,
        profile.target_country,
    ]
    
    # Add track-specific keywords
    if track == "research":
        parts.append("research fellowship")
    else:
        parts.append("masters scholarship")

    # Add top research interests if any
    if profile.research_interests:
        parts.extend(profile.research_interests[:2])

    if not profile.has_ielts:
        parts.append("no IELTS required")
    
    query = " ".join(p for p in parts if p)
    print(f"[OpportunityAgent] Search Query: {query}")
    return query


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
    profile: Profile, *, max_results: int = 15
) -> tuple[str, list[Opportunity]]:
    """
    Performs a multi-country, global scholarship search based on the profile's DNA.
    Targets major fully-funded programs (DAAD, Erasmus, MEXT, GKS, Australia Awards).
    """
    client = get_default_search_client()
    if client is None:
        return "NO_SEARCH_CLIENT", []

    queries = [
        # Global Fully-Funded
        f"fully funded Erasmus Mundus masters {profile.major} scholarships EMAI",
        f"DAAD fully funded scholarship master {profile.major} for {profile.nationality} students",
        # Target/Regional
        f"Australia Awards Scholarship {profile.major} for {profile.nationality}",
        f"MEXT Japan fully funded scholarship {profile.major} {profile.nationality}",
        f"GKS Korea fully funded scholarship {profile.major} {profile.nationality}",
        # Field Specific
        f"AI and Machine Learning masters scholarship fully funded international students",
        f"Endeavour Leadership Australia scholarship {profile.major}",
        f"NUS Research Scholarship Singapore {profile.major} fully funded",
    ]

    all_results: list[SearchResult] = []
    
    # Run searches in parallel for efficiency
    search_tasks = [client.search(q, max_results=5) for q in queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    
    for res in search_results:
        if isinstance(res, list):
            all_results.extend(res)

    # 1. Deduplicate and Group by Program
    # We use a program-key to ensure we only keep the best result for major programs
    program_map: dict[str, SearchResult] = {}
    
    # Priority keywords for grouping
    priority_programs = ["erasmus", "daad", "mext", "gks", "australia awards", "endeavour", "nus research"]
    
    for r in all_results:
        low_title = r.title.lower()
        matched_program = "other"
        for p in priority_programs:
            if p in low_title:
                matched_program = p
                break
        
        # If we haven't seen this program yet, or this result has a snippet and the previous didn't
        if matched_program == "other":
            # Just use URL for other results
            if r.url not in program_map:
                program_map[r.url] = r
        else:
            # For priority programs, only keep the most relevant one (best snippet or title match)
            if matched_program not in program_map:
                program_map[matched_program] = r
            else:
                # Heuristic: keep the one with the longer snippet or more specific title
                existing = program_map[matched_program]
                if (r.snippet and not existing.snippet) or (len(r.title) > len(existing.title) and "official" in low_title):
                    program_map[matched_program] = r

    unique_results = list(program_map.values())

    # 2. Enrich with real deadlines and details (Fix 2)
    # Only enrich top 10 for performance
    target_urls = [r.url for r in unique_results[:10]]
    enriched_details = await enrich_urls(target_urls, max_concurrency=5)

    # 3. Filter and Parse into Opportunity models
    opportunities: list[Opportunity] = []
    for res in unique_results:
        details = enriched_details.get(res.url)
        
        # Hardcoded fallback deadlines (Fix 2)
        fallback_deadline = None
        low_title = res.title.lower()
        if "daad" in low_title: fallback_deadline = date(date.today().year, 10, 15)
        elif "erasmus" in low_title: fallback_deadline = date(date.today().year + 1, 1, 15)
        elif "mext" in low_title: fallback_deadline = date(date.today().year, 5, 30)
        elif "australia awards" in low_title: fallback_deadline = date(date.today().year, 4, 30)
        elif "gks" in low_title or "korea" in low_title: fallback_deadline = date(date.today().year, 9, 30)

        # Use extracted deadline if available, else fallback
        final_deadline = details.deadline if (details and details.deadline) else fallback_deadline
        
        opp = Opportunity(
            title=res.title,
            url=res.url,
            country=_detect_country(res.title, profile.target_country),
            fully_funded=details.fully_funded if (details and details.fully_funded is not None) else True,
            requires_ielts=details.requires_ielts if (details and details.requires_ielts is not None) else None,
            minimum_gpa=details.minimum_gpa if (details and details.minimum_gpa is not None) else None,
            deadline=final_deadline,
            snippet=res.snippet,
            raw={"url": res.url, "source": res.source, "is_rolling": final_deadline is None}
        )
        opportunities.append(opp)

    # 4. Enforce Priority Order (Fix 4)
    def _priority_score(opp: Opportunity) -> int:
        t = opp.title.lower()
        if "australia awards" in t: return 100
        if "erasmus" in t and "emai" in t: return 90
        if "daad" in t and "development" in t: return 80
        if "gks" in t or "korea" in t: return 70
        if "mext" in t: return 60
        if "endeavour" in t: return 50
        if "daad" in t: return 40
        if "nus" in t: return 30
        return 0

    opportunities.sort(key=_priority_score, reverse=True)
    return "GLOBAL_MULTI_QUERY_ENRICHED", opportunities[:10]

def _detect_country(title: str, default: str) -> str:
    low = title.lower()
    if "germany" in low or "daad" in low: return "Germany"
    if "japan" in low or "mext" in low: return "Japan"
    if "korea" in low or "gks" in low: return "South Korea"
    if "australia" in low: return "Australia"
    if "singapore" in low or "nus" in low: return "Singapore"
    if "europe" in low or "erasmus" in low: return "EU/Global"
    return default

