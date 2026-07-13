#!/usr/bin/env python3
"""
Validate ellipse-derived bolt heights vs. optimized bolt heights.

Computes bolt heights from the ideal elliptic paraboloid surface
(z = A*x² + B*z² + C*x*z) and compares with TPS-optimized bolt heights.

Usage:
    python scripts/validate_ellipse_vs_optimized.py [--output-dir <dir>]
"""
import numpy as np
import argparse
import json
import os
import sys

# ── Mirror geometry ──────────────────────────────────────────────────
W = 12.84   # width (m)
L = 9.45    # length (m)
NB_X = 7    # bolts in x
NB_Z = 5    # bolts in z
MARGIN = 0.08
GRID = 32

# ── Bolt positions (matches pipeline.cpp:1035-1044) ───────────────────
def bolt_positions():
    """Return array of bolt positions [35, 2] = (x, z) in row-major order."""
    positions = []
    for j in range(NB_Z):
        v = MARGIN + (1.0 - 2.0 * MARGIN) * j / (NB_Z - 1)
        for i in range(NB_X):
            u = MARGIN + (1.0 - 2.0 * MARGIN) * i / (NB_X - 1)
            x = (u - 0.5) * W
            z = (v - 0.5) * L
            positions.append([x, z])
    return np.array(positions)


def ellipse_surface(x, z, A, B, C):
    """Elliptic paraboloid: height = A*x² + B*z² + C*x*z"""
    return A * x**2 + B * z**2 + C * x * z


