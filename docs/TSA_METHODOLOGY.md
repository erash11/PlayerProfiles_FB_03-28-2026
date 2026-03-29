# Total Score of Athleticism (TSA)
## Scoring Methodology

**Version:** 1.0
**Created:** March 2026

**References:**
- Turner, A. et al. (2019). Total Score of Athleticism: Holistic Athlete Profiling.
  Strength & Conditioning Journal, 41(6), 1-13.
- Ward, P. Total Score of Athleticism — R Markdown & R Shiny.
  Optimum Sports Performance Blog. optimumsportsperformance.com
- Whitacre, C. et al. (2025). Analysis of Z-Score and TSA on drafted and undrafted
  players from the NFL Scouting Combine. Scientific Reports.

---

## 1. What is TSA?

The Total Score of Athleticism (TSA) is a single composite number that summarizes an
athlete's overall athleticism across multiple performance domains. Rather than reporting
isolated metrics, TSA combines normalized scores from a testing battery into one holistic
value that can be used to rank athletes and track development over time.

The core principle: an athlete who is moderately strong across all dimensions is often more
valuable than one who excels in one area but is deficient in others. TSA rewards balance.

---

## 2. Core Methodology

TSA is computed in four steps.

---

### Step 1 — Collect Raw Scores

Pull the most recent or period-averaged value for each metric in the reporting window
for every athlete in the population.

Metric domains for this application:

**CMJ**
- Jump Height (cm)
- Peak Power (W)
- Reactive Strength Index (RSI)

**GPS**
- High Speed Distance per session (m)
- Sprint Count per session
- Player Load per session
- Max Velocity (m/s)

**Body Weight**
- Weight (kg) relative to position norm or change from period baseline

---

### Step 2 — Compute Z-Scores

For each metric:

```
z = (x - mean) / std_dev
```

Where:
- x       = individual athlete's value
- mean    = population mean for that metric
- std_dev = population standard deviation for that metric

A z-score of 0 = exactly average.
A z-score of +1 = one standard deviation above average.
A z-score of -1 = one standard deviation below average.

**Population definition:** The active roster included in the current report run.

**Sign flipping for time-based metrics:**
For metrics where lower = better (e.g., 40-yard dash time), flip the sign after
computing the z-score so that "better performance" always corresponds to a higher score:

```
z_adjusted = z * -1
```

---

### Step 3 — Convert Z-Scores to T-Scores

T-scores rescale z-scores to a 0-100 range centered at 50, which is more intuitive
for coaches and avoids negative numbers.

```
t = (z * 10) + 50
```

Reference table:

| Z-Score | T-Score | Interpretation        |
|---------|---------|-----------------------|
|   +2.0  |   70    | 2 SDs above average   |
|   +1.5  |   65    | 1.5 SDs above average |
|   +1.0  |   60    | 1 SD above average    |
|    0.0  |   50    | Exactly average       |
|   -1.0  |   40    | 1 SD below average    |
|   -1.5  |   35    | 1.5 SDs below average |
|   -2.0  |   30    | 2 SDs below average   |

Cap t-scores at 0 (floor) and 100 (ceiling) to handle extreme outliers.

---

### Step 4 — Compute TSA Composite

Use domain-level compositing (recommended) to prevent data-rich domains from
dominating the composite simply because they have more metrics.

```
CMJ Domain T   = mean(jump_height_t, peak_power_t, rsi_t)
GPS Domain T   = mean(high_speed_dist_t, sprint_count_t, player_load_t, max_vel_t)
BW Domain T    = mean(bodyweight_t)

TSA Composite  = mean(CMJ Domain T, GPS Domain T, BW Domain T)
```

This gives each domain equal weight regardless of how many individual metrics
it contributes.

---

## 3. RAG Status Assignment

After computing TSA composites for the full roster, assign status based on rank thirds:

```
Sort all athletes by TSA composite descending.
Top 33%    -> Green  (high composite athleticism for this roster)
Middle 34% -> Amber  (average composite athleticism)
Bottom 33% -> Red    (below average composite athleticism)
```

Thresholds are calculated fresh for each report run relative to the included population.
RAG status is roster-relative, not an absolute scale.

---

## 4. Example Calculation

Five athletes, two metrics (Jump Height and Player Load):

Population stats:
- Jump Height: mean = 39.6 cm, SD = 3.97 cm
- Player Load:  mean = 509.0,   SD = 23.0

| Athlete | Jump (cm) | Jump Z | Jump T | Player Load | PL Z  | PL T | TSA Avg | Rank |
|---------|-----------|--------|--------|-------------|-------|------|---------|------|
| A       | 45.0      | +1.36  | 63.6   | 480         | -1.26 | 37.4 | 50.5    | 3    |
| B       | 42.0      | +0.61  | 56.1   | 510         | +0.04 | 50.4 | 53.3    | 2    |
| C       | 40.0      | +0.10  | 51.0   | 495         | -0.61 | 43.9 | 47.5    | 4    |
| D       | 38.0      | -0.40  | 46.0   | 540         | +1.35 | 63.5 | 54.8    | 1    |
| E       | 33.0      | -1.66  | 33.4   | 520         | +0.48 | 54.8 | 44.1    | 5    |

RAG assignment (5 athletes: top 2 = Green, middle 1 = Amber, bottom 2 = Red):
- D (54.8) -> Green
- B (53.3) -> Green
- A (50.5) -> Amber
- C (47.5) -> Red
- E (44.1) -> Red

