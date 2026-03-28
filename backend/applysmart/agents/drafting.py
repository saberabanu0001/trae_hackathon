from __future__ import annotations

import json
import re

from applysmart.models.core import ApplySmartState, DraftOutputs, Profile
from applysmart.services.llm import chat_completion


def _strip_json_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _dna_summary(profile: Profile) -> str:
    if not profile.dna:
        return ""
    d = profile.dna
    parts: list[str] = []
    axes = [
        ("Technical depth", d.technical_depth),
        ("Execution consistency", d.execution_consistency),
        ("Research track fit", d.research_track_fit),
        ("Language readiness", d.language_readiness),
        ("Engineering track fit", d.engineering_track_fit),
        ("Publication strength", d.publication_strength),
    ]
    for label, ax in axes:
        if ax.explanation:
            parts.append(f"- **{label}** ({ax.score:.0f}/100): {ax.explanation}")
    return "\n".join(parts)


def _clean_strengths(strengths: list[str]) -> list[str]:
    out: list[str] = []
    for s in strengths:
        t = (s or "").strip()
        if len(t) < 12:
            continue
        if re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b", t):
            if len(t) < 100 and ("–" in t or (len(t) > 5 and "-" in t[:50])):
                continue
        out.append(t)
    return out[:8]


def _rich_template_documents(state: ApplySmartState) -> DraftOutputs:
    profile = state.profile
    assert profile is not None

    target_opp = state.scored[0].opportunity if state.scored else None
    sch_title = target_opp.title if target_opp else "Fully-funded graduate scholarship"
    sch_country = (target_opp.country if target_opp else None) or profile.target_country or "your target region"

    langs = ", ".join((profile.languages or [])[:8]) or "Not listed"
    projects = (profile.projects or [])[:6]
    proj_lines = "\n".join(f"- {p}" for p in projects) if projects else "- (Add notable repositories from GitHub.)"
    strengths = _clean_strengths(profile.strengths or [])
    strength_block = (
        "\n".join(f"- {s}" for s in strengths)
        if strengths
        else "- Strong academic record and structured preparation for graduate study."
    )

    verdict_block = (
        f"\n\n**Profile snapshot:** {profile.verdict.strip()}\n"
        if profile.verdict
        else ""
    )
    opp_verdict = (
        f"\n**Track focus:** {profile.opportunity_type_verdict.strip()}\n"
        if profile.opportunity_type_verdict
        else ""
    )

    dna_text = _dna_summary(profile) or "- DNA vector: see Opportunity DNA tab for full 6-axis breakdown."

    conflict_note = ""
    if profile.conflicts:
        c = profile.conflicts[0]
        if c.message:
            conflict_note = (
                f"\n\n**Evidence check:** Align public GitHub work with skills on your CV "
                f"({c.message[:220]}…)"
            )

    sop = f"""# Statement of Purpose

**{profile.full_name}** · {profile.degree_level.title()} applicant · {profile.major}

## Program and scholarship focus

I am applying to pursue **{profile.degree_level}** studies in **{profile.major}**, with primary targets in **{sch_country}**. This statement supports **{sch_title}** as a top match from ApplySmart opportunity analysis.{verdict_block}{opp_verdict}

## Academic and technical preparation

My technical toolkit includes **{langs}**. Representative projects and repositories include:

{proj_lines}

**Strengths and evidence:**

{strength_block}

## Opportunity DNA (fit narrative)

{dna_text}

## Research interests and goals

My focus areas include: **{", ".join((profile.research_interests or profile.interests or [])[:6]) or "graduate-level work in my field"}**.

## Why this scholarship

I am seeking **fully funded** support aligned with my profile (declared living budget context: **${profile.budget_usd}/month** where relevant). I am prepared to meet eligibility requirements including English proficiency tests as required.{conflict_note}

## Closing

I welcome the opportunity to discuss how my background aligns with **{sch_title}**.

Respectfully,  
**{profile.full_name}**
"""

    motivation = f"""# Motivation Letter — {sch_title}

Dear Scholarship Committee,

I am writing to express my strong motivation for **{sch_title}** ({sch_country}).

My background in **{profile.major}** is supported by concrete project experience and academic preparation (CGPA **{profile.gpa}** / **{profile.gpa_scale_max}**). English: **{"IELTS " + str(profile.ielts_score) if profile.has_ielts and profile.ielts_score else "see profile / tests in progress"}**.

**Why this program:** The opportunity matches my **Opportunity DNA** and my need for **full funding** given my financial parameters.

**What I bring:** {strengths[0] if strengths else "Hands-on project work and a clear graduate goal."}

Sincerely,  
{profile.full_name}
"""

    top_proj = projects[0] if projects else profile.major
    interest_str = ", ".join((profile.interests or [])[:5]) or "graduate research in my field"
    subject = f"Research inquiry — {profile.major} ({sch_country}) — {profile.full_name.split()[0] if profile.full_name else 'Applicant'}"
    email_body = f"""Dear Professor,

I am {profile.full_name}, a prospective {profile.degree_level} student in {profile.major}. I am writing to respectfully inquire whether you are considering new students in the coming cycle, and whether my background might align with your group’s research directions.

**Background.** My technical work centers on {langs.split(",")[0] if langs else "software and systems"}; representative activity includes {top_proj}. I have been building depth in: {interest_str}.

**Why I am reaching out.** I am targeting fully funded graduate study in {sch_country} and am identifying labs where my skills and research interests overlap with ongoing projects. Your group’s work appears relevant to my trajectory; I would value the chance to learn whether there could be a fit.

**Evidence I can share.** I can provide a CV, GitHub profile, transcript summary, and a short research statement. If helpful, I am happy to tailor a one-page summary to your specific papers or project themes.

**Ask.** Would you be open to a brief email exchange, or to guidance on whether I should apply through the formal admissions path and mention your lab in my statement?

Thank you for your time and consideration.

Best regards,
{profile.full_name}
{profile.degree_level.title()} applicant · {profile.major}
"""

    outline = [
        "Hook — problem + motivation for graduate study",
        "Evidence — projects, tools, outcomes",
        "Fit — scholarship / program / country",
        "Plan — near-term goals",
        "Closing",
    ]

    return DraftOutputs(
        professor_email_subject=subject,
        professor_email_body=email_body,
        sop_outline=outline,
        scholarship_sop=sop,
        motivation_letter=motivation,
    )


