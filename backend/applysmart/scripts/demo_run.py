from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from rich import print as rprint
from rich.panel import Panel

from applysmart.graph.langgraph_app import build_app
from applysmart.models.core import ApplySmartState, Profile


def _show_state(state: ApplySmartState) -> None:
    if state.gaps:
        rprint(Panel.fit("\n".join([*state.gaps.notes]), title="Profile Agent → gaps/notes"))

    if state.meta.get("opportunity_source") == "live":
        q = state.meta.get("opportunity_query", "")
        n = state.meta.get("opportunity_live_count", 0)
        rprint(Panel.fit(f"Query: {q}\nLive results: {n}", title="Opportunity Agent → live web search"))
    else:
        rprint(Panel.fit("Using cached demo opportunities (no API key configured).", title="Opportunity Agent"))

    if state.scored:
        lines: list[str] = []
        for i, s in enumerate(state.scored[:3], start=1):
            opp = s.opportunity
            extracted_bits: list[str] = []
            if opp.deadline:
                extracted_bits.append(f"deadline={opp.deadline.isoformat()}")
            if opp.requires_ielts is not None:
                extracted_bits.append(f"ielts={'yes' if opp.requires_ielts else 'no'}")
            if opp.fully_funded is not None:
                extracted_bits.append(f"funded={'yes' if opp.fully_funded else 'no'}")
            extra = f"  • {'  '.join(extracted_bits)}" if extracted_bits else ""
            lines.append(
                f"{i}. {opp.title}  • score={s.total_score:.2f}  • {s.bucket.value.upper()}{extra}"
            )
        rprint(Panel.fit("\n".join(lines), title="Scoring Agent → top ranked"))

    if state.critic:
        rprint(Panel.fit(state.critic.reason, title=f"Critic Agent → {state.critic.action.upper()}"))

    trace = state.meta.get("critic_trace")
    if trace:
        lines = []
        for e in trace[-5:]:
            lines.append(str(e))
        rprint(Panel.fit("\n".join(lines), title="Critic trace (last 5 events)"))

    if state.drafts:
        rprint(Panel.fit(state.drafts.professor_email_subject, title="Drafting Agent → email subject"))

    if state.followups:
        rprint(Panel.fit(f"Scheduled in {state.followups[-1].due_in_days} days", title="Follow‑Up Agent → next action"))


def main() -> None:
    # Load `.env` from the backend root (works regardless of current working directory).
    backend_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=backend_root / ".env", override=False)
    rprint(Panel.fit("ApplySmart — 7-Agent Pipeline Demo", title="Start"))

    # Demo profile matching the pitch: Bangladesh → South Korea, no IELTS.
    initial = ApplySmartState(
        profile=Profile(
            full_name="Demo Student",
            nationality="Bangladesh",
            target_country="South Korea",
            degree_level="master",
            major="Computer Science",
            gpa=3.2,
            has_ielts=False,
            budget_usd=0,
            interests=["multi-agent systems", "automation"],
        )
    )

    app = build_app()
    out = app.invoke(initial.model_dump(), config={"recursion_limit": 25})
    final_state = ApplySmartState.model_validate(out)

    _show_state(final_state)
    rprint(
        Panel.fit(
            "Done. Set APPLYSMART_DEMO_VETO=1 for a guaranteed Critic block + rerank on stage.",
            title="End",
        )
    )


if __name__ == "__main__":
    main()

