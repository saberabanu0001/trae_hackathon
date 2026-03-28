from __future__ import annotations

import json
from applysmart.models.core import ApplySmartState, DraftOutputs
from applysmart.services.llm import chat_completion

async def drafting_agent(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    if profile is None:
        return state

    # Identify the top target opportunity for personalization
    target_opp = state.scored[0].opportunity if state.scored else None
    target_name = target_opp.title if target_opp else "Global Scholarships"
    target_country = target_opp.country if target_opp else profile.target_country

    system_instruction = """You are the ApplySmart Drafting Agent. Your job is to generate high-quality, 
SCHOLARSHIP-SPECIFIC documents for international students. 

CRITICAL RULES:
1. NEVER mention self-funding. 
2. ALWAYS emphasize the "Opportunity DNA" (Technical Depth, Research Fit, etc.).
3. CROSS-REFERENCE GitHub evidence (projects, languages) and Resume text.
4. PERSONALIZATION: Tailor the content to the specific scholarship if provided.
5. NO GENERIC FLUFF: Use concrete examples from the profile.

Output MUST be a JSON object with:
- professor_email_subject: String
- professor_email_body: String
- sop_outline: Array of strings
- scholarship_sop: Markdown string (The full Statement of Purpose)
- motivation_letter: Markdown string (Specifically for a fully-funded scholarship)
"""

    context = {
        "profile": profile.model_dump(mode="json"),
        "target_scholarship": target_name,
        "target_country": target_country,
        "dna": profile.dna.model_dump() if profile.dna else "Not provided",
    }

    prompt = f"Draft scholarship application materials for {profile.full_name} targeting {target_name}.\n\nContext:\n{json.dumps(context, indent=2)}"

    try:
        res_text = await chat_completion(prompt, system_instruction=system_instruction, response_format="json_object")
        data = json.loads(res_text)
        
        return state.model_copy(
            update={
                "drafts": DraftOutputs(
                    professor_email_subject=data.get("professor_email_subject", ""),
                    professor_email_body=data.get("professor_email_body", ""),
                    sop_outline=data.get("sop_outline", []),
                    scholarship_sop=data.get("scholarship_sop"),
                    motivation_letter=data.get("motivation_letter")
                )
            }
        )
    except Exception as e:
        print(f"[DraftingAgent] Error: {e}")
        # Fallback to basic template if LLM fails
        return _fallback_drafts(state)

def _fallback_drafts(state: ApplySmartState) -> ApplySmartState:
    profile = state.profile
    subject = f"Research Inquiry — {profile.major} ({profile.target_country})"
    body = f"Dear Professor,\n\nI am {profile.full_name}, interested in {profile.major} scholarships..."
    return state.model_copy(
        update={
            "drafts": DraftOutputs(
                professor_email_subject=subject,
                professor_email_body=body,
                sop_outline=["Hook", "Journey", "Why this program", "Goals", "Conclusion"]
            )
        }
    )

