from applysmart.models.core import ConflictItem, DNAAxis, DNAVector, GitHubAnalysis, Profile, RejectionRisk
import json
import asyncio


async def synthesize_profile(profile: Profile, gh_payload: dict | None = None) -> Profile:
    """
    LLM-based synthesis of the profile. Cross-references GitHub, Resume, and target country.
    """
    system_instruction = """You are the ApplySmart Profile Agent. Your job is to analyze a student's profile (Resume + GitHub + Goals) and provide deep, actionable insights.

CRITICAL INSTRUCTIONS:
1. STRENGTHS: Don't just copy raw resume lines. Synthesize them into meaningful achievements as FULL SENTENCES.
   - Good: "2+ years Teaching Assistant experience signals strong communication ability."
   - Bad: "Teaching Assistant Jan 2024 - Present"
2. CONFLICTS: Cross-reference skills. If they claim PyTorch on their CV but their GitHub has 0 PyTorch repos, generate a ConflictItem.
   - Severity: critical/high/medium/low.
3. DNA VECTOR: Compute 6-axis scores (0-100) based on real evidence. Provide a one-line explanation for each.
   - technical_depth, execution_consistency, research_track_fit, language_readiness, engineering_track_fit, publication_strength.
4. BUDGET & IELTS: Analyze against target country (e.g., Australia costs ~$1500-2000/mo, needs 6.5+ IELTS).
5. REJECTION RISKS: Identify specific risks based on the profile (e.g., "IELTS Gap", "Low Project Documentation").
6. VERDICT: Provide a 20-second summary that a stranger could read to understand their situation.
7. ACTION PLAN: Provide a specific 30-day plan (Week 1, Week 2, Week 3, Week 4).
8. TRACK: Decide if they are Engineering-track or Research-track.

Output MUST be a JSON object matching this structure:
{
  "strengths": ["string"],
  "conflicts": [{"type": "string", "severity": "string", "claim": "string", "evidence": "string", "message": "string", "recommendation": "string"}],
  "dna": {
    "technical_depth": {"score": 0, "explanation": "string"},
    "execution_consistency": {"score": 0, "explanation": "string"},
    "research_track_fit": {"score": 0, "explanation": "string"},
    "language_readiness": {"score": 0, "explanation": "string"},
    "engineering_track_fit": {"score": 0, "explanation": "string"},
    "publication_strength": {"score": 0, "explanation": "string"}
  },
  "rejection_risks": [{"risk_name": "string", "impact": "string", "urgency": "string", "fix_action": "string"}],
  "ielts_gap_analysis": "string",
  "budget_analysis": "string",
  "verdict": "string",
  "action_plan": ["string"],
  "opportunity_type_verdict": "string",
  "consistency_summary": "string or null"
}"""

    # Prepare context
    context = {
        "full_name": profile.full_name,
        "nationality": profile.nationality,
        "target_country": profile.target_country,
        "degree_level": profile.degree_level,
        "major": profile.major,
        "gpa": f"{profile.gpa}/{profile.gpa_scale_max}",
        "has_ielts": profile.has_ielts,
        "ielts_score": profile.ielts_score,
        "budget_usd": profile.budget_usd,
        "interests": profile.interests,
        "github_analysis": profile.github_analysis.model_dump() if profile.github_analysis else "Not provided",
        "github_raw": gh_payload if gh_payload else "Not provided",
        "resume_text": (profile.resume_text or "")[:10000],
    }

    prompt = f"Analyze this profile and provide structured synthesis:\n\n{json.dumps(context, indent=2)}"
    
    from applysmart.services.llm import chat_completion
    try:
        res_text = await chat_completion(prompt, system_instruction=system_instruction, response_format="json_object")
        if res_text.startswith("LLM_NOT_CONFIGURED"):
            print("[ProfileAgent] LLM NOT CONFIGURED - skipping synthesis")
            return profile

        try:
            data = json.loads(res_text)
        except json.JSONDecodeError as e:
            print(f"[ProfileAgent] JSON Decode Error: {e}\nRaw response: {res_text}")
            return profile
            
        # Parse DNA vector
        dna_data = data.get("dna")
        dna_vector = None
        if dna_data:
            try:
                dna_vector = DNAVector.model_validate(dna_data)
            except Exception:
                pass

        return profile.model_copy(update={
            "strengths": data.get("strengths", profile.strengths),
            "conflicts": [ConflictItem.model_validate(c) for c in data.get("conflicts", [])],
            "dna": dna_vector,
            "rejection_risks": [RejectionRisk.model_validate(r) for r in data.get("rejection_risks", [])],
            "ielts_gap_analysis": data.get("ielts_gap_analysis"),
            "budget_analysis": data.get("budget_analysis"),
            "verdict": data.get("verdict"),
            "action_plan": data.get("action_plan", []),
            "opportunity_type_verdict": data.get("opportunity_type_verdict"),
            "consistency_summary": data.get("consistency_summary", profile.consistency_summary),
        })
    except Exception as e:
        print(f"[ProfileAgent] synthesis error: {e}")
        return profile


