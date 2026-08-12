#!/usr/bin/env python3
"""
Ellipse vs TPS LS-Fit deformation validation for NEWS (North/East/West/South) at 300m.

Compares the ideal elliptic paraboloid surface against the TPS influence-function
least-squares fit, without gravity. Generates surface files for downstream C++
Vulkan flux dump and S95 computation.

Usage:
    python scripts/validate_ellipse_tps_news.py [--output-dir <dir>]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parent.parent

# ── Constants ────────────────────────────────────────────────────────────────
W, L = 12.84, 9.45       # plate dimensions (m)
GS = 32                    # render grid size
NB = 35                    # number of bolts
MARGIN = 0.08

# ── Mirror name -> distance mapping ──────────────────────────────────────────
MIRRORS_300M = ["North", "East", "South", "West"]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def bolt_positions():
    """Return [NB, 2] array of (x, z) bolt positions in plate-local coords."""
    positions = []
    for j in range(5):   # nz
        v = MARGIN + (1.0 - 2.0 * MARGIN) * j / 4.0
        for i in range(7):  # nx
            u = MARGIN + (1.0 - 2.0 * MARGIN) * i / 6.0
            x = (u - 0.5) * W
            z = (v - 0.5) * L
            positions.append([x, z])
    return np.array(positions)


def grid_coordinates():
    """Return (xg, zg, Xg, Zg) — 1D and 2D pixel-centered grid coords."""
    u = (np.arange(GS) + 0.5) / GS
    xg = (u - 0.5) * W
    zg = (u - 0.5) * L
    Xg, Zg = np.meshgrid(xg, zg)  # [GS, GS], row=z, col=x
    return xg, zg, Xg, Zg


def load_influence(data_dir="data_proxy"):
    """Load TPS influence functions. Returns phi [NB, GS*GS]."""
    phi_path = os.path.join(data_dir, "influence_phi.bin")
    phi_raw = np.fromfile(phi_path, dtype=np.float32)
    phi = phi_raw.reshape(NB, GS * GS)
    unit_sum = phi.sum(axis=0)
    print(f"  Influence: {NB} bolts, {GS}x{GS} grid")
    print(f"  Unit decomposition: min={unit_sum.min():.8f}, max={unit_sum.max():.8f}, "
          f"PV={unit_sum.max() - unit_sum.min():.2e}")
    self_vals = phi[np.arange(NB), _bolt_nearest_grid_idx()]
    print(f"  Self-influence (nearest grid): [{self_vals.min():.4f}, {self_vals.max():.4f}] "
          f"mean={self_vals.mean():.4f}")
    return phi


def _bolt_nearest_grid_idx():
    """Return grid flat index nearest to each bolt position."""
    pos = bolt_positions()
    xg, zg, _, _ = grid_coordinates()
    idxs = np.zeros(NB, dtype=int)
    for b in range(NB):
        di = np.argmin(np.abs(xg - pos[b, 0]))
        dj = np.argmin(np.abs(zg - pos[b, 1]))
        idxs[b] = dj * GS + di
    return idxs


def load_ellipse_params(ellipse_file, distance=300.0):
    """Parse ellipse.txt and return dict: mirror_name -> (A, B, C).

    File format: name pos_x pos_y pos_z A B C
    Distance = sqrt(px² + py² + pz²) (heliostat radial distance).
    """
    params = {}
    with open(ellipse_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            name = parts[0]
            px, py, pz = float(parts[1]), float(parts[2]), float(parts[3])
            dist = np.sqrt(px**2 + py**2 + pz**2)
            if abs(dist - distance) < 1.0 and name in MIRRORS_300M:
                A, B, C = float(parts[4]), float(parts[5]), float(parts[6])
                params[name] = (A, B, C)
    return params


def ellipse_surface(A, B, C):
    """Compute elliptic paraboloid on GSxGS grid. Returns flat [GS*GS] array."""
    _, _, Xg, Zg = grid_coordinates()
    w = A * Xg ** 2 + B * Zg ** 2 + C * Xg * Zg
    return w.ravel().astype(np.float64)


def tps_lsq_fit(phi, w_target):
    """Least-squares fit: min_h || h^T Phi - w_target ||^2.
    Returns h_lsq [NB] and w_tps [GS*GS].
    """
    PhiPhiT = phi @ phi.T
    Phi_w = phi @ w_target
    h_lsq = np.linalg.solve(PhiPhiT, Phi_w)
    w_tps = h_lsq @ phi
    return h_lsq, w_tps


def compute_deformation_metrics(w_ref, w_test, label_ref="Ref", label_test="Test"):
    """Return dict of metrics comparing two de-meaned surfaces."""
    w_r = np.asarray(w_ref, dtype=np.float64).ravel()
    w_t = np.asarray(w_test, dtype=np.float64).ravel()
    w_r_dm = w_r - np.mean(w_r)
    w_t_dm = w_t - np.mean(w_t)
    residual = w_r_dm - w_t_dm
    rms = np.sqrt(np.mean(residual ** 2)) * 1000  # mm
    sst = np.sum(w_r_dm ** 2)
    r2 = 1.0 - np.sum(residual ** 2) / max(sst, 1e-30)
    num = np.sum(w_r_dm * w_t_dm)
    den = np.sqrt(np.sum(w_r_dm ** 2) * np.sum(w_t_dm ** 2))
    shape_corr = num / max(den, 1e-30)
    pv_ref = np.ptp(w_r_dm) * 1000
    pv_test = np.ptp(w_t_dm) * 1000
    return {
        "rms_mm": float(rms),
        "r2": float(r2),
        "shape_corr": float(shape_corr),
        "pv_ref_mm": float(pv_ref),
        "pv_test_mm": float(pv_test),
        "pv_ratio": float(pv_test / max(pv_ref, 1e-10)),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Surface file I/O (x z uy format for C++ pipeline)
# ══════════════════════════════════════════════════════════════════════════════

def write_surface_file(w_flat, path):
    """Write surface as 'x z uy' text file (row-major: z outer, x inner)."""
    xg, zg, Xg, Zg = grid_coordinates()
    w_2d = w_flat.reshape(GS, GS)
    with open(path, "w") as f:
        f.write(f"# Surface file: {GS}x{GS} grid, x z uy (m)\n")
        for j in range(GS):
            for i in range(GS):
                f.write(f"{xg[i]:.9f} {zg[j]:.9f} {w_2d[j, i]:.12f}\n")


def write_bolt_file(heights, path, label="LS-fit"):
    """Write bolt heights as plain text."""
    with open(path, "w") as f:
        f.write(f"# Bolt heights ({label}), {NB} bolts\n")
        f.write(f"# max_stroke = {heights.max()*1000:.4f} mm\n")
        for h in heights:
            f.write(f"{h:.9f}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Plotting
# ══════════════════════════════════════════════════════════════════════════════

def plot_deformation(w_ellipse, w_tps, Xg, Zg, mirror_name, metrics, out_dir):
    """2x2 comparison: Ellipse | TPS LS-fit | Residual | Cross-section."""
    # Ensure 2D shapes
    w_e_2d = np.asarray(w_ellipse, dtype=np.float64).reshape(GS, GS)
    w_t_2d = np.asarray(w_tps, dtype=np.float64).reshape(GS, GS)
    w_e_dm = (w_e_2d - np.mean(w_e_2d)) * 1000  # mm
    w_t_dm = (w_t_2d - np.mean(w_t_2d)) * 1000
    res = w_e_dm - w_t_dm
    vm_surf = max(abs(w_e_dm).max(), abs(w_t_dm).max())
    vm_err = max(abs(res).max(), 0.01)

    bx, bz = bolt_positions()[:, 0], bolt_positions()[:, 1]

    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35,
                  width_ratios=[1, 1, 1], height_ratios=[1, 0.55])

    # Row 1: Ellipse surface | TPS LS-fit surface | Residual
    titles_row1 = [
        f"Ideal Elliptic Paraboloid\nPV={np.ptp(w_e_dm):.2f} mm",
        f"TPS LS-Fit Surface\nPV={np.ptp(w_t_dm):.2f} mm",
        f"Residual (Ellipse − TPS LS)\nRMS={metrics['rms_mm']:.3f} mm  "
        f"R²={metrics['r2']:.4f}  r={metrics['shape_corr']:.4f}",
    ]
    data_row1 = [w_e_dm, w_t_dm, res]
    cmaps_row1 = ["RdYlBu_r", "RdYlBu_r", "RdBu_r"]
    vmins = [(-vm_surf, vm_surf), (-vm_surf, vm_surf), (-vm_err, vm_err)]

    for c in range(3):
        ax = fig.add_subplot(gs[0, c])
        im = ax.pcolormesh(Xg, Zg, data_row1[c], cmap=cmaps_row1[c], shading="auto",
                           vmin=vmins[c][0], vmax=vmins[c][1])
        ax.set_title(titles_row1[c], fontsize=10, fontweight="bold")
        ax.set_aspect("equal")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("z (m)")
        plt.colorbar(im, ax=ax, label="mm")
        if c < 2:
            ax.scatter(bx, bz, c="black", s=12, marker="o", zorder=5,
                       edgecolors="white", linewidths=0.3)

    # Row 2 left: centre cross-section
    ax_xs = fig.add_subplot(gs[1, 0])
    mid_row = GS // 2
    x_1d = np.linspace(-W / 2, W / 2, GS)
    ax_xs.plot(x_1d, w_e_dm[mid_row, :], "b-", lw=1.8, label="Ellipse")
    ax_xs.plot(x_1d, w_t_dm[mid_row, :], "r--", lw=1.5, label="TPS LS-Fit")
    ax_xs.set_xlabel("x (m)")
    ax_xs.set_ylabel("w (mm)")
    ax_xs.set_title("Centre cross-section (z=0)", fontsize=10, fontweight="bold")
    ax_xs.legend(fontsize=8)
    ax_xs.grid(True, alpha=0.3)

    # Row 2 middle: per-row RMS
    ax_rms = fig.add_subplot(gs[1, 1])
    z_1d = np.linspace(-L / 2, L / 2, GS)
    rms_row = np.array([np.sqrt(np.mean(res[i, :] ** 2)) for i in range(GS)])
    ax_rms.plot(z_1d, rms_row, "b-o", ms=3, label=f"Mean={rms_row.mean():.3f} mm")
    ax_rms.fill_between(z_1d, 0, rms_row, alpha=0.15, color="blue")
    ax_rms.set_xlabel("z (m)")
    ax_rms.set_ylabel("RMS error (mm)")
    ax_rms.set_title("Per-row RMS error", fontsize=10, fontweight="bold")
    ax_rms.legend(fontsize=8)
    ax_rms.grid(True, alpha=0.3)

    # Row 2 right: metrics + bolt heights table
    ax_tbl = fig.add_subplot(gs[1, 2])
    ax_tbl.axis("off")
    lines = [
        f"Deformation Metrics — {mirror_name} 300m",
        "=" * 45,
        f"  RMS error:       {metrics['rms_mm']:.4f} mm",
        f"  R-squared:       {metrics['r2']:.6f}",
        f"  Shape corr:      {metrics['shape_corr']:.6f}",
        f"  PV ratio:        {metrics['pv_ratio']:.4f}",
        f"  Ellipse PV:      {metrics['pv_ref_mm']:.2f} mm",
        f"  TPS LS-fit PV:   {metrics['pv_test_mm']:.2f} mm",
    ]
    ax_tbl.text(0.05, 0.95, "\n".join(lines), transform=ax_tbl.transAxes,
                fontsize=8.5, fontfamily="monospace", va="top",
                bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.85))

    fig.suptitle(f"Ellipse vs TPS LS-Fit: {mirror_name} 300m (no gravity)",
                 fontsize=13, fontweight="bold", y=0.98)

    png_path = os.path.join(out_dir, f"comparison_{mirror_name}_300m.png")
    plt.savefig(png_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"    Plot: {png_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ellipse-file", default="data/ellipse.txt",
                   help="Ellipse parameter file (default: data/ellipse.txt)")
    p.add_argument("--data-dir", default="data_proxy",
                   help="TPS proxy data directory (default: data_proxy)")
    p.add_argument("--output-dir", default="validation/ellipse_tps_news",
                   help="Output directory (default: validation/ellipse_tps_news)")
    p.add_argument("--distance", type=float, default=300.0,
                   help="Heliostat distance in meters (default: 300)")
    args = p.parse_args()

    # ── Resolve paths ──
    ellipse_file = str(ROOT / args.ellipse_file) if not os.path.isabs(args.ellipse_file) else args.ellipse_file
    data_dir = str(ROOT / args.data_dir) if not os.path.isabs(args.data_dir) else args.data_dir
    out_dir = str(ROOT / args.output_dir) if not os.path.isabs(args.output_dir) else args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    print("=== Ellipse vs TPS LS-Fit — NEWS 300m Deformation Validation ===\n")

    # ── Load data ──
    print("[1/4] Loading TPS influence functions ...")
    phi = load_influence(data_dir)

    print(f"\n[2/4] Loading ellipse parameters from {args.ellipse_file} ...")
    ellipse_params = load_ellipse_params(ellipse_file, args.distance)
    if len(ellipse_params) != 4:
        print(f"WARNING: Expected 4 mirrors at {args.distance}m, found {len(ellipse_params)}: "
              f"{list(ellipse_params.keys())}")
    for name, (A, B, C) in ellipse_params.items():
        print(f"  {name}: A={A:.6e}, B={B:.6e}, C={C:.6e}")

    # ── Geometry ──
    _, _, Xg, Zg = grid_coordinates()

    # ── Process each mirror ──
    all_metrics = {}
    print(f"\n[3/4] Computing surfaces and metrics ...")
    for mirror in MIRRORS_300M:
        if mirror not in ellipse_params:
            print(f"  {mirror}: SKIP (no ellipse params)")
            continue
        A, B, C = ellipse_params[mirror]
        print(f"\n  --- {mirror} 300m ---")
        print(f"      A={A:.6e}, B={B:.6e}, C={C:.6e}")

        # Ideal ellipse surface
        w_ellipse = ellipse_surface(A, B, C)
        pv_ellipse = (w_ellipse.max() - w_ellipse.min()) * 1000
        print(f"      Ellipse surface PV: {pv_ellipse:.2f} mm")

        # TPS LS-fit
        h_lsq, w_tps = tps_lsq_fit(phi, w_ellipse)
        pv_h = (h_lsq.max() - h_lsq.min()) * 1000
        print(f"      LS-fit bolt PV: {pv_h:.2f} mm, "
              f"range [{h_lsq.min()*1000:.2f}, {h_lsq.max()*1000:.2f}] mm")

        # Deformation metrics
        m = compute_deformation_metrics(w_ellipse, w_tps, "Ellipse", "TPS-LSQ")
        all_metrics[mirror] = m
        print(f"      RMS={m['rms_mm']:.4f} mm  R2={m['r2']:.4f}  "
              f"shape_corr={m['shape_corr']:.4f}  PV_ratio={m['pv_ratio']:.4f}")

        # Plot
        plot_deformation(w_ellipse, w_tps, Xg, Zg, mirror, m, out_dir)

        # Write surface files
        sfx_ellipse = os.path.join(out_dir, f"{mirror}_300m_ellipse_surface.txt")
        sfx_tps = os.path.join(out_dir, f"{mirror}_300m_tps_lsq_surface.txt")
        write_surface_file(w_ellipse, sfx_ellipse)
        write_surface_file(w_tps, sfx_tps)
        print(f"      Surface files: {os.path.basename(sfx_ellipse)}, "
              f"{os.path.basename(sfx_tps)}")

        # Write bolt file
        bolt_path = os.path.join(out_dir, f"{mirror}_300m_tps_lsq_bolts.txt")
        write_bolt_file(h_lsq, bolt_path, f"LS-fit to {mirror} ellipse")
        print(f"      Bolt file: {os.path.basename(bolt_path)}")

    # ── Save summary ──
    print(f"\n[4/4] Saving summary ...")
    metrics_path = os.path.join(out_dir, "deformation_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)

    # CSV summary
    csv_path = os.path.join(out_dir, "summary_deformation.csv")
    with open(csv_path, "w") as f:
        f.write("Mirror,Ellipse_PV_mm,TPS_PV_mm,RMS_mm,R2,shape_corr,PV_ratio\n")
        for mirror in MIRRORS_300M:
            if mirror in all_metrics:
                m = all_metrics[mirror]
                f.write(f"{mirror},{m['pv_ref_mm']:.3f},{m['pv_test_mm']:.3f},"
                        f"{m['rms_mm']:.4f},{m['r2']:.4f},"
                        f"{m['shape_corr']:.4f},{m['pv_ratio']:.4f}\n")

    # ── Print summary table ──
    print(f"\n{'='*80}")
    print(f"  Deformation Summary — NEWS 300m (no gravity)")
    print(f"{'='*80}")
    print(f"  {'Mirror':<8s} {'Ellipse PV':>10s} {'TPS PV':>10s} {'RMS':>8s} {'R2':>8s} {'shape_corr':>10s} {'PV_ratio':>8s}")
    print(f"  {'-'*70}")
    for mirror in MIRRORS_300M:
        if mirror in all_metrics:
            m = all_metrics[mirror]
            print(f"  {mirror:<8s} {m['pv_ref_mm']:9.2f}mm {m['pv_test_mm']:9.2f}mm "
                  f"{m['rms_mm']:7.4f}mm {m['r2']:8.4f} {m['shape_corr']:10.4f} {m['pv_ratio']:8.4f}")
    print(f"{'='*80}")

    print(f"\n  Output: {out_dir}/")
    for fn in sorted(os.listdir(out_dir)):
        fpath = os.path.join(out_dir, fn)
        if os.path.isfile(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            print(f"    {fn}  ({size_kb:.1f} KB)")

    print(f"\n  Next step: run flux dump via C++ pipeline, then compute S95.")


if __name__ == "__main__":
    main()
