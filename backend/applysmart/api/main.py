from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from applysmart.models.core import Profile, ProfileGaps, ApplySmartState
from applysmart.services.cv_builder import render_cv_markdown
from applysmart.services.fetch_text import fetch_page_text
from applysmart.services.github_public import fetch_public_github, parse_github_username
from applysmart.services.profile_ingest import ingest_profile_sources
from applysmart.services.resume_text import extract_text_from_upload

app = FastAPI(title="ApplySmart API", version="0.1.0")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_BACKEND_ROOT / ".env", override=False)


def _form_bool(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _parse_optional_float(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sanitize_profile_inputs(
    *,
    gpa: float,
    gpa_scale_max: float,
    budget_usd: int,
    ielts_f: float | None,
) -> tuple[float, float, int, float | None]:
    """Clamp form values so Pydantic never rejects normal UX (e.g. negative budget by mistake)."""
    gpa = max(0.0, min(10.0, float(gpa)))
    gpa_scale_max = max(1.0, min(10.0, float(gpa_scale_max)))
    budget_usd = max(0, int(budget_usd))
    if ielts_f is not None:
        if ielts_f < 0 or ielts_f > 9:
            ielts_f = None
    return gpa, gpa_scale_max, budget_usd, ielts_f


def _analysis_log(profile: Profile, ingest: dict) -> list[str]:
    lines: list[str] = ["→ Profile Agent initialized"]
    gh = (profile.ingest_meta or {}).get("github") or {}
    if profile.github_url and gh.get("user"):
        lines.append(f"→ Reading GitHub: {gh.get('user')}…")
        pr = gh.get("public_repos")
        if pr is not None:
            lines.append(f"→ Public repo count (API): {pr}")
    langs = profile.languages or []
    if langs:
        top = ", ".join(langs[:6])
        lines.append(f"→ Languages / tools (merged): {top}")
    if profile.projects:
        lines.append(f"→ Projects sampled: {len(profile.projects)}")
    if profile.resume_text:
        lines.append(f"→ Resume text extracted ({len(profile.resume_text)} chars)")
    for w in ingest.get("warnings") or []:
        lines.append(f"→ Note: {w}")
    if not profile.has_ielts:
        lines.append("→ IELTS: not declared — many opps require proof of English")
    
    if profile.verdict:
        lines.append("✓ Profile synthesis complete (LLM)")
        if profile.conflicts:
            lines.append(f"→ Found {len(profile.conflicts)} evidence conflicts")
        if profile.rejection_risks:
            lines.append(f"→ Identified {len(profile.rejection_risks)} rejection risks")
    else:
        lines.append("→ Profile analysis complete (Heuristics only)")
    
    lines.append("→ Generating 6-axis Opportunity DNA vector…")
    lines.append("✓ Profile analysis complete. Open your profile card.")
    return lines

_STATIC = Path(__file__).resolve().parent / "static"
if _STATIC.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_STATIC)), name="assets")


@app.get("/", response_class=HTMLResponse)
async def profile_page() -> str:
    html_path = _STATIC / "profile.html"
    if html_path.is_file():
        return html_path.read_text(encoding="utf-8")
    return "<p>Missing static/profile.html</p>"


def _parse_portfolios(s: str) -> list[str]:
    return [line.strip() for line in (s or "").splitlines() if line.strip()]


@app.post("/api/profile/github-preview")
async def api_github_preview(github_url: str = Form("")):
    username = parse_github_username(github_url.strip())
    if not username:
        return {"ok": False, "error": "Could not parse GitHub username from URL"}
    data = await fetch_public_github(username)
    if data.get("error"):
        return {"ok": False, "error": data["error"]}
    prof = data.get("profile") or {}
    langs: dict[str, int] = {}
    for repo in data.get("repos") or []:
        if not isinstance(repo, dict):
            continue
        lang = repo.get("language")
        if isinstance(lang, str) and lang:
            langs[lang] = langs.get(lang, 0) + 1
    total = sum(langs.values()) or 1
    lang_pct = {k: round(100 * v / total) for k, v in sorted(langs.items(), key=lambda x: -x[1])}
    stars = sum(int(r.get("stargazers_count") or 0) for r in (data.get("repos") or []) if isinstance(r, dict))
    topics: list[str] = []
    for r in data.get("repos") or []:
        if isinstance(r, dict):
            topics.extend(r.get("topics") or [])
    top_topics = list(dict.fromkeys(topics))[:10]
    return {
        "ok": True,
        "login": prof.get("login"),
        "name": prof.get("name"),
        "bio": prof.get("bio"),
        "repo_count": len(data.get("repos") or []),
        "public_repos": prof.get("public_repos"),
        "stars": stars,
        "languages": lang_pct,
        "top_topics": top_topics,
    }


