"""Generate a self-contained HTML performance report.

Usage:
    python generate_report.py --start 2025-09-01 --end 2026-03-28 --label "Spring 2026"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR
from src.data import merge_all
from src.scorer import score
from src.renderer import render


def main():
    parser = argparse.ArgumentParser(description="Generate Football Performance Report")
    parser.add_argument("--start",  required=True,  help="Period start date (YYYY-MM-DD)")
    parser.add_argument("--end",    required=True,  help="Period end date   (YYYY-MM-DD)")
    parser.add_argument("--label",  default="Report", help="Report label (e.g. 'Spring 2026')")
    parser.add_argument("--output", default=None,   help="Override output file path")
    args = parser.parse_args()

    print(f"Loading data: {args.start} to {args.end} ...")
    df = merge_all(args.start, args.end)
    print(f"  Athletes loaded:  {len(df)}")
    print(f"  CMJ coverage:     {df['jump_height_cm'].notna().sum()}/{len(df)}")
    print(f"  GPS coverage:     {df['avg_hsd_m'].notna().sum()}/{len(df)}")
    print(f"  BW  coverage:     {df['weight_kg'].notna().sum()}/{len(df)}")
    print(f"  IMTP coverage:    {df['peak_force_bm'].notna().sum()}/{len(df)}")
    perch_col = 'bs_1rm_bw'
    print(f"  Perch coverage:   {df[perch_col].notna().sum()}/{len(df)}" if perch_col in df.columns else "  Perch coverage:   0 (no data)")

    print("Scoring ...")
    df_scored, pop_stats = score(df)
    rag_counts = df_scored["rag"].value_counts()
    print(f"  Green: {rag_counts.get('green', 0)}  Amber: {rag_counts.get('amber', 0)}  Red: {rag_counts.get('red', 0)}")

    print("Loading history ...")
    from src.data import load_cmj_history, load_imtp_history, load_bw_history, load_gps_history, load_perch_history
    cmj_hist   = load_cmj_history(args.start, args.end)
    imtp_hist  = load_imtp_history(args.start, args.end)
    bw_hist    = load_bw_history(args.end)
    gps_hist   = load_gps_history(args.start, args.end)
    perch_hist = load_perch_history(args.start, args.end)
    print(f"  CMJ tests:      {len(cmj_hist)}")
    print(f"  IMTP tests:     {len(imtp_hist)}")
    print(f"  BW entries:     {len(bw_hist)}")
    print(f"  GPS sessions:   {len(gps_hist)}")
    print(f"  Perch sessions: {len(perch_hist)}")

    print("Rendering HTML ...")
    html = render(df_scored, pop_stats, cmj_hist, gps_hist, bw_hist, imtp_hist, perch_hist,
                  args.label, args.start, args.end)

    if args.output:
        out_path = Path(args.output)
    else:
        safe_label = args.label.replace(" ", "_").replace("/", "-")
        out_path = OUTPUT_DIR / f"{safe_label}_{args.end}.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    main()
