from applysmart.models.core import ConflictItem, DNAAxis, DNAVector, GitHubAnalysis, Profile, RejectionRisk
import json
import asyncio


from datetime import datetime, timezone


def _calculate_readme_score(readme: str | None) -> float:
    if not readme:
        return 0.0
    score = 0.0
    if len(readme) > 500:
        score += 30
    if "## " in readme:
        score += 25
    if "```" in readme:
        score += 20
    if "![" in readme or "http" in readme: # Simple proxy for badges/screenshots
        score += 25
    return min(100, score)


async def synthesize_profile(profile: Profile, gh_payload: dict | None = None) -> Profile:
    """
    LLM-based synthesis of the profile. Cross-references GitHub, Resume, and target country.
    """
    system_instruction = """You are the ApplySmart Profile Agent. Your job is to analyze a student's profile (Resume + GitHub + Goals) and provide deep, actionable insights for SCHOLARSHIP MATCHING.

CRITICAL CONTEXT:
ApplySmart is a SCHOLARSHIP-ONLY matching system. We do not support self-funded study. 
The student's declared budget is only for incidental costs; we are matching them to 100% FULLY-FUNDED opportunities.

INSTRUCTIONS:
1. STRENGTHS: Synthesize into meaningful achievements that win SCHOLARSHIPS.
2. CONFLICTS: Detect unverified claims (e.g. CV skills vs GitHub evidence).
3. DNA VECTOR: Compute 6-axis scores based on REAL data.
4. SCHOLARSHIP ANALYSIS:
   - For Australia: Needs 6.5+ IELTS. If missing, flag as "Critical Scholarship Blocker".
   - Budget: If budget is low (e.g. $500), emphasize that this student MUST win a fully-funded award (DAAD, Erasmus, GKS, Australia Awards).
   - Analysis should focus on "Scholarship Competitiveness" rather than "Self-funding Capability".
5. VERDICT: Summary of scholarship candidacy.
6. ACTION PLAN: Focus on winning scholarships (improving profile, securing references, acing IELTS).
7. REJECTION RISKS: Urgency MUST be one of: 'critical', 'high', 'medium', 'low' (all lowercase).

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
  "consistency_summary": "string or null",
  "verified_skills": ["string"]
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
            return _apply_deterministic_fallbacks(profile)

        try:
            data = json.loads(res_text)
        except json.JSONDecodeError as e:
            print(f"[ProfileAgent] JSON Decode Error: {e}\nRaw response: {res_text}")
            return _apply_deterministic_fallbacks(profile)
            
        # Parse DNA vector
        dna_data = data.get("dna")
        dna_vector = None
        if dna_data:
            try:
                dna_vector = DNAVector.model_validate(dna_data)
            except Exception:
                pass

        # Normalize rejection risk urgency to lowercase (Fix for bug)
        raw_risks = data.get("rejection_risks", [])
        for r in raw_risks:
            if "urgency" in r:
                r["urgency"] = r["urgency"].lower()

        p = profile.model_copy(update={
            "strengths": data.get("strengths", profile.strengths),
            "conflicts": [ConflictItem.model_validate(c) for c in data.get("conflicts", [])],
            "dna": dna_vector,
            "rejection_risks": [RejectionRisk.model_validate(r) for r in raw_risks],
            "ielts_gap_analysis": data.get("ielts_gap_analysis"),
            "budget_analysis": data.get("budget_analysis"),
            "verdict": data.get("verdict"),
            "action_plan": data.get("action_plan", []),
            "opportunity_type_verdict": data.get("opportunity_type_verdict"),
            "consistency_summary": data.get("consistency_summary", profile.consistency_summary),
            "verified_skills": data.get("verified_skills", []),
        })
        return _apply_deterministic_fallbacks(p)
    except Exception as e:
        print(f"[ProfileAgent] synthesis error: {e}")
        return _apply_deterministic_fallbacks(profile)


def _apply_deterministic_fallbacks(p: Profile) -> Profile:
    """
    Ensure critical fields like IELTS, budget, and conflicts have fallback logic if LLM fails.
    """
    updates: dict[str, Any] = {}
    
    # Deterministic IELTS analysis (Task 5)
    if not p.has_ielts and p.target_country == "Australia":
        if not p.ielts_gap_analysis:
            updates["ielts_gap_analysis"] = "Australia requires IELTS 6.5+ for most programs. Current match pool is effectively 0."
        if not any(r.risk_name == "IELTS Gap" for r in p.rejection_risks):
            p.rejection_risks.append(RejectionRisk(
                risk_name="IELTS Gap",
                impact="Australian target unreachable",
                urgency="critical",
                fix_action="Register for IELTS immediately"
            ))

    # Deterministic Budget analysis (Task 5)
    if p.budget_usd < 2000:
        if not p.budget_analysis:
            p.budget_analysis = (
                f"Your declared budget (${p.budget_usd}/mo) is low for self-funding. "
                "ApplySmart has flagged you as a 100% SCHOLARSHIP CANDIDATE. "
                "We are prioritizing fully-funded programs (DAAD, Erasmus, GKS, Australia Awards) "
                "where your technical strength can win you a full ride."
            )
        
        # Clean up any "increase budget" advice in action plan, verdict, or budget analysis
        bad_phrases = ["increase budget", "raise funds", "self-fund", "personal savings", "financial proof"]
        
        if p.action_plan:
            new_plan = []
            for step in p.action_plan:
                if any(phrase in step.lower() for phrase in bad_phrases):
                    new_plan.append("Shortlist 3-5 fully-funded scholarships that match your DNA (technical depth/research).")
                else:
                    new_plan.append(step)
            updates["action_plan"] = new_plan

        if p.verdict and any(phrase in p.verdict.lower() for phrase in bad_phrases):
            p.verdict = p.verdict.replace("increase your budget", "focus on full-ride scholarships")
            p.verdict = p.verdict.replace("raise more funds", "secure a 100% funded award")
            updates["verdict"] = p.verdict

    # Ensure opportunity type verdict is always scholarship-focused
    if not p.opportunity_type_verdict or "self-fund" in p.opportunity_type_verdict.lower():
        updates["opportunity_type_verdict"] = "100% Fully-Funded Scholarship Track (High Competitiveness)"

    # Deterministic Conflict Detection (Task 3)
    cv_text = (p.resume_text or "").lower()
    gh_langs = {l.lower() for l in p.github_analysis.languages.keys()}
    
    # Auto-verify skills based on GitHub activity
    verified = set(p.verified_skills)
    for lang in p.github_analysis.languages.keys():
        if lang.lower() in cv_text:
            verified.add(lang)
    updates["verified_skills"] = list(verified)

    if "pytorch" in cv_text or "tensorflow" in cv_text:
        if "python" not in gh_langs:
            if not any(c.type == "Skill Mismatch" for c in p.conflicts):
                p.conflicts.append(ConflictItem(
                    type="Skill Mismatch",
                    severity="high",
                    claim="Deep Learning (PyTorch/TensorFlow)",
                    evidence="No Python repositories found on GitHub",
                    message="You claim deep learning skills, but your GitHub shows no Python activity to support this.",
                    recommendation="Add a small PyTorch project to your GitHub."
                ))

    # DNA Fallback (Task 4)
    if not p.dna:
        updates["dna"] = DNAVector(
            technical_depth=DNAAxis(score=40 + min(40, len(p.languages) * 5), explanation="Based on language variety."),
            execution_consistency=DNAAxis(score=p.github_analysis.consistency_score, explanation="Based on commit history."),
            research_track_fit=DNAAxis(score=30 + min(40, len(p.research_interests) * 5), explanation="Based on interests."),
            language_readiness=DNAAxis(score=80 if p.has_ielts else 30, explanation="Based on IELTS status."),
            engineering_track_fit=DNAAxis(score=50 + min(30, p.github_analysis.repos_count * 2), explanation="Based on repo count."),
            publication_strength=DNAAxis(score=0, explanation="No publications detected.")
        )

    if updates:
        p = p.model_copy(update=updates)
    return p


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
    readme_scores: list[float] = []
    last_pushed: datetime | None = None

    if gh_payload and not gh_payload.get("error"):
        p = gh_payload.get("profile") or {}
        gh_name = p.get("name")
        if gh_name and (not profile.full_name.strip() or profile.full_name == "Demo Student"):
            profile = profile.model_copy(update={"full_name": str(gh_name)})

        gh_analysis.repos_count = len(gh_payload.get("repos") or [])
        gh_analysis.total_stars = sum(int(r.get("stargazers_count") or 0) for r in (gh_payload.get("repos") or []) if isinstance(r, dict))
        
        now = datetime.now(timezone.utc)
        recent_pushes = 0

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
            
            # Activity scoring (Fix for "inactive" bug)
            updated_at_str = repo.get("updated_at")
            if updated_at_str:
                dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if last_pushed is None or dt > last_pushed:
                    last_pushed = dt
                if (now - dt).days < 180: # 6 months
                    recent_pushes += 1

            # README scoring (Fix for 0.0 bug)
            if repo.get("readme_content"):
                readme_scores.append(_calculate_readme_score(repo["readme_content"]))
            
            gh_analysis.top_repos.append(repo)

        # Finalize GitHub Heuristics
        if readme_scores:
            gh_analysis.readme_quality_avg = sum(readme_scores) / len(readme_scores)
        
        if gh_analysis.repos_count > 0:
            gh_analysis.consistency_score = min(100, (recent_pushes / gh_analysis.repos_count) * 100)
        
        if recent_pushes > 3:
            gh_analysis.activity_pattern = "consistent"
        elif recent_pushes > 0:
            gh_analysis.activity_pattern = "burst"
        else:
            gh_analysis.activity_pattern = "inactive"

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
