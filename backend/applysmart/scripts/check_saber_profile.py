from __future__ import annotations

import json
from pathlib import Path

from applysmart.models.core import ApplySmartState, Profile
from applysmart.services.profile_ingest import ingest_profile_sources
from dotenv import load_dotenv


async def check_profile():
    # Load env
    backend_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=backend_root / ".env", override=False)

    # Use the real profile data from the prompt
    profile = Profile(
        full_name="Sabera Banu",
        nationality="Bangladesh",
        target_country="Australia",
        degree_level="master",
        major="Computer Science",
        gpa=4.11,
        gpa_scale_max=4.5,
        has_ielts=False,
        budget_usd=500,
        interests=["multi-agent systems", "AI", "GarmentAI"],
        github_url="https://github.com/saberabanu0001",
        # Simulating extracted resume text with the PyTorch/TensorFlow claim
        resume_text="""
Sabera Banu
Best Innovation Award at Sejong University Capstone 2025
Teaching Assistant (2+ years)
Professional AI Developer at JBRSOFT since Jan 2024
Skills: PyTorch, TensorFlow, Python, TypeScript, Dart
Projects: GarmentAI (leading team of 7), PrescriptionPro, CalmateAI
        """
    )

    print("--- Running Profile Ingest ---")
    profile, _ = await ingest_profile_sources(profile)

    print("\n--- Profile Agent Output (JSON) ---")
    print(profile.model_dump_json(indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(check_profile())