async def ingest_profile_sources(profile: Profile) -> tuple[Profile, dict[str, Any]]:
    """
    Pull public GitHub + optional portfolio pages + best-effort LinkedIn URL fetch.
    Merges heuristics into Profile fields used for opportunity matching & auto-CV.
    Then performs LLM synthesis for deeper insights.
    """
    ingest: dict[str, Any] = {"sources": [], "warnings": []}

    from applysmart.services.github_public import fetch_public_github, parse_github_username
    gh_user = parse_github_username(profile.github_url or "")
    gh_payload: dict[str, Any] | None = None
    tasks = []

    if gh_user:
        ingest["sources"].append("github_api")

        async def _gh() -> None:
            nonlocal gh_payload
            gh_payload = await fetch_public_github(gh_user)

        tasks.append(asyncio.create_task(_gh()))

    portfolio_texts: dict[str, str] = {}
    from applysmart.services.fetch_text import fetch_page_text

    async def _fetch_portfolio(u: str) -> None:
        text, meta = await fetch_page_text(u)
        portfolio_texts[u] = text or ""
        if text is None:
            ingest["warnings"].append(f"portfolio_fetch:{meta.get('status') or meta.get('error')}")

    for url in profile.portfolio_urls[:5]:
        if not url or not url.startswith("http"):
            continue
        ingest["sources"].append(f"portfolio:{url[:48]}")
        tasks.append(asyncio.create_task(_fetch_portfolio(url)))

    linkedin_text: str | None = None
    if profile.linkedin_url and profile.linkedin_url.startswith("http"):
        ingest["sources"].append("linkedin_url_attempt")

        async def _li() -> None:
            nonlocal linkedin_text
            text, meta = await fetch_page_text(profile.linkedin_url or "")
            linkedin_text = text
            if text is None or (text and len(text) < 200):
                ingest["warnings"].append(
                    "linkedin_limited: public fetch often blocked; paste highlights or resume."
                )

        tasks.append(asyncio.create_task(_li()))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- Merge GitHub (Heuristics) ---
    gh_analysis = GitHubAnalysis()
    languages_count: dict[str, int] = {}
    projects: list[str] = []
    topics: list[str] = []

    if gh_payload and not gh_payload.get("error"):
        p = gh_payload.get("profile") or {}
        gh_name = p.get("name")
        if gh_name and (not profile.full_name.strip() or profile.full_name == "Demo Student"):
            profile = profile.model_copy(update={"full_name": str(gh_name)})

        gh_analysis.repos_count = len(gh_payload.get("repos") or [])
        gh_analysis.total_stars = sum(int(r.get("stargazers_count") or 0) for r in (gh_payload.get("repos") or []) if isinstance(r, dict))
        
        for repo in gh_payload.get("repos") or []:
            if not isinstance(repo, dict):
                continue
            lang = repo.get("language")
            if isinstance(lang, str) and lang:
                languages_count[lang] = languages_count.get(lang, 0) + 1
            
            desc = (repo.get("description") or "").strip()
            name = repo.get("name") or ""
            if not desc:
                gh_analysis.repos_without_description.append(name)
            
            line = f"{name}: {desc}" if desc else str(name)
            if line:
                projects.append(line)
            for tp in repo.get("topics") or []:
                if isinstance(tp, str) and tp:
                    topics.append(tp)
                    gh_analysis.research_signals.append(tp.lower())
            
            gh_analysis.top_repos.append(repo)

        langs_sorted = [k for k, _ in sorted(languages_count.items(), key=lambda kv: (-kv[1], kv[0]))]
        total_lang_repos = sum(languages_count.values()) or 1
        gh_analysis.languages = {k: (v / total_lang_repos) * 100 for k, v in languages_count.items()}

        ri = list({t.replace("-", " ") for t in topics})[:12]
        bio = (p.get("bio") or "").strip()
        if bio:
            ri.insert(0, bio[:240])

        def _uniq_keep_order(lst):
            seen = set()
            return [x for x in lst if not (x in seen or seen.add(x))]

        profile = profile.model_copy(
            update={
                "languages": _uniq_keep_order(profile.languages + langs_sorted),
                "projects": _uniq_keep_order(profile.projects + projects)[:30],
                "research_interests": _uniq_keep_order(profile.research_interests + ri),
                "github_analysis": gh_analysis,
                "ingest_meta": {**profile.ingest_meta, "github": {"user": gh_user, "public_repos": p.get("public_repos")}},
            }
        )
    elif gh_user and gh_payload and gh_payload.get("error"):
        ingest["warnings"].append(f"github:{gh_payload.get('error')}")

    # --- Resume + page text (Heuristics) ---
    blob_parts: list[str] = []
    if profile.resume_text:
        blob_parts.append(profile.resume_text)
    blob_parts.extend(portfolio_texts.values())
    if linkedin_text:
        blob_parts.append(linkedin_text)

    big = "\n".join(blob_parts)
    if big.strip():
        from applysmart.services.profile_extract_heuristic import extract_languages_from_text
        langs = extract_languages_from_text(big)
        def _uniq_keep_order(lst):
            seen = set()
            return [x for x in lst if not (x in seen or seen.add(x))]
        profile = profile.model_copy(
            update={
                "languages": _uniq_keep_order(profile.languages + langs),
            }
        )
    
    # --- LLM Synthesis Step ---
    profile = await synthesize_profile(profile, gh_payload)

    ingest["warnings"] = list(dict.fromkeys(ingest["warnings"]))
    profile = profile.model_copy(update={"ingest_meta": {**profile.ingest_meta, "last_ingest": ingest}})
    return profile, ingest
