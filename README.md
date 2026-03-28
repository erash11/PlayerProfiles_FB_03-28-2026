# Football Player Performance Report
## Claude Code Workflow Guide

**Audience:** Mid-level users familiar with Claude Code, MCPs, and basic agentic workflows
**Environment:** VS Code + Claude Code + GitHub (Windows)
**Project:** Baylor Athletics Football Performance Report — B.A.I.R. Initiative

---

## What This Project Is

A React + FastAPI web application that pulls CMJ, GPS, and body weight data into a
unified football athlete performance report. The landing page ranks athletes by TSA
composite score. Clicking an athlete drills into their individual profile with a spider
chart, metrics table, and longitudinal trend charts.

---

## Project Setup

### 1. Clone the repo and open in VS Code

```bash
git clone https://github.com/YOUR_ORG/football-player-report.git
cd football-player-report
code .
```

### 2. Set up the Python backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows activation
pip install -r requirements.txt
```

### 3. Set up the React frontend

```bash
cd frontend
npm install
```

### 4. Initialize the database

```bash
cd backend
python data_importer.py --init
```

This creates the DuckDB database and runs the schema from docs/DATA_SCHEMA.md.

---

## Working With Claude Code

### Starting a session

From the project root in VS Code terminal:

```bash
claude
```

Or use the Claude Code panel in the VS Code sidebar if you have the extension installed.

### Giving Claude Code context at the start of a session

Always orient Claude Code to the project before diving into a task:

```
Read docs/TECH_SPEC.md, docs/DATA_SCHEMA.md, and docs/TSA_METHODOLOGY.md.
This is the Baylor Athletics football player performance report project.
We are working on [describe what you need today].
```

If resuming work on a specific file:

```
Read backend/tsa_scorer.py and docs/TSA_METHODOLOGY.md.
We are continuing work on the TSA scoring logic from last session.
```

### Effective prompt patterns for this project

**Building a new component from the wireframe spec:**
```
Using the wireframe in docs/UI_WIREFRAMES.md Section 3 (Individual Athlete Profile),
build the SpiderChart component at frontend/src/components/SpiderChart.tsx.
Use D3.js. Accept t-score values for 7 axes defined in docs/TSA_METHODOLOGY.md
Section 6. Overlay a second dataset for team average comparison. Use TypeScript
interfaces for all props.
```

**Implementing backend scoring logic:**
```
Implement the TSA scoring logic in backend/tsa_scorer.py following
docs/TSA_METHODOLOGY.md exactly. Use pandas. Accept a DataFrame and a domain_map dict.
Return a DataFrame with per-metric z-scores, t-scores, domain t-scores, composite TSA,
rank, and RAG status. Include the domain-level compositing approach.
```

**Adding an API endpoint:**
```
Add a FastAPI endpoint at GET /api/athlete/{id}/tsa to backend/routes/athlete.py.
It should return all tsa_scores rows for that athlete ordered by report_period_start.
Follow the existing patterns in the file. Use the database.py query layer.
```

**Updating schema after pipeline docs arrive:**
```
I now have the Catapult GPS pipeline documentation. The actual export columns are:
[paste column names here].
Update docs/DATA_SCHEMA.md and backend/database.py to match these column names.
Also update data_importer.py to map these fields correctly on CSV import.
```

**Debugging a component:**
```
The spider chart is rendering the athlete polygon but the team average overlay is not
showing. Current file: frontend/src/components/SpiderChart.tsx. Expected behavior is
in docs/UI_WIREFRAMES.md Section 3.1 (spider chart section). What is causing this
and how do we fix it?
```

---

## Git Workflow

### Branch strategy

```
main        stable, tested version
dev         active development
feature/    optional — specific feature branches for larger work
```

### Typical session workflow

```bash
git checkout dev

# Claude Code makes changes in VS Code

git diff                       # review what changed
git add -p                     # stage selectively if needed
git commit -m "feat: add spider chart component"
git push origin dev
```

### Commit message conventions

```
feat:      new feature or component
fix:       bug fix
refactor:  restructure without changing behavior
data:      schema or pipeline changes
docs:      documentation updates
```

### Merging to main when stable

```bash
git checkout main
git merge dev
git push origin main
```

---

## Running the App Locally

### Backend

```bash
cd backend
venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

FastAPI auto-generated docs available at: http://localhost:8000/docs
Use this to test endpoints directly before wiring up the frontend.

### Frontend