def main():
    parser = argparse.ArgumentParser(description="Validate ellipse vs optimized bolt heights")
    parser.add_argument("--ellipse-file", default="data/ellipse_north.txt",
                        help="Ellipse config file (default: data/ellipse_north.txt)")
    parser.add_argument("--opt-bolts", default="results_vsm_mnvn_300iter/North_300m_BEST_bolts.txt",
                        help="Optimized bolt file")
    parser.add_argument("--output-dir", default="validation_ellipse_vs_opt",
                        help="Output directory for bolt files and comparison data")
    parser.add_argument("--grid", type=int, default=GRID, help="Surface grid resolution")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # ── Read ellipse ABC ──────────────────────────────────────────────
    A, B, C = None, None, None
    with open(args.ellipse_file, encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                parts = line.split()
                name, a_val, b_val, c_val = parts[0], float(parts[4]), float(parts[5]), float(parts[6])
                if 'North' in name and '300' in name:  # Will match "North"
                    A, B, C = float(parts[4]), float(parts[5]), float(parts[6])
                    break
        if A is None:
            # Use first line
            parts = open(args.ellipse_file, encoding='utf-8', errors='ignore').readline().split()
            A, B, C = float(parts[4]), float(parts[5]), float(parts[6])

    print(f"Ellipse parameters: A={A:.6e}, B={B:.6e}, C={C:.6e}")

    # ── Compute bolt heights from ellipse surface ─────────────────────
    pos = bolt_positions()
    h_ellipse = ellipse_surface(pos[:, 0], pos[:, 1], A, B, C)

    print(f"\nEllipse bolt heights (35 bolts):")
    print(f"  min={h_ellipse.min():.4f} mm, max={h_ellipse.max():.4f} mm")
    print(f"  PV={h_ellipse.max()-h_ellipse.min():.4f} mm")

    # ── Read optimized bolt heights ───────────────────────────────────
    h_opt = None
    try:
        vals = []
        with open(args.opt_bolts, encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    vals.append(float(parts[1]))
                else:
                    vals.append(float(parts[0]))
        if len(vals) == 35:
            h_opt = np.array(vals)
            print(f"\nOptimized bolt heights:")
            print(f"  min={h_opt.min():.4f} mm, max={h_opt.max():.4f} mm")
            print(f"  PV={h_opt.max()-h_opt.min():.4f} mm")
        else:
            print(f"WARNING: {args.opt_bolts} has {len(vals)} values (expected 35)")
    except FileNotFoundError:
        print(f"WARNING: Optimized bolt file not found: {args.opt_bolts}")

    # ── Write ellipse bolt height files ───────────────────────────────
    # Simple format: one value per line
    bolt_txt = os.path.join(args.output_dir, "ellipse_bolts.txt")
    with open(bolt_txt, 'w') as f:
        f.write("# Ellipse-derived bolt heights for North 300m\n")
        f.write(f"# A={A:.6e} B={B:.6e} C={C:.6e}\n")
        for i, h in enumerate(h_ellipse):
            f.write(f"{i} {h:.8f}\n")
    print(f"\nSaved ellipse bolts: {bolt_txt}")

    # Raw format (just values, for simpler parsing)
    bolt_raw = os.path.join(args.output_dir, "ellipse_bolts_raw.txt")
    with open(bolt_raw, 'w') as f:
        for h in h_ellipse:
            f.write(f"{h:.8f}\n")

    # Also save optimized bolts in same directory for comparison
    if h_opt is not None:
        opt_txt = os.path.join(args.output_dir, "optimized_bolts.txt")
        with open(opt_txt, 'w') as f:
            f.write("# TPS-optimized bolt heights for North 300m\n")
            for i, h in enumerate(h_opt):
                f.write(f"{i} {h:.8f}\n")

    # ── Compute full ellipse surface on 32×32 grid ────────────────────
    print(f"\n── Surface comparison ({args.grid}×{args.grid} grid) ──")

    # Grid points (matching bolt_forward.slang: u = i/(GS-1), v = j/(GS-1))
    u_vals = np.linspace(0, 1, args.grid)
    v_vals = np.linspace(0, 1, args.grid)
    x_grid = (u_vals - 0.5) * W
    z_grid = (v_vals - 0.5) * L
    X, Z = np.meshgrid(x_grid, z_grid, indexing='ij')  # [grid, grid]
    ellipse_grid = ellipse_surface(X, Z, A, B, C)       # [grid, grid]

    print(f"  Ellipse surface PV: {ellipse_grid.max()-ellipse_grid.min():.4f} mm")
    print(f"  Ellipse surface RMS: {np.std(ellipse_grid):.4f} mm")

    # ── Compare bolt heights ─────────────────────────────────────────
    if h_opt is not None:
        # Align: optimize removes piston (max → 0, then -0.5mm). Also
        # ellipse bolts may have different overall piston.
        # For fair shape comparison, subtract mean.
        h_ellipse_dm = h_ellipse - h_ellipse.mean()
        h_opt_dm = h_opt - h_opt.mean()

        rms_diff = np.sqrt(np.mean((h_ellipse_dm - h_opt_dm)**2))
        corr = np.corrcoef(h_ellipse, h_opt)[0, 1]
        print(f"\n── Bolt height comparison (35 bolts) ──")
        print(f"  RMS diff (de-meaned): {rms_diff:.4f} mm")
        print(f"  Correlation: {corr:.6f}")

        # Print bolt-by-bolt comparison
        print(f"\n  Bolt-by-bolt (ellipse vs optimized, mm):")
        print(f"  {'Idx':>4s} {'X(m)':>8s} {'Z(m)':>8s} {'Ellipse':>10s} {'Optimized':>10s} {'Diff':>10s}")
        for i in range(35):
            diff = h_ellipse[i] - h_opt[i]
            print(f"  {i:4d} {pos[i,0]:8.3f} {pos[i,1]:8.3f} "
                  f"{h_ellipse[i]:10.4f} {h_opt[i]:10.4f} {diff:10.4f}")

    # ── Save surface grid for external comparison ─────────────────────
    surf_path = os.path.join(args.output_dir, "ellipse_surface_32x32.txt")
    with open(surf_path, 'w') as f:
        f.write(f"# Ellipse surface: A={A:.6e} B={B:.6e} C={C:.6e}\n")
        f.write(f"# x z height\n")
        for i in range(args.grid):
            for j in range(args.grid):
                f.write(f"{X[i,j]:.6f} {Z[i,j]:.6f} {ellipse_grid[i,j]:.8f}\n")
    print(f"\nSaved surface grid: {surf_path}")

    # ── Save metadata ────────────────────────────────────────────────
    meta = {
        "ellipse_file": args.ellipse_file,
        "A": float(A), "B": float(B), "C": float(C),
        "ellipse_bolt_PV_mm": float(h_ellipse.max() - h_ellipse.min()),
        "ellipse_surface_PV_mm": float(ellipse_grid.max() - ellipse_grid.min()),
        "ellipse_surface_RMS_mm": float(np.std(ellipse_grid)),
    }
    if h_opt is not None:
        meta["opt_bolt_PV_mm"] = float(h_opt.max() - h_opt.min())
        meta["bolt_rms_diff_mm"] = float(rms_diff)
        meta["bolt_correlation"] = float(corr)

    with open(os.path.join(args.output_dir, "metadata.json"), 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"Saved metadata: {os.path.join(args.output_dir, 'metadata.json')}")

    print(f"\n── Next steps ──")
    print(f"  # Run flux dump with ellipse bolts:")
    print(f"  ./build/src/Release/bezier_opt.exe --dump-flux --bolt-file {bolt_txt} "
          f"--config configs/validate_flux.json")
    if h_opt is not None:
        print(f"  # Run flux dump with optimized bolts:")
        print(f"  ./build/src/Release/bezier_opt.exe --dump-flux --bolt-file {opt_txt} "
              f"--config configs/validate_flux.json")


if __name__ == "__main__":
    main()
