## ApplySmart (Hackathon)

ApplySmart is a **7-agent scholarship application assistant** designed for the “Agent” hackathon theme:
it **understands a user’s goal**, **searches**, **ranks**, **blocks bad options (“Critic Agent”)**, and then **executes** by drafting materials and scheduling follow-ups.

### Architecture (7 agents)
- **Profile Agent**: collects user profile + constraints; detects gaps (e.g., “no IELTS”).
- **Opportunity Agent**: searches the live web (with a cached fallback for demos).
- **Scoring Agent**: scores + buckets opportunities (Safe / Target / Reach).
- **Critic Agent**: vetoes unrealistic/invalid choices and routes back for re-ranking.
- **Planning Agent**: produces a 7‑day execution roadmap.
- **Drafting Agent**: generates ready-to-send outreach email + SOP outline.
- **Follow‑Up Agent**: persists follow-up actions (timer simulated for demo).

### Repo layout
```text
backend/
  applysmart/
    agents/
    graph/
    models/
    services/
  scripts/
```

### Quickstart (CLI demo)
Prereqs: Python 3.11+ (3.12 recommended; some agent libs may warn on 3.14)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional (live web search): copy env template and set an API key
cp .env.example .env
# edit `.env` and set SERPER_API_KEY=... (or TAVILY_API_KEY=...)

python -m applysmart.scripts.demo_run
```

### Profile Agent UI (links + resume → structured profile + auto-CV)

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn applysmart.api.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` — paste **GitHub** (URL or username), optional **LinkedIn** / **portfolio** URLs, upload **PDF or text resume**. The page shows **languages, projects, interests, strengths**, ingest warnings, and **Markdown auto-CV**; use **Download auto-CV** for a `.md` file.

### Demo behavior (what judges should see)
- A **full multi-step trace** from Profile → Opportunity → Scoring → Critic (veto) → Planning → Drafting → Follow‑Up.
- The **Critic Agent** visibly blocks at least one “bad” opportunity and triggers re-ranking.

### Guaranteed Critic “WOW” (rehearsal / recording)
Force a deliberate bad #1 so the Critic always vetos once, then the pipeline re-scores after demotion:

```bash
export APPLYSMART_DEMO_VETO=1
python -m applysmart.scripts.demo_run
```

The CLI prints a short **critic trace** (block reasons + demotion). Unset the variable for an organic run.

