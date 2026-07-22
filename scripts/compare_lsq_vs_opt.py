#!/usr/bin/env python3
"""
Parse evaluation outputs and produce LS-Fit vs Optimized S95 comparison.

Reads S95 values from:
  - LS eval output (results_lsq_eval)
  - Opt eval output (results_opt_eval)
  - Original optimization summaries (results_Field)
Produces a comparison table and optional CSV.
"""

import os
import re
import sys
import numpy as np
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent


def parse_eval_output(text):
    """Parse eval stdout to extract per-mirror S95 values.
    Returns dict: name -> s95_m2 (float)
    """
    results = {}
    # Pattern: "Optimizing (BOLT mode, 35 bolts): North (dist=150.0m)" followed by S95
    current_mirror = None
    current_dist = None
    for line in text.split('\n'):
        m = re.search(r'Optimizing.*bolts\):\s*(\w+)\s*\(dist=([\d.]+)m\)', line)
        if m:
            current_mirror = m.group(1)
            current_dist = float(m.group(2))
            continue
        # Match "Done. Best S95: 38.7852"
        m = re.search(r'Best S95:\s*([\d.]+)', line)
        if m and current_mirror:
            s95 = float(m.group(1))
            name = f"{current_mirror}_{int(current_dist)}m"
            results[name] = s95
            current_mirror = None
    return results


def parse_opt_summary(summary_dir):
    """Parse optimization_summary.csv files from results_Field.
    Returns dict: name -> {init_s95, best_s95, reduction_pct}
    """
    results = {}
    for csv_path in sorted(Path(summary_dir).glob('results_*/optimization_summary.csv')):
        with open(csv_path) as f:
            header = f.readline().strip()
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) >= 4:
                    position = parts[0]
                    distance = float(parts[1])
                    init_s95 = float(parts[2])
                    best_s95 = float(parts[3])
                    reduction = float(parts[4]) if len(parts) > 4 else 0.0
                    name = f"{position}_{int(distance)}m"
                    results[name] = {
                        'init_s95': init_s95,
                        'best_s95': best_s95,
                        'reduction_pct': reduction
                    }
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Compare LS-fit vs Optimized S95')
    parser.add_argument('--lsq-eval-output', default=None,
                        help='Path to LS eval stdout text file')
    parser.add_argument('--opt-eval-output', default=None,
                        help='Path to Opt eval stdout text file')
    parser.add_argument('--opt-summary-dir', default=str(ROOT / 'results_Field'),
                        help='Directory with optimization_summary.csv files')
    parser.add_argument('--output-csv', default=None,
                        help='Output CSV path for comparison table')
    parser.add_argument('--lsq-s95', action='append', default=[],
                        help='Manual LS S95 entries: name=value')
    parser.add_argument('--opt-s95', action='append', default=[],
                        help='Manual Opt S95 entries: name=value')
    args = parser.parse_args()

    # Load LS S95 from eval output or manual entries
    lsq_s95 = {}
    opt_s95_334 = {}
    if args.lsq_eval_output:
        with open(args.lsq_eval_output) as f:
            lsq_s95 = parse_eval_output(f.read())
        print(f"Loaded {len(lsq_s95)} LSQ S95 values from {args.lsq_eval_output}")

    for entry in args.lsq_s95:
        name, val = entry.split('=')
        lsq_s95[name] = float(val)

    for entry in args.opt_s95:
        name, val = entry.split('=')
        opt_s95_334[name] = float(val)

    # Load Opt S95 from eval output (334-dir) or summary (36-dir)
    if args.opt_eval_output:
        with open(args.opt_eval_output) as f:
            opt_s95_334 = parse_eval_output(f.read())
        print(f"Loaded {len(opt_s95_334)} Opt S95 (334-dir) values from {args.opt_eval_output}")

    opt_summary = parse_opt_summary(args.opt_summary_dir)
    print(f"Loaded {len(opt_summary)} Opt summary entries (36-dir) from {args.opt_summary_dir}")

    # Build comparison table
    all_names = sorted(set(list(lsq_s95.keys()) + list(opt_summary.keys())))

    print(f"\n{'='*100}")
    print(f"  LS-Fit vs Optimized S95 Comparison (334-dir annual average)")
    print(f"{'='*100}")
    print(f"  {'Mirror':<18s} {'LS-Fit S95':>10s} {'Opt S95(334)':>12s} "
          f"{'Opt S95(36)':>12s} {'Delta(LS-Opt)':>12s} {'LS/Opt':>8s} "
          f"{'Opt Reduc%':>10s}")
    print(f"  {'-'*95}")

    rows = []
    for name in all_names:
        ls = lsq_s95.get(name, None)
        opt334 = opt_s95_334.get(name, None) if opt_s95_334 else None
        opt_sum = opt_summary.get(name, {})
        opt36 = opt_sum.get('best_s95', None) if opt_sum else None
        reduc = opt_sum.get('reduction_pct', None) if opt_sum else None

        # Use opt334 if available, else opt36
        opt_display = opt334 if opt334 else opt36
        opt_label = "(334d)" if opt334 else "(36d)"

        if ls and opt_display:
            delta = ls - opt_display
            ratio = ls / opt_display
            print(f"  {name:<18s} {ls:9.2f} m2 {opt_display:11.2f} m2 "
                  f"{opt36 if opt36 else 'N/A':>12} {delta:+11.2f} m2 "
                  f"{ratio:7.3f}x {reduc if reduc else 'N/A':>9}")
            rows.append({
                'name': name, 'lsq_s95_334d': ls, 'opt_s95_334d': opt334,
                'opt_s95_36d': opt36, 'delta': delta, 'ratio': ratio,
                'opt_reduction_pct': reduc
            })
        elif ls:
            print(f"  {name:<18s} {ls:9.2f} m2 {'N/A':>12s} "
                  f"{opt36 if opt36 else 'N/A':>12} {'N/A':>12} "
                  f"{'N/A':>8s} {'N/A':>10s}")

    print(f"{'='*100}")

    # Summary stats
    if rows:
        deltas = [r['delta'] for r in rows if r['delta'] is not None]
        ratios = [r['ratio'] for r in rows if r['ratio'] is not None]
        if deltas:
            print(f"\n  LS-Fit vs Opt Delta: mean={np.mean(deltas):+.1f} m2, "
                  f"min={np.min(deltas):+.1f}, max={np.max(deltas):+.1f} m2")
        if ratios:
            print(f"  LS-Fit / Opt Ratio: mean={np.mean(ratios):.3f}x, "
                  f"min={np.min(ratios):.3f}x, max={np.max(ratios):.3f}x")

    # Optional CSV output
    if args.output_csv and rows:
        import csv
        with open(args.output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n  Comparison saved to: {args.output_csv}")


if __name__ == '__main__':
    main()
