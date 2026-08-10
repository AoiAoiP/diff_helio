#!/usr/bin/env python3
"""
Least-squares fit of TPS bolt heights to ideal elliptic mirror surfaces.

For each mirror in ellipse.txt, computes the 35 bolt heights h_b that minimize
  || Σ h_b * φ_b(x,z) - s_target(x,z) ||²

where s_target is the ideal elliptic sag in pipeline convention (+Y away from receiver):
  s_target(x,z) = -0.5 * (cx*x² + cy*z² + 2*cxy*x*z)

Outputs bolt init files ready for the C++ pipeline (--bolt-file).
"""

import os
import sys
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PROXY = Path(os.environ.get("BEZIER_PROXY_DIR", str(ROOT / 'data_proxy')))

# Plate dimensions (matching generate_proxy_model.py and shader conventions;
# env override for literature replication runs)
W = float(os.environ.get("BEZIER_PLATE_W", "12.84"))
L = float(os.environ.get("BEZIER_PLATE_L", "9.45"))
GS = 32     # grid size
NB = 35     # number of bolts (7x5)
BOLTS_X = 7
BOLTS_Z = 5
MARGIN = 0.08


def compute_grid():
    """Pixel-centered grid in plate-local coordinates (matching shader gridToPlate)."""
    u = (np.arange(GS) + 0.5) / GS
    x = (u - 0.5) * W
    z = (u - 0.5) * L
    Xg, Zg = np.meshgrid(x, z)  # default 'xy': X-fast, Z-slow
    return x, z, Xg, Zg


def load_influence_phi():
    """Load influence_phi.bin: (NB, GS*GS) float32, row-major over grid (z outer, x inner)."""
    path = DATA_PROXY / 'influence_phi.bin'
    data = np.fromfile(path, dtype=np.float32)
    n_total = NB * GS * GS
    assert len(data) == n_total, f"Expected {n_total} floats, got {len(data)}"
    phi = data.reshape(NB, GS * GS)
    return phi


def parse_ellipse_file(path):
    """
    Parse ellipse.txt.
    Format per line: direction x y z cx cy cxy  (7 fields, no index column)
    Returns list of dicts.
    """
    mirrors = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            direction = parts[0]
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            cx, cy, cxy = float(parts[4]), float(parts[5]), float(parts[6])
            distance = np.sqrt(x*x + y*y + z*z)
            name = f"{direction}_{int(distance)}m"
            mirrors.append({
                'name': name,
                'direction': direction,
                'position': np.array([x, y, z]),
                'cx': cx,
                'cy': cy,
                'cxy': cxy,
                'distance': distance,
            })
    return mirrors


def compute_target_sag(cx, cy, cxy, Xg, Zg):
    """
    Compute ideal elliptic sag (matching src/input.h convention):
      sag(x,z) = cx*x^2 + cy*z^2 + cxy*x*z
    This is the sag in plate-local coordinates (+Y away from receiver).
    """
    sag = cx * Xg**2 + cy * Zg**2 + cxy * Xg * Zg
    return sag.ravel()  # (GS*GS,) flat, row-major


def lsq_fit_bolts(phi, s_target):
    """
    Solve min_h || phi^T @ h - s_target ||²
    phi: (NB, GS*GS) — each row is one bolt's influence at all grid points
    s_target: (GS*GS,) — target sag
    Returns h: (NB,) — bolt heights in pipeline convention
    """
    A = phi.T  # (GS*GS, NB)
    h, residuals, rank, sv = np.linalg.lstsq(A, s_target, rcond=None)
    return h


