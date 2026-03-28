# Football Player Performance Progress Report
## Technical Specification

**Version:** 1.0
**Created:** March 2026
**Project:** Baylor Athletics — B.A.I.R. Initiative
**Status:** Ready for Development

---

## 1. Overview

The Football Player Performance Progress Report is an on-demand web application that aggregates
countermovement jump (CMJ), GPS, and body weight data into a unified athlete profiling system.
It surfaces a team-level dashboard with composite athleticism scores, then allows staff to drill
into individual athlete profiles featuring data tables, spider charts, and longitudinal trend analysis.

Reports are generated manually at key checkpoints:
- End of spring football
- End of regular season
- Post-summer training block
- Ad-hoc coaching staff requests

---

## 2. Architecture Overview

### 2.1 Tech Stack

**Frontend**
- React 18+ with TypeScript
- D3.js for spider/radar charts
- Recharts for longitudinal trend lines
- Tailwind CSS for styling
- React Router for team view to athlete profile navigation
- Axios for API calls

**Backend**
- Python + FastAPI (aligns with existing Python pipeline stack)
- Pandas for normalization and processing
- DuckDB as the aggregation layer

**Data Sources**
- CMJ pipeline -> ForceDecks
- GPS pipeline -> Catapult API / CSV export
- Body weight pipeline -> manual entry or integrated source

**DevOps**
- GitHub for version control
- Claude Code for AI-assisted development
- VS Code as primary IDE

### 2.2 Data Flow

```
CMJ Pipeline  --+
GPS Pipeline  --+--->  DuckDB (aggregation layer)
Body Wt. Pipe --+           |
                             v
                    Python: Z-score -> T-score -> TSA
                             |
                             v
                    FastAPI (REST endpoints)
                             |
                             v
                    React Frontend
                    +-- Team Snapshot (landing page)
                    +-- Athlete Profile (drill-down)
```

---

## 3. Application Structure

### 3.1 Landing Page — Team Snapshot

Entry point. All football athletes ranked by TSA composite score.

**Components:**
- Header bar: report metadata, date range, generation timestamp
- Position filter: QB, RB, WR, TE, OL, DL, LB, DB, ST, K/P
- Athlete roster table sorted by TSA rank
- RAG indicator per athlete (Green / Amber / Red)
- Athlete name click target navigates to individual profile

**Table Columns:** Rank | Name | Position | Class | TSA Score | CMJ T | GPS T | Body Wt. T | Status

Landing page stays clean — no red flag breakdowns here. The drill-down tells the individual story.

---

### 3.2 Individual Athlete Profile — Drill-Down

**Section A — Header**
Name, jersey, position, class year, TSA score + RAG badge, report period label, back button

**Section B — Performance Metrics Table**
Metric | Raw Value | Z-Score | T-Score | Team Avg | Position Avg
Rows grouped by CMJ, GPS, Body Weight with section headers

**Section C — Spider Chart**
- Axes: CMJ Jump Height, CMJ Peak Power, CMJ Reactivity, GPS Speed, GPS Endurance, GPS Workload, Body Composition
- Athlete overlaid on team average (position average toggle available)
- All axes on t-score scale (0-100)
- Built in D3.js with React wrapper

**Section D — Longitudinal Trend Charts**
- Separate line charts per domain (CMJ, GPS, Body Weight)
- Time axis spans all available data for that athlete (single season to multi-year)
- Training cycle boundaries as vertical reference lines
- Gaps in line with tooltip for missing data
- Built in Recharts

**Section E — Comparison Panel (Expandable)**
- Search/select 1-2 additional athletes
- Side-by-side metric table
- Spider chart overlay with color-coded athletes and legend

---

## 4. API Endpoints

```
GET  /api/team/snapshot                 All athletes, TSA scores, RAG status
GET  /api/team/snapshot?position=DB     Filtered by position
GET  /api/athlete/{id}                  Full profile for one athlete
GET  /api/athlete/{id}/cmj              CMJ history
GET  /api/athlete/{id}/gps              GPS session history
GET  /api/athlete/{id}/bodyweight       Body weight history
GET  /api/athlete/{id}/tsa              TSA scores over time
POST /api/report/generate               Trigger report for date range
GET  /api/athletes/list                 All athletes (for comparison search)
```

---

## 5. Implementation Phases

**Phase 1 — Data Foundation**
- Set up repo structure
- Validate schema against pipeline docs
- Build CSV import scripts (CMJ, GPS, body weight)
- Set up DuckDB aggregation database
- Implement tsa_scorer.py
- Build FastAPI with core endpoints

**Phase 2 — Frontend MVP**
- React + TypeScript + Tailwind setup
- Team snapshot page (table + RAG)
- Individual athlete profile layout
- Spider chart (D3.js)
- Longitudinal trend charts (Recharts)

**Phase 3 — Refinement**
- Athlete comparison feature
- Position filtering
- Multi-year tenure handling
- Missing data graceful fallbacks
- Red flag indicators in drill-down

**Phase 4 — Polish and Export**
- PDF export of individual profiles
- Report date range selector UI
- Performance optimization (lazy loading, score caching)
- Role-based access (admin / coaching staff / athlete)

---

## 6. Key Technical Decisions

**Backend:** Python + FastAPI. Aligns with existing pipeline stack.
**Database:** DuckDB. Better for analytical queries; fits existing DuckDB-first infrastructure.
**Spider Chart:** D3.js custom component. Most control over axis scaling and overlay styling.
**Trend Charts:** Recharts. Simpler API, sufficient for line charts, easier to maintain.
**Normalization:** Against current active roster. Position-specific normalization is a future iteration.

---

## 7. File Structure

```
football-player-report/
+-- backend/
|   +-- main.py
|   +-- database.py
|   +-- tsa_scorer.py
|   +-- data_importer.py
|   +-- models.py
|   +-- routes/
|       +-- team.py
|       +-- athlete.py
+-- frontend/
|   +-- src/
|   |   +-- components/
|   |   |   +-- TeamSnapshot.tsx
|   |   |   +-- AthleteProfile.tsx
|   |   |   +-- SpiderChart.tsx
|   |   |   +-- TrendChart.tsx
|   |   |   +-- ComparisonPanel.tsx
|   |   +-- pages/
|   |   |   +-- TeamPage.tsx
|   |   |   +-- AthletePage.tsx
|   |   +-- App.tsx
|   +-- package.json
|   +-- tailwind.config.js
+-- data/
|   +-- raw/
|   +-- db/
+-- docs/
    +-- TECH_SPEC.md
    +-- DATA_SCHEMA.md
    +-- UI_WIREFRAMES.md
    +-- TSA_METHODOLOGY.md
    +-- README.md
```

---

## 8. Next Steps Before Development

1. Provide pipeline docs — share Claude.md files from CMJ, GPS, and body weight projects to finalize schema
2. Confirm FastAPI/Python backend aligns with current setup
3. Confirm DuckDB fits existing infrastructure
4. Initialize GitHub repo and add docs folder
5. Start Phase 1 with tsa_scorer.py and import scripts using Claude Code

---
*Living spec. Update as pipeline documentation is provided and implementation decisions are finalized.*
