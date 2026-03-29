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

    print("Scoring …")
    df_scored = score(df)
    rag_counts = df_scored["rag"].value_counts()
    print(f"  Green: {rag_counts.get('green', 0)}  Amber: {rag_counts.get('amber', 0)}  Red: {rag_counts.get('red', 0)}")

    print("Rendering HTML …")
    html = render(df_scored, args.label, args.start, args.end)

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
