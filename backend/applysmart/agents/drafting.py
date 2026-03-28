from __future__ import annotations

from applysmart.models.core import ApplySmartState, DraftOutputs


def drafting_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None:
        return state

    subject = f"Research Collaboration Inquiry — {profile.major} ({profile.target_country})"

    body = "\n".join(
        [
            "Dear Professor [Name],",
            "",
            f"I am {profile.full_name}, currently studying {profile.major} and preparing for {profile.degree_level.title()} applications.",
            f"My background includes projects in {', '.join(profile.interests[:2])}.",
            "",
            "I recently read your work on [specific paper/project] and found strong alignment with my interests.",
            "Would you be open to a short call to discuss potential supervision or collaboration opportunities?",
            "",
            "I have attached my CV and a brief research statement. Thank you for your time.",
            "",
            "With respect,",
            f"{profile.full_name}",
        ]
    )

    sop_outline = [
        "Para 1 — Hook: a specific problem that motivated you (concrete, not generic).",
        "Para 2 — Your journey: relevant projects, TA/RA work, skills and evidence.",
        "Para 3 — Why this program: specific faculty/labs/curriculum alignment.",
        "Para 4 — What you will do: research direction, 2–3 year goals, expected impact.",
        "Para 5 — Why you: proof, outcomes, and what you uniquely bring.",
    ]

    return state.model_copy(
        update={
            "drafts": DraftOutputs(
                professor_email_subject=subject,
                professor_email_body=body,
                sop_outline=sop_outline,
            )
        }
    )

