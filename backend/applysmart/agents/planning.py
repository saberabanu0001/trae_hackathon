from __future__ import annotations

import json
from applysmart.models.core import ApplySmartState, ExecutionPlan
from applysmart.services.llm import chat_completion


async def planning_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None:
        return state

    # Use the DNA and top scholarships to create a custom 7-day sprint
    top_opps = [s.opportunity.title for s in state.scored[:3]]
    
    system_instruction = """You are the ApplySmart Planning Agent. Your job is to create a 
HIGH-VELOCITY 7-day scholarship application sprint.

CRITICAL RULES:
1. Each day must have exactly ONE clear, actionable task.
2. Focus 100% on securing FULLY-FUNDED scholarships.
3. Use the student's DNA and specific target scholarships in the plan.
4. Tasks should include: profile optimization, document drafting, and submission.

Output MUST be a JSON object with:
- days: Array of exactly 7 strings (Day 1, Day 2, etc.)
"""

    context = {
        "profile": profile.model_dump(mode="json"),
        "top_scholarships": top_opps,
        "dna": profile.dna.model_dump() if profile.dna else "Not provided"
    }

    prompt = f"Create a 7-day scholarship winning plan for {profile.full_name}.\n\nContext:\n{json.dumps(context, indent=2)}"

    try:
        res_text = await chat_completion(prompt, system_instruction=system_instruction, response_format="json_object")
        data = json.loads(res_text)
        return state.model_copy(update={"plan": ExecutionPlan(days=data.get("days", []))})
    except Exception as e:
        print(f"[PlanningAgent] Error: {e}")
        # Fallback to the default 7-day plan
        days = [
            "Day 1: Collect passport, transcripts, and initial CV drafts.",
            "Day 2: Identify 3 target professors/labs aligned with your DNA.",
            "Day 3: Tailor CV and draft the first scholarship Motivation Letter.",
            "Day 4: Refine Statement of Purpose based on scholarship requirements.",
            "Day 5: Request recommendation letters from current faculty.",
            "Day 6: Final proofreading and document assembly.",
            "Day 7: Submit first 2 applications and schedule follow-ups."
        ]
        return state.model_copy(update={"plan": ExecutionPlan(days=days)})