@app.post("/api/profile/fetch-url")
async def api_fetch_url(url: str = Form("")):
    text, meta = await fetch_page_text(url.strip())
    if text and len(text) > 400:
        return {"ok": True, "chars": len(text)}
    return {
        "ok": False,
        "chars": len(text or ""),
        "hint": "linkedin_or_paywall",
        "detail": meta.get("status") or meta.get("error"),
    }


async def _build_profile_payload(
    *,
    full_name: str,
    nationality: str,
    target_country: str,
    degree_level: str,
    major: str,
    gpa: float,
    gpa_scale_max: float,
    has_ielts: str,
    budget_usd: int,
    interests: str,
    linkedin_url: str,
    github_url: str,
    portfolio_urls: str,
    resume: UploadFile | None,
    academic_status: str = "",
    ielts_score: str = "",
) -> dict:
    resume_text: str | None = None
    resume_meta: dict = {}
    if resume and resume.filename:
        data = await resume.read()
        resume_text, resume_meta = extract_text_from_upload(resume.filename, data)

    interest_list = [x.strip() for x in interests.split(",") if x.strip()]
    ielts_f = _parse_optional_float(ielts_score)
    gpa, gpa_scale_max, budget_usd, ielts_f = _sanitize_profile_inputs(
        gpa=gpa,
        gpa_scale_max=gpa_scale_max,
        budget_usd=budget_usd,
        ielts_f=ielts_f,
    )
    has_ok = _form_bool(has_ielts) or (ielts_f is not None and ielts_f > 0)

    try:
        profile = Profile(
            full_name=full_name or "Applicant",
            nationality=nationality,
            target_country=target_country.strip() or "South Korea",
            degree_level=degree_level,  # type: ignore[arg-type]
            major=major,
            gpa=gpa,
            gpa_scale_max=gpa_scale_max,
            has_ielts=has_ok,
            budget_usd=budget_usd,
            interests=interest_list or ["scholarships", "graduate study"],
            linkedin_url=linkedin_url.strip() or None,
            github_url=github_url.strip() or None,
            portfolio_urls=_parse_portfolios(portfolio_urls),
            resume_text=resume_text,
            ingest_meta={"resume_upload": resume_meta},
            academic_status=academic_status.strip() or None,
            ielts_score=ielts_f,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    profile, ingest = await ingest_profile_sources(profile)

    missing: list[str] = []
    if not profile.full_name.strip():
        missing.append("full_name")
    gaps = ProfileGaps(missing=missing, notes=list(ingest.get("warnings", [])))

    cv_md = render_cv_markdown(profile)

    return {
        "ok": True,
        "profile": profile.model_dump(mode="json"),
        "gaps": gaps.model_dump(),
        "ingest": ingest,
        "cv_markdown": cv_md,
        "analysis_log": _analysis_log(profile, ingest),
    }


@app.post("/api/profile/build")
async def api_profile_build(
    full_name: str = Form(""),
    nationality: str = Form("Bangladesh"),
    target_country: str = Form("South Korea"),
    degree_level: str = Form("master"),
    major: str = Form("Computer Science"),
    gpa: float = Form(3.2),
    gpa_scale_max: float = Form(4.0),
    has_ielts: str = Form("false"),
    budget_usd: int = Form(0),
    interests: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    portfolio_urls: str = Form(""),
    resume: UploadFile | None = File(None),
    academic_status: str = Form(""),
    ielts_score: str = Form(""),
):
    try:
        return await _build_profile_payload(
            full_name=full_name,
            nationality=nationality,
            target_country=target_country,
            degree_level=degree_level,
            major=major,
            gpa=gpa,
            gpa_scale_max=gpa_scale_max,
            has_ielts=has_ielts,
            budget_usd=budget_usd,
            interests=interests,
            linkedin_url=linkedin_url,
            github_url=github_url,
            portfolio_urls=portfolio_urls,
            resume=resume,
            academic_status=academic_status,
            ielts_score=ielts_score,
        )
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "status": "error",
            "message": f"Profile analysis failed: {str(e)}"
        }


