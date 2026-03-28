from __future__ import annotations

from applysmart.models.core import ApplySmartState, FollowUpItem


def followup_agent(state: ApplySmartState) -> ApplySmartState:
    """
    Scaffold: create a follow-up item due in 7 days.
    A real implementation would persist state and trigger on a scheduler.
    """
    if state.drafts is None:
        return state

    item = FollowUpItem(
        due_in_days=7,
        channel="email",
        message="Follow up on the previous email. Ask politely if they had time to review your CV and whether a short call is possible.",
    )

    return state.model_copy(update={"followups": [*state.followups, item]})

