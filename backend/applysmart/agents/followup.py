from __future__ import annotations

import json
from applysmart.models.core import ApplySmartState, FollowUpItem
from applysmart.services.llm import chat_completion


async def followup_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None or not state.scored:
        return state

    top_scholarship = state.scored[0].opportunity.title
    
    system_instruction = """You are the ApplySmart Assistant Lifecycle Agent. 
Your job is to create a 3-month proactive monitoring and follow-up plan.

CRITICAL RULES:
1. Generate exactly 3-4 lifecycle events.
2. Events must include:
   - due_in_days: Integer (e.g., 7, 30, 60, 90)
   - channel: String ("email", "notification", or "monitoring")
   - message: String (A proactive action, check-in, or monitoring alert)
3. Lifecycle actions:
   - 1 week: Follow-up on specific application.
   - 1 month: Opportunity Agent re-scans the web for new portal openings.
   - 2 months: DNA Vector update (suggest adding new GitHub projects/skills).
   - 3 months: Critic Agent re-evaluates eligibility for late-season programs.

Output MUST be a JSON object with:
- followups: Array of objects (FollowUpItem)
"""

    context = {
        "profile": profile.model_dump(mode="json"),
        "top_scholarship": top_scholarship,
        "dna": profile.dna.model_dump() if profile.dna else "Not provided"
    }

    prompt = f"Create a 21-day follow-up sequence for {profile.full_name} regarding {top_scholarship}.\n\nContext:\n{json.dumps(context, indent=2)}"

    try:
        res_text = await chat_completion(prompt, system_instruction=system_instruction, response_format="json_object")
        data = json.loads(res_text)
        items = [FollowUpItem.model_validate(item) for item in data.get("followups", [])]
        return state.model_copy(update={"followups": items})
    except Exception as e:
        print(f"[FollowUpAgent] Error: {e}")
        # Fallback to basic follow-up
        item = FollowUpItem(
            due_in_days=7,
            channel="email",
            message="Polite check-in: Ask if they have had time to review your materials.",
        )
        return state.model_copy(update={"followups": [item]})

