#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare optimization results across different sundir training sets.
"""

import numpy as np
import sys
from pathlib import Path

RESULT_DIRS = {
    "36dir": "results_sundir_cmp_36dir",
    "110dir": "results_sundir_cmp_110dir",
    "334dir": "results_sundir_cmp_334dir",
}

def load_history(result_dir: str) -> dict:
    """Load optimization history CSV."""
    # Find the history file
    history_files = list(Path(result_dir).glob("*_history.csv"))
    if not history_files:
        print(f"WARNING: No history CSV found in {result_dir}")
        return None
    data = np.loadtxt(history_files[0], delimiter=",", skiprows=1)
    return {
        "iteration": data[:, 0].astype(int),
        "loss": data[:, 1],
        "s95": data[:, 2],
    }

def load_bolt_strokes(result_dir: str) -> np.ndarray | None:
    """Load final bolt stroke heights."""
    stroke_files = list(Path(result_dir).glob("*_STROKE_bolts.txt"))
    if not stroke_files:
        # Try BEST_bolts
        best_files = list(Path(result_dir).glob("*_BEST_bolts.txt"))
        if not best_files:
            print(f"WARNING: No bolt file found in {result_dir}")
            return None
        # Parse BEST_bolts format: idx h_pipe h_stroke
        strokes = []
        with open(best_files[0]) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.strip().split()
                if len(parts) >= 3:
                    strokes.append(float(parts[2]))  # h_stroke column
        return np.array(strokes)
    else:
        strokes = []
        with open(stroke_files[0]) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                strokes.append(float(line.strip()))
        return np.array(strokes)

def load_summary(result_dir: str) -> dict | None:
    """Load optimization summary CSV."""
    summary_path = Path(result_dir) / "optimization_summary.csv"
    if not summary_path.exists():
        return None
    with open(summary_path) as f:
        header = f.readline().strip()
        values = f.readline().strip().split(",")
    return {
        "init_s95": float(values[2]),
        "best_s95": float(values[3]),
        "reduction": float(values[4]),
    }

def main():
    print("=" * 70)
    print("Sundir Sampling Comparison: 36dir vs 110dir (paper) vs 334dir (balanced)")
    print("=" * 70)

    histories = {}
    strokes = {}
    summaries = {}

    for label, dirname in RESULT_DIRS.items():
        print(f"\n--- {label} ({dirname}) ---")
        h = load_history(dirname)
        s = load_bolt_strokes(dirname)
        sm = load_summary(dirname)

        if h is None or s is None:
            print(f"  SKIPPED: missing data")
            continue

        histories[label] = h
        strokes[label] = s
        summaries[label] = sm

        print(f"  Initial S95 (train): {h['s95'][0]:.4f} m²")
        print(f"  Best S95 (train):    {h['s95'][-1]:.4f} m²")
        print(f"  Improvement:         {h['s95'][0] - h['s95'][-1]:.4f} m² ({(1 - h['s95'][-1]/h['s95'][0])*100:.1f}%)")
        if sm:
            print(f"  Summary init/best:   {sm['init_s95']:.4f} / {sm['best_s95']:.4f} m²")
        print(f"  Max bolt stroke:     {s.max()*1000:.1f} mm")
        print(f"  RMS bolt stroke:     {np.sqrt(np.mean(s**2))*1000:.1f} mm")

    # Cross-comparison of bolt strokes
    print("\n" + "=" * 70)
    print("Cross-Comparison: Bolt Stroke Patterns")
    print("=" * 70)

    labels = list(strokes.keys())
    for i, li in enumerate(labels):
        for j, lj in enumerate(labels):
            if i >= j:
                continue
        si, sj = strokes[li], strokes[lj]
        rms_diff = np.sqrt(np.mean((si - sj)**2))
        corr = np.corrcoef(si, sj)[0, 1]
        max_diff = np.max(np.abs(si - sj))
        print(f"  {li} vs {lj}: RMS diff={rms_diff*1000:.3f} mm, corr={corr:.6f}, max diff={max_diff*1000:.3f} mm")

    # S95 convergence comparison
    print("\n" + "=" * 70)
    print("Cross-Comparison: Training S95 Convergence")
    print("=" * 70)

    for label, h in histories.items():
        s95_first = h['s95'][0]
        s95_final = h['s95'][-1]
        # Print key iterations
        checkpoints = [0, 9, 19, 49, 99, 149, 199]
        print(f"\n  {label}:")
        for cp in checkpoints:
            if cp < len(h['s95']):
                print(f"    iter {cp:3d}: S95={h['s95'][cp]:.4f} m²")

    print("\nDone.")


if __name__ == "__main__":
    main()