```bash
cd frontend
npm run dev
```

App runs at: http://localhost:5173

---

## Importing Data From Your Pipelines

Place CSV exports in the data/raw/ directory, then run:

```bash
# CMJ data from ForceDecks
python data_importer.py --source cmj --file data/raw/cmj_export.csv

# GPS session summaries from Catapult
python data_importer.py --source gps --file data/raw/gps_sessions.csv

# Body weight measurements
python data_importer.py --source bodyweight --file data/raw/bodyweight.csv
```

After importing, generate a report for the period:

```bash
python tsa_scorer.py --start 2026-01-01 --end 2026-05-01 --label "Spring 2026"
```

This populates the tsa_scores table and makes the data available in the app.
You can also trigger report generation from the UI via the "Generate New Report" button.

---

## Handing Off Pipeline Docs to Claude Code

When you are ready to connect actual pipeline outputs:

1. Copy your pipeline documentation or existing Claude.md files into docs/
2. Start a Claude Code session:

```
I have added the CMJ pipeline documentation to docs/cmj_pipeline.md.
Read that file and the current docs/DATA_SCHEMA.md.
Update DATA_SCHEMA.md and backend/data_importer.py to match the actual
ForceDecks export column names and data types.
```

3. Review diffs in VS Code, test with a sample CSV, commit if good
4. Repeat the same process for GPS and body weight pipeline docs

The schema is intentionally flexible — these updates should be contained and straightforward.

---

## Project File Map

```
backend/
  main.py             FastAPI app entry point — all routes registered here
  tsa_scorer.py       TSA scoring logic (z-scores, t-scores, domain compositing, RAG)
  database.py         DuckDB connection and query layer
  data_importer.py    CSV import scripts for CMJ, GPS, body weight
  models.py           Pydantic models for API request/response validation
  routes/
    team.py           /api/team/* endpoints
    athlete.py        /api/athlete/* endpoints

frontend/src/
  App.tsx             Root component and React Router setup
  pages/
    TeamPage.tsx      Landing page — mounts TeamSnapshot
    AthletePage.tsx   Drill-down page — mounts AthleteProfile
  components/
    TeamSnapshot.tsx  Roster table with position filter and RAG indicators
    AthleteProfile.tsx  Parent component — fetches data, passes to children
    MetricsTable.tsx  CMJ / GPS / Body Weight grouped metrics table
    SpiderChart.tsx   D3.js radar chart with overlay support
    TrendChart.tsx    Recharts longitudinal line charts
    ComparisonPanel.tsx  Collapsible athlete comparison panel

data/
  raw/                Drop CSV exports from pipelines here (gitignored)
  db/                 DuckDB database file (gitignored)

docs/
  TECH_SPEC.md        Architecture, stack, phases, file structure
  DATA_SCHEMA.md      Database tables and field definitions
  UI_WIREFRAMES.md    Layout specs and component inventory
  TSA_METHODOLOGY.md  Scoring framework with Python implementation
  README.md           This file — Claude Code workflow guide
```

---

## .gitignore Essentials

Add these to your .gitignore:

```
# Python
venv/
__pycache__/
*.pyc
.env

# Database — do not version control
data/db/
*.duckdb

# Raw data — do not version control
data/raw/

# Node
node_modules/
dist/
.env.local

# OS
.DS_Store
Thumbs.db
```

---

## Common Issues

**"No athletes found" on landing page**
- Verify data has been imported: run data_importer.py and check for errors
- Verify a report has been generated for the selected period: run tsa_scorer.py
- Test the endpoint directly at http://localhost:8000/docs -> GET /api/team/snapshot

**Spider chart not rendering**
- Check that all 7 t-score dimensions are present in the data returned by the API
- Missing values cause D3 to fail silently — open browser console and check for errors
- Athletes missing one domain should show available axes only; log a warning for the rest

**TSA scores all equal 50**
- This means only one or two athletes have data in the reporting window
- Z-scores collapse to zero with n=1; you need at least 5-10 athletes for meaningful spread
- Check that your date range actually covers sessions with data

**Import errors on CSV files**
- Check column name mapping in data_importer.py against your actual export headers
- These mappings will be updated once pipeline docs are provided — see DATA_SCHEMA.md TODO list

---
*This project is part of the B.A.I.R. Initiative — Baylor Athletics Innovation Research.*
*For sport science methodology questions, see TSA_METHODOLOGY.md.*
*For data structure questions, see DATA_SCHEMA.md.*
