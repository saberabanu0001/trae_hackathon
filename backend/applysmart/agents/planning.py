from __future__ import annotations

from applysmart.models.core import ApplySmartState, ExecutionPlan


def planning_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None:
        return state

    days = [
        "Day 1: Confirm shortlist + collect documents (passport, transcript, CV).",
        "Day 2: Identify 3 target professors/labs aligned with your interests.",
        "Day 3: Draft professor outreach email + tailor CV bullet points.",
        "Day 4: Draft SOP outline; map projects to program requirements.",
        "Day 5: Fill application forms; request recommendation letters if needed.",
        "Day 6: Review + proofread; verify eligibility and required tests/documents.",
        "Day 7: Submit (or schedule submission) + activate follow-up in 7 days.",
    ]

    return state.model_copy(update={"plan": ExecutionPlan(days=days)})

