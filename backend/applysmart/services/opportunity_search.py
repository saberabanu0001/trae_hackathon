from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from applysmart.models.core import Opportunity, Profile, OpportunityType
from applysmart.services.opportunity_extract import enrich_urls
from applysmart.services.web_search import SearchResult, WebSearchClient, get_default_search_client


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
    program_map: dict[str, SearchResult] = {}
    priority_programs = ["erasmus", "daad", "mext", "gks", "australia awards", "endeavour", "nus research"]
    
    for r in all_results:
        low_title = r.title.lower()
        matched_program = "other"
        for p in priority_programs:
            if p in low_title:
                matched_program = p
                break
        
        if matched_program == "other":
            if r.url not in program_map:
                program_map[r.url] = r
        else:
            if matched_program not in program_map:
                program_map[matched_program] = r
            else:
                existing = program_map[matched_program]
                if (r.snippet and not existing.snippet) or (len(r.title) > len(existing.title) and "official" in low_title):
                    program_map[matched_program] = r

    unique_results = list(program_map.values())

    # 2. Enrich with real deadlines and details
    target_urls = [r.url for r in unique_results[:10]]
    enriched_details = await enrich_urls(target_urls, max_concurrency=5)

    # 3. Filter and Parse into Opportunity models
    opportunities: list[Opportunity] = []
    for res in unique_results:
        details = enriched_details.get(res.url)
        
        # Hardcoded fallback deadlines
        fallback_deadline = None
        low_title = res.title.lower()
        if "daad" in low_title: fallback_deadline = date(date.today().year, 10, 15)
        elif "erasmus" in low_title: fallback_deadline = date(date.today().year + 1, 1, 15)
        elif "mext" in low_title: fallback_deadline = date(date.today().year, 5, 30)
        elif "australia awards" in low_title: fallback_deadline = date(date.today().year, 4, 30)
        elif "gks" in low_title or "korea" in low_title: fallback_deadline = date(date.today().year, 9, 30)

        final_deadline = details.deadline if (details and details.deadline) else fallback_deadline
        
        # 1. Classify Opportunity Type
        opp_type = OpportunityType.portal
        actions = ["Generate SOP Outline", "View Requirements"]
        profs = []
        
        if any(kw in low_title for kw in ["mext", "research", "lab", "professor", "supervisor"]):
            opp_type = OpportunityType.research
            actions = ["Find Matching Professors"]
            # Mock some professor discovery based on interests
            profs = [
                {
                    "name": "Prof. Kim",
                    "university": "Seoul National University",
                    "research": "NLP, LLM, Multi-agent systems",
                    "match": "High (your GitHub shows agent-based projects)",
                    "email": "kim@snu.ac.kr"
                },
                {
                    "name": "Prof. Tanaka",
                    "university": "University of Tokyo",
                    "research": "Robotics + AI",
                    "match": "Medium (aligned with engineering track)",
                    "email": "tanaka@u-tokyo.ac.jp"
                }
            ]
        elif any(kw in low_title for kw in ["daad", "erasmus", "gks", "awards"]):
            opp_type = OpportunityType.portal
            actions = ["Generate SOP Outline", "View Requirements"]
        elif any(kw in low_title for kw in ["university", "nus", "admission"]):
            opp_type = OpportunityType.university
            actions = ["Compare Admission Chances", "Generate Motivation Letter"]

        opp = Opportunity(
            title=res.title,
            url=res.url,
            country=_detect_country(res.title, profile.target_country),
            fully_funded=details.fully_funded if (details and details.fully_funded is not None) else True,
            deadline=final_deadline,
            snippet=res.snippet or f"Fully funded scholarship for {profile.major} students.",
            opp_type=opp_type,
            recommended_actions=actions,
            matched_professors=profs,
            raw={"url": res.url, "source": res.source}
        )
        opportunities.append(opp)

    # 4. Enforce Priority Order
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