Note: Athlete D ranked first despite low CMJ because their GPS workload was strong.
This is the rounded-athlete principle in action.

---

## 5. Python Implementation

### tsa_scorer.py

```python
import pandas as pd
import numpy as np


def compute_z_score(series: pd.Series) -> pd.Series:
    """Compute z-score for a metric column."""
    return (series - series.mean()) / series.std()


def compute_t_score(z: pd.Series) -> pd.Series:
    """Convert z-scores to t-scores, capped at 0-100."""
    return ((z * 10) + 50).clip(0, 100)


def assign_rag(tsa: pd.Series) -> pd.Series:
    """Assign Green/Amber/Red based on rank thirds."""
    bottom_threshold = tsa.quantile(1 / 3)
    top_threshold = tsa.quantile(2 / 3)
    conditions = [tsa >= top_threshold, tsa >= bottom_threshold]
    choices = ['green', 'amber']
    return pd.Series(
        np.select(conditions, choices, default='red'),
        index=tsa.index
    )


def compute_tsa(
    df: pd.DataFrame,
    metrics: list,
    invert: list = [],
    domain_map: dict = None
) -> pd.DataFrame:
    """
    Compute TSA composite scores for a roster.

    Parameters
    ----------
    df         : DataFrame with athlete_id and metric columns
    metrics    : list of column names to include
    invert     : metric names where lower = better (sign will be flipped)
    domain_map : dict mapping domain names to lists of metric column names
                 e.g., {'cmj': ['jump_height', 'peak_power', 'rsi'],
                        'gps': ['high_speed_dist', 'sprint_count', 'player_load'],
                        'bw':  ['weight_kg']}
                 If None, all metrics are averaged equally.

    Returns
    -------
    DataFrame with z-scores, t-scores, domain t-scores, TSA composite, rank, RAG
    """
    result = df[['athlete_id']].copy()
    t_cols = []

    for metric in metrics:
        z = compute_z_score(df[metric])
        if metric in invert:
            z = z * -1
        t = compute_t_score(z)
        result[f'{metric}_z'] = z
        result[f'{metric}_t'] = t
        t_cols.append(f'{metric}_t')

    if domain_map:
        domain_t_cols = []
        for domain, domain_metrics in domain_map.items():
            domain_t_col = f'{domain}_domain_t'
            available = [f'{m}_t' for m in domain_metrics if f'{m}_t' in result.columns]
            if available:
                result[domain_t_col] = result[available].mean(axis=1)
                domain_t_cols.append(domain_t_col)
        result['tsa_composite'] = result[domain_t_cols].mean(axis=1)
    else:
        result['tsa_composite'] = result[t_cols].mean(axis=1)

    result['tsa_rank'] = result['tsa_composite'].rank(ascending=False).astype(int)
    result['rag_status'] = assign_rag(result['tsa_composite'])

    return result
```

### Example usage

```python
import pandas as pd
from tsa_scorer import compute_tsa

df = pd.read_csv('data/processed/roster_metrics.csv')

domain_map = {
    'cmj': ['jump_height_cm', 'peak_power_w', 'rsi'],
    'gps': ['high_speed_dist_m', 'sprint_count', 'player_load'],
    'bw':  ['weight_kg']
}

results = compute_tsa(
    df=df,
    metrics=['jump_height_cm', 'peak_power_w', 'rsi',
             'high_speed_dist_m', 'sprint_count', 'player_load',
             'weight_kg'],
    invert=[],       # add time-based metrics here if needed
    domain_map=domain_map
)

print(results[['athlete_id', 'tsa_composite', 'tsa_rank', 'rag_status']])
```

---

## 6. Spider Chart Axis Selection

Recommended axes using t-score values (0-100 scale):

1. CMJ Jump Height
2. CMJ Peak Power
3. CMJ Reactive Strength Index
4. GPS High Speed Distance (avg per session)
5. GPS Sprint Count (avg per session)
6. GPS Player Load (avg per session)
7. Body Weight (relative to position norm)

This 7-axis configuration covers power, reactivity, speed output, endurance demand,
total workload, and body composition — a reasonable view of holistic athleticism for
American football.

Axes are configurable in the UI to allow position-specific emphasis in future iterations.

---

## 7. Important Considerations

**Small populations:** With fewer than ~15-20 athletes in the population, z-scores
become less statistically stable. T-scores at the extremes should be interpreted with
appropriate caution. The methodology still applies — just note the sample size when
presenting results.

**Missing data:** If an athlete has CMJ data but no GPS data, two approaches are valid:
(a) exclude them from full TSA and show a partial score, or (b) compute TSA using only
available domains. The application should clearly flag partial scores rather than silently
dropping athletes or presenting incomplete composites as full ones.

**Temporal context:** TSA is always relative to the population in the current report run.
A t-score of 60 in Spring means something different from a 60 in Fall if the roster
composition changes. Do not compare raw TSA values across report periods. Compare ranks
and trends instead.

**Longitudinal interpretation:** Track TSA rank and domain t-scores over time per athlete
to understand development trajectory. A rising trend is more meaningful than any single
snapshot score.

**Position norms:** The current implementation normalizes against the full roster.
A future enhancement would normalize within position groups (linemen vs. skill positions)
particularly for body weight, where a 135 kg OL is not meaningfully comparable to an 85 kg DB.
This is a Phase 2+ consideration.
