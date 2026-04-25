# BW Fallback: ForceDecks `raw_tests` Source

**Date:** 2026-04-24  
**Status:** Approved  
**Scope:** `src/data.py` only — no scorer, renderer, or template changes

---

## Problem

12 of 98 roster athletes have no match in `BodyWeightMaster.csv`. Their `weight_kg` is NaN in `merge_all()`, causing:
- BW domain score = NaN (domain dropped from TSA)
- Perch 1RM/BW normalization = NaN (Weight Room domain degraded)

All 12 athletes have `"Bodyweight in Kilograms"` recorded in ForceDecks `raw_tests`.

---

## Solution

Add two private helper functions to `src/data.py`. No public API changes.

### `_load_fd_bw(start_date, end_date) -> DataFrame[forcedecks_id, weight_kg]`

Queries `raw_tests` for `metric_name = 'Bodyweight in Kilograms'`. Takes the most recent value per athlete within `[start_date, end_date]`. Returns weight already in kg (ForceDecks stores natively in kg).

### `_load_bw_combined(start_date, end_date) -> DataFrame[forcedecks_id, name_normalized, weight_kg]`

1. Loads CSV BW via existing `load_bodyweight()` logic
2. Joins roster to attach `forcedecks_id` to CSV BW rows (by `name_normalized`)
3. Loads FD BW via `_load_fd_bw()`
4. Coalesces: CSV value wins; FD value fills NaN gaps
5. Returns one row per athlete with both join keys

---

## Changes to Existing Functions

### `merge_all()`
Replace `load_bodyweight(end_date)` call with `_load_bw_combined(start_date, end_date)`. Join on `name_normalized` as before — same column, same behavior for athletes in the CSV.

### `load_perch()` and `load_perch_history()`
After the existing CSV BW join via `name_normalized`, merge FD BW by `forcedecks_id`. The FD BW is in kg — convert to lbs (`/ 0.453592`) before filling NaN `weight_lbs` values, then proceed with the `1rm_lbs / weight_lbs` division step.

---

## Data Flow

```
CSV (BodyWeightMaster.csv)
  └─ name_normalized → weight_kg (CSV)
                                        ┐
                                        ├─ coalesce → weight_kg (final)
ForceDecks raw_tests                    ┘
  └─ forcedecks_id → weight_kg (FD, most recent in window)
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Athlete has no FD BW in date range | NaN — same as today, no regression |
| ForceDecks DB unreachable | `_load_fd_bw()` returns empty DataFrame; coalesce is no-op |
| Athlete IS in CSV | CSV value wins; FD value ignored |

---

## Testing

The existing 26-test suite covers `merge_all()` and the Perch loaders. No tests currently assert NaN for a specific athlete's BW, so no test changes needed.

Practical validation: run `generate_report.py` and confirm those 12 athletes have a BW domain score.

---

## Files Changed

| File | Change |
|------|--------|
| `src/data.py` | Add `_load_fd_bw()`, `_load_bw_combined()`; update `merge_all()`, `load_perch()`, `load_perch_history()` |
