# Football Player Performance Report
## UI Wireframes & Component Specification

**Version:** 1.0
**Created:** March 2026

---

## 1. Overview

Layout and component structure for both views of the application. These are
specification-level wireframes to guide Claude Code development, not visual designs.

---

## 2. Landing Page — Team Snapshot

### 2.1 Layout

```
+--------------------------------------------------------------+
| HEADER                                                       |
| Football Player Performance Report                           |
| Period: [Spring 2026]  |  Generated: [date]                  |
| Sources: CMJ [ok]  GPS [ok]  Body Weight [ok]                |
|                                  [Generate New Report v]     |
+--------------------------------------------------------------+
| FILTER BAR                                                   |
| Position: [All][QB][RB][WR][TE][OL][DL][LB][DB][ST][K/P]    |
| Sort: [TSA Rank v]    Search: [_____________________________] |
+--------------------------------------------------------------+
| ROSTER TABLE                                                 |
|                                                              |
| Rank | Name          | Pos | Yr | TSA  | CMJ T | GPS T | [*] |
| ----------------------------------------------------------------|
|  1   | Athlete Name  | WR  | SR | 68.4 |  72   |  65   | [G] |
|  2   | Athlete Name  | DB  | JR | 65.1 |  68   |  63   | [G] |
|  3   | Athlete Name  | RB  | SO | 62.8 |  60   |  66   | [A] |
| ...                                                          |
|                                                              |
| [G]=Green [A]=Amber [R]=Red RAG status                       |
| Athlete name is a clickable link -> athlete profile          |
+--------------------------------------------------------------+
```

### 2.2 RAG Status Logic

- Green: TSA composite in top 33% of active roster
- Amber: TSA composite in middle 34%
- Red: TSA composite in bottom 33%
- Use shape (circle/triangle/square) AND color for colorblind accessibility

### 2.3 Table Behavior

- Default sort: TSA rank ascending (rank 1 = highest TSA)
- Click any column header to re-sort
- Position filter updates table and recalculates visible rank
- Search filters by first name, last name, or jersey number
- Athlete name click navigates to /athlete/{id}

### 2.4 Generate New Report Dropdown

Opens a small inline form:
- Date range picker (start date / end date)
- Optional report label text field (e.g., "Spring 2026")
- [Run Report] button triggers POST /api/report/generate

---

## 3. Individual Athlete Profile — Drill-Down

### 3.1 Layout

```
+--------------------------------------------------------------+
| <- Back to Team    ATHLETE PROFILE                           |
+--------------------------------------------------------------+
| ATHLETE HEADER                                               |
| #22  Marcus Johnson  |  WR  |  Senior                        |
| Report: Spring 2026 Training Block                           |
| TSA: 68.4  [GREEN]                         [Compare v]       |
+--------------------------------------------------------------+
| PERFORMANCE METRICS TABLE                                    |
|                                                              |
| CMJ METRICS                                                  |
| Metric            | Raw   |  Z   |  T  | Team Avg | Pos Avg  |
| Jump Height (cm)  | 42.1  | +1.2 | 62  |   38.5   |   41.0   |
| Peak Power (W)    | 4820  | +0.8 | 58  |   4510   |   4740   |
| RSI               | 2.31  | +1.4 | 64  |   1.95   |   2.10   |
|                                                              |
| GPS METRICS                                                  |
| Metric            | Raw   |  Z   |  T  | Team Avg | Pos Avg  |
| Total Dist (m)    | 6,840 | +0.6 | 56  |   6200   |   6750   |
| Hi Speed Dist (m) | 1,240 | +1.1 | 61  |    980   |   1190   |
| Sprint Count      |  18.2 | +0.9 | 59  |   14.1   |   17.8   |
| Player Load       |   512 | +0.4 | 54  |    492   |    508   |
|                                                              |
| BODY WEIGHT                                                  |
| Metric            | Raw   |  Z   |  T  | Team Avg | Pos Avg  |
| Weight (kg)       | 84.2  | +0.2 | 52  |   82.1   |   83.7   |
| Change (period)   | +1.1  |  --  | --  |    --    |    --    |
+--------------------------------------------------------------+
| SPIDER CHART                   [Team Avg] [Position Avg]     |
|                                                              |
|         CMJ Height                                           |
|              *                                               |
|    BW ----- / \ ----- CMJ Power                             |
|            /   \                                             |
| GPS Load  *     * CMJ RSI    --- athlete                     |
|            \   /             ... team avg                    |
|   GPS End   * * GPS Speed                                    |
|                                                              |
+--------------------------------------------------------------+
| LONGITUDINAL TRENDS                                          |
|                                                              |
| CMJ Jump Height (cm)                                         |
| [line chart — spans full athlete tenure]                     |
| vertical lines mark training cycle boundaries                |
|                                                              |
| GPS Avg Total Distance per Session (m)                       |
| [line chart]                                                 |
|                                                              |
| Body Weight (kg)                                             |
| [line chart]                                                 |
|                                                              |
+--------------------------------------------------------------+
| COMPARISON PANEL  [collapsed by default, click to expand]    |
|                                                              |
| Compare with: [Search athlete name...] [+ Add]               |
|                                                              |
| [side-by-side metrics table for selected athletes]           |
| [spider chart overlay with color legend]                     |
+--------------------------------------------------------------+
```