def save_bolt_init_file(h, output_path, mirror_name):
    """Save bolt heights as a bolt init file for C++ pipeline (--bolt-file)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(f"# LSQ elliptic fit bolt heights — PIPELINE convention (+Y away from receiver)\n")
        f.write(f"# Mirror: {mirror_name}\n")
        f.write(f"# idx  h_pipe(m)\n")
        for i, hi in enumerate(h):
            f.write(f"{i} {hi:.8f}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='LSQ elliptic fit for TPS bolt heights')
    parser.add_argument('--ellipse-file', default=str(ROOT / 'data' / 'ellipse.txt'),
                        help='Path to ellipse.txt')
    parser.add_argument('--output-dir', default=str(ROOT / 'data' / 'init'),
                        help='Output directory for bolt init files')
    parser.add_argument('--summary-csv', default=None,
                        help='Optional summary CSV output path')
    args = parser.parse_args()

    # Load influence functions
    print("Loading TPS influence functions...")
    phi = load_influence_phi()
    print(f"  influence_phi: {phi.shape} (NB={NB}, n_grid={GS*GS})")

    # Grid coordinates
    x_grid, z_grid, Xg, Zg = compute_grid()
    print(f"  Grid: {GS}x{GS}, x=[{x_grid[0]:.2f}, {x_grid[-1]:.2f}]m, "
          f"z=[{z_grid[0]:.2f}, {z_grid[-1]:.2f}]m")

    # Parse ellipse file
    mirrors = parse_ellipse_file(args.ellipse_file)
    print(f"\nLoaded {len(mirrors)} mirror configurations from {args.ellipse_file}")

    # Process each mirror
    results = []
    for m in mirrors:
        print(f"\n--- {m['name']} ({m['direction']}, dist={m['distance']:.1f}m) ---")
        print(f"  cx={m['cx']:.4e}, cy={m['cy']:.4e}, cxy={m['cxy']:.4e}")

        # Target sag
        s_target = compute_target_sag(m['cx'], m['cy'], m['cxy'], Xg, Zg)
        sag_pv = s_target.max() - s_target.min()
        sag_rms = np.sqrt(np.mean(s_target**2))
        print(f"  Target sag: PV={sag_pv*1e3:.2f} mm, RMS={sag_rms*1e3:.2f} mm")

        # LS fit
        h_lsq = lsq_fit_bolts(phi, s_target)
        h_range_mm = (h_lsq.max() - h_lsq.min()) * 1e3
        print(f"  LSQ bolt heights: min={h_lsq.min()*1e3:.2f}, max={h_lsq.max()*1e3:.2f}, "
              f"PV={h_range_mm:.2f} mm")

        # Residual
        A = phi.T
        s_fitted = A @ h_lsq
        residual = s_target - s_fitted
        rms_res = np.sqrt(np.mean(residual**2))
        max_res = np.max(np.abs(residual))
        print(f"  Fit residual: RMS={rms_res*1e3:.4f} mm, max|res|={max_res*1e3:.4f} mm")

        # R²
        ss_res = np.sum(residual**2)
        ss_tot = np.sum((s_target - np.mean(s_target))**2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
        print(f"  R2 = {r2:.6f}")

        # Save bolt init file
        output_path = os.path.join(args.output_dir, f"{m['name']}_lsq_bolt_init.txt")
        save_bolt_init_file(h_lsq, output_path, m['name'])
        print(f"  Saved: {output_path}")

        results.append({
            'name': m['name'],
            'direction': m['direction'],
            'distance': m['distance'],
            'cx': m['cx'],
            'cy': m['cy'],
            'cxy': m['cxy'],
            'sag_pv_mm': sag_pv * 1e3,
            'sag_rms_mm': sag_rms * 1e3,
            'bolt_min_mm': h_lsq.min() * 1e3,
            'bolt_max_mm': h_lsq.max() * 1e3,
            'bolt_pv_mm': h_range_mm,
            'residual_rms_mm': rms_res * 1e3,
            'residual_max_mm': max_res * 1e3,
            'r2': r2,
        })

    # Summary table
    print(f"\n{'='*90}")
    print(f"{'Mirror':<20s} {'Dist(m)':>8s} {'SagPV':>8s} {'BoltPV':>8s} "
          f"{'ResRMS':>8s} {'ResMax':>8s} {'R2':>8s}")
    print(f"{'-'*90}")
    for r in results:
        print(f"{r['name']:<20s} {r['distance']:8.1f} {r['sag_pv_mm']:7.2f} "
              f"{r['bolt_pv_mm']:7.2f} {r['residual_rms_mm']:7.3f} "
              f"{r['residual_max_mm']:7.3f} {r['r2']:7.5f}")

    # Optional CSV output
    if args.summary_csv:
        import csv
        with open(args.summary_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"\nSummary saved to: {args.summary_csv}")

    print(f"\nDone. {len(results)} bolt init files written to {args.output_dir}/")


if __name__ == '__main__':
    main()
