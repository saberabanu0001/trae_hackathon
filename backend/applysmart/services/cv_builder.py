from __future__ import annotations

from applysmart.models.core import Profile


def render_cv_markdown(p: Profile) -> str:
    lines: list[str] = []
    lines.append(f"# {p.full_name}")
    lines.append("")
    lines.append("## Summary")
    lines.append(
        f"- **Degree target:** {p.degree_level.title()} · **Field:** {p.major}"
    )
    lines.append(f"- **From:** {p.nationality} → **Target:** {p.target_country}")
    if p.academic_status:
        lines.append(f"- **Status:** {p.academic_status}")
    ielts_line = "Yes" if p.has_ielts else "No"
    if p.ielts_score is not None:
        ielts_line = f"{p.ielts_score} (declared)"
    lines.append(
        f"- **CGPA:** {p.gpa:.2f} / {p.gpa_scale_max:g} · **IELTS:** {ielts_line}"
    )
    if p.budget_usd:
        lines.append(f"- **Budget (declared):** ${p.budget_usd:,}")
    lines.append("")

    if p.linkedin_url or p.github_url or p.portfolio_urls:
        lines.append("## Links")
        if p.linkedin_url:
            lines.append(f"- LinkedIn: {p.linkedin_url}")
        if p.github_url:
            lines.append(f"- GitHub: {p.github_url}")
        for u in p.portfolio_urls:
            lines.append(f"- Portfolio: {u}")
        lines.append("")

    if p.languages:
        lines.append("## Languages & tools")
        lines.append(", ".join(f"`{x}`" for x in p.languages))
        lines.append("")

    if p.projects:
        lines.append("## Projects")
        for pr in p.projects[:25]:
            lines.append(f"- {pr}")
        lines.append("")

    if p.research_interests:
        lines.append("## Research interests")
        for ri in p.research_interests:
            lines.append(f"- {ri}")
        lines.append("")

    if p.strengths:
        lines.append("## Strengths (auto)")
        for s in p.strengths:
            lines.append(f"- {s}")
        lines.append("")

    if p.opportunity_type_verdict:
        lines.append("## Opportunity type verdict")
        lines.append(p.opportunity_type_verdict)
        lines.append("")

    if p.verdict:
        lines.append("## Overall verdict")
        lines.append(p.verdict)
        lines.append("")

    if p.action_plan:
        lines.append("## 30-day action plan")
        for step in p.action_plan:
            lines.append(f"- {step}")
        lines.append("")

    if p.consistency_summary:
        lines.append("## Profile consistency")
        lines.append(p.consistency_summary)
        lines.append("")

    if p.interests:
        lines.append("## Focus areas (manual / merged)")
        lines.append(", ".join(p.interests))
        lines.append("")

    if p.resume_text:
        lines.append("## Resume excerpt (source text)")
        lines.append("```")
        lines.append(p.resume_text[:8000] + ("…" if len(p.resume_text) > 8000 else ""))
        lines.append("```")

    return "\n".join(lines).strip() + "\n"