### 3.2 Metrics Table Behavior

- Positive z-scores: light green cell background tint
- Negative z-scores: light red cell background tint
- Near-zero z-scores: no background tint
- Raw values display with appropriate units
- Partial data (athlete missing a domain): show available rows, flag missing with note

---

## 4. Component Inventory

### TeamSnapshot.tsx
Renders the roster table. Receives athletes[] array with TSA scores and RAG status.
Handles column sort, position filter, and name search. Athlete name routes to /athlete/{id}.

### AthleteProfile.tsx
Parent for the drill-down view. Fetches full athlete data on mount. Passes data down
to MetricsTable, SpiderChart, TrendChart, and ComparisonPanel.

### MetricsTable.tsx
Grouped metrics table with CMJ, GPS, and Body Weight sections. Props include a metrics
object containing raw, z-score, t-score, team average, and position average per metric.
Applies conditional cell background tinting based on z-score sign.

### SpiderChart.tsx
D3.js radar chart. Props: athleteScores (t-score per dimension), comparisonScores (optional
for team/position overlay), dimensions array. Toggle between team average and position average
overlay. Handles 5-8 axes. Responsive SVG sizing.

### TrendChart.tsx
Recharts LineChart wrapper. Props: data array (date, value pairs), metricLabel, unit string,
cycleBoundaries array. Handles gaps in data gracefully — breaks the line and shows tooltip
explanation. Training cycle boundaries rendered as ReferenceLine components.

### ComparisonPanel.tsx
Collapsible/expandable panel. Contains athlete search input querying /api/athletes/list.
Renders a side-by-side MetricsTable and a SpiderChart with multi-athlete overlay.
Color-codes each athlete line distinctly with a legend.

---

## 5. Routing

```
/                           Redirects to /team
/team                       Team Snapshot (landing page)
/team?position=WR           Team Snapshot filtered by position
/athlete/:id                Individual athlete profile
/athlete/:id?compare=:id2   Profile with comparison panel pre-opened
```

---

## 6. Color and Style Notes

- RAG colors (colorblind-safe): Green #2D9D78 / Amber #E8A838 / Red #D84B4B
- Always pair color with shape indicator for full accessibility compliance
- Spider chart athlete line: Baylor Gold #FFB81C
- Spider chart comparison lines: muted blues or grays with clear legend
- Positive z-score cells: rgba(45,157,120,0.12) background
- Negative z-score cells: rgba(216,75,75,0.12) background
- Overall aesthetic: clean, minimal, data-first — coaching tool, not a marketing deck

---

## 7. Responsive Targets

- Primary: desktop browser (coaching staff, sport science staff at desk)
- Secondary: tablet (iPad in weight room or on sideline)
- Mobile: low priority for v1 but layout should not break completely
- Spider chart and trend charts scale with container width using responsive SVG viewBox
