from __future__ import annotations

import json
from applysmart.models.core import ApplySmartState, FollowUpItem
from applysmart.services.llm import chat_completion


async def followup_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None or not state.scored:
        return state

    top_scholarship = state.scored[0].opportunity.title
    
    system_instruction = """You are the ApplySmart Follow-up Agent. Your job is to create a 
SMART email follow-up sequence for scholarship applications.

CRITICAL RULES:
1. Generate exactly 2 follow-up tasks.
2. Each task MUST include:
   - due_in_days: Integer (7, 14, or 21)
   - channel: String ("email")
   - message: String (A polite follow-up email draft or specific instruction)
3. Tailor the messages to the student's background and top scholarship match.

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

