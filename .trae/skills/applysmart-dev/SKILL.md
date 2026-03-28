---
name: "applysmart-dev"
description: "Assists in building ApplySmart agents, ensuring all API routes return JSONResponse and follow the 7-agent pipeline architecture. Invoke when creating or modifying agents, models, or API endpoints."
---

# ApplySmart Development Skill

This skill provides guidelines and patterns for developing the ApplySmart multi-agent scholarship application system.

## Core Architecture

ApplySmart is a 7-agent pipeline orchestrated via LangGraph:
1. **Profile Agent**: Ingests and synthesizes student profiles.
2. **Opportunity Agent**: Searches for matching scholarships.
3. **Scoring Agent**: Ranks opportunities based on DNA fit.
4. **Critic Agent**: Vetoes ineligible applications.
5. **Planning Agent**: Creates application roadmaps.
6. **Drafting Agent**: Generates emails and SOPs.
7. **Follow-Up Agent**: Manages persistence and follow-ups.

## API Response Rule (CRITICAL)

**Rule**: All FastAPI routes must return `JSONResponse` (or a dict that FastAPI converts to JSON) even on error.
- **Pattern**: Wrap all business logic in `try/except`.
- **Error Response**: Return `{"ok": false, "error": "...", "status": "error", "message": "..."}`.
- **Success Response**: Always include `"ok": true`.

## Data Modeling

- Use Pydantic models from [core.py](file:///Users/saberabanu/Documents/Research/SOAP/soap_/Projects/ApplySmart/backend/applysmart/models/core.py).
- All inter-agent communication must use `ApplySmartState`.
- DNA vectors are 6-axis scores (0-100) with mandatory explanation strings.

## LLM Synthesis Pattern

- Use the LLM to "reason" and "synthesize" rather than just extracting text.
- Follow the pattern in [profile_ingest.py](file:///Users/saberabanu/Documents/Research/SOAP/soap_/Projects/ApplySmart/backend/applysmart/services/profile_ingest.py) for all agents.
- Always include a `system_instruction` that defines the agent's role and specific constraints.

## GitHub Analysis

- Weighted language detection based on repo size.
- README quality scoring (max 100).
- Conflict detection between CV claims and GitHub evidence.