@app.post("/api/profile/cv.md")
async def api_profile_cv_download(
    full_name: str = Form(""),
    nationality: str = Form("Bangladesh"),
    target_country: str = Form("South Korea"),
    degree_level: str = Form("master"),
    major: str = Form("Computer Science"),
    gpa: float = Form(3.2),
    gpa_scale_max: float = Form(4.0),
    has_ielts: str = Form("false"),
    budget_usd: int = Form(0),
    interests: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    portfolio_urls: str = Form(""),
    resume: UploadFile | None = File(None),
    academic_status: str = Form(""),
    ielts_score: str = Form(""),
):
    body = await _build_profile_payload(
        full_name=full_name,
        nationality=nationality,
        target_country=target_country,
        degree_level=degree_level,
        major=major,
        gpa=gpa,
        gpa_scale_max=gpa_scale_max,
        has_ielts=has_ielts,
        budget_usd=budget_usd,
        interests=interests,
        linkedin_url=linkedin_url,
        github_url=github_url,
        portfolio_urls=portfolio_urls,
        resume=resume,
        academic_status=academic_status,
        ielts_score=ielts_score,
    )
    safe = "".join(c for c in (full_name or "profile") if c.isalnum() or c in (" ", "-", "_")).strip() or "profile"
    filename = f"{safe.replace(' ', '_')}_auto_cv.md"
    return PlainTextResponse(
        body["cv_markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/scholarships/search")
async def api_scholarships_search(
    full_name: str = Form(""),
    nationality: str = Form("Bangladesh"),
    target_country: str = Form("South Korea"),
    degree_level: str = Form("master"),
    major: str = Form("Computer Science"),
    gpa: float = Form(3.2),
    gpa_scale_max: float = Form(4.0),
    has_ielts: str = Form("false"),
    budget_usd: int = Form(0),
    interests: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    portfolio_urls: str = Form(""),
    resume: UploadFile | None = File(None),
    academic_status: str = Form(""),
    ielts_score: str = Form(""),
):
    try:
        # 1. Build profile (ingests PDF/GitHub)
        payload = await _build_profile_payload(
            full_name=full_name,
            nationality=nationality,
            target_country=target_country,
            degree_level=degree_level,
            major=major,
            gpa=gpa,
            gpa_scale_max=gpa_scale_max,
            has_ielts=has_ielts,
            budget_usd=budget_usd,
            interests=interests,
            linkedin_url=linkedin_url,
            github_url=github_url,
            portfolio_urls=portfolio_urls,
            resume=resume,
            academic_status=academic_status,
            ielts_score=ielts_score,
        )
        
        # 2. Extract Profile object
        profile_data = payload["profile"]
        profile = Profile.model_validate(profile_data)
        
        # 3. Build LangGraph state
        initial_state = ApplySmartState(profile=profile)
        
        # 4. Compile and run graph (lazy import: langgraph + agents are heavy; keep GET / cold-start small)
        from applysmart.graph.langgraph_app import build_app as _build_langgraph_app

        app_graph = _build_langgraph_app()
        final_state_dict = await app_graph.ainvoke(initial_state.model_dump())
        # Normalize so nested models (drafts with SoP/motivation) round-trip cleanly to JSON
        try:
            final_state = ApplySmartState.model_validate(final_state_dict)
            state_out = final_state.model_dump(mode="json", exclude_none=False)
        except Exception:
            state_out = final_state_dict

        return {
            "ok": True,
            "state": state_out,
            "opportunity_types": {
                "portal": "portal-based",
                "research": "research-based",
                "university": "university-funding"
            },
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "error": str(e),
            "message": f"Global scholarship search failed: {str(e)}"
        }