def _merge_drafts(llm: dict, template: DraftOutputs) -> DraftOutputs:
    def pick(key: str, alt: str, min_len: int) -> str:
        v = llm.get(key)
        if isinstance(v, str) and len(v.strip()) >= min_len:
            return v.strip()
        return alt

    ol = llm.get("sop_outline")
    if not isinstance(ol, list) or len(ol) < 3:
        ol = template.sop_outline

    return DraftOutputs(
        professor_email_subject=pick("professor_email_subject", template.professor_email_subject, 12),
        # Prefer our full template unless the LLM returns a similarly complete email
        professor_email_body=pick("professor_email_body", template.professor_email_body, 280),
        sop_outline=ol,
        scholarship_sop=pick("scholarship_sop", template.scholarship_sop or "", 200),
        motivation_letter=pick("motivation_letter", template.motivation_letter or "", 100),
    )


async def drafting_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None:
        return state

    template = _rich_template_documents(state)

    target_opp = state.scored[0].opportunity if state.scored else None
    target_name = target_opp.title if target_opp else "Global Scholarships"
    target_country = target_opp.country if target_opp else profile.target_country

    system_instruction = """You are the ApplySmart Drafting Agent. Generate SCHOLARSHIP-SPECIFIC documents.

Output a JSON object with keys:
professor_email_subject, professor_email_body, sop_outline (array of strings),
scholarship_sop (markdown string), motivation_letter (markdown string).
"""

    context = {
        "profile": profile.model_dump(mode="json"),
        "target_scholarship": target_name,
        "target_country": target_country,
        "dna": profile.dna.model_dump(mode="json") if profile.dna else None,
    }

    prompt = f"Draft scholarship materials for {profile.full_name} targeting {target_name} in {target_country}.\n\nContext:\n{json.dumps(context, indent=2)}"

    try:
        res_text = await chat_completion(
            prompt, system_instruction=system_instruction, response_format="json_object"
        )
        if not res_text or res_text.strip().startswith("LLM_NOT_CONFIGURED"):
            return state.model_copy(update={"drafts": template})

        raw = _strip_json_fences(res_text)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return state.model_copy(update={"drafts": template})

        merged = _merge_drafts(data, template)
        return state.model_copy(update={"drafts": merged})
    except Exception as e:
        print(f"[DraftingAgent] Error: {e}")
        return state.model_copy(update={"drafts": template})
