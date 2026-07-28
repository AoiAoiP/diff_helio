#!/usr/bin/env python3
"""
Post-FEA validation: three-way deformation comparison.

Runs ANSYS MAPDL batch simulation with prescribed bolt strokes at a given tilt
angle, then compares the resulting FEA deformation field against two references:
  (1) GUI Workbench FEA point cloud (optional, if available)
  (2) TPS proxy model prediction

Outputs (to validation/post_fea_validation/ by default):
  - node_dump_{angle}deg.csv              APDL raw 7-col output
  - apdl_bolt_stroke_{angle}deg.dat       APDL input file (reproducible)
  - comparison_{angle}deg.png             3-way 2D deformation comparison figure
  - metrics_{angle}deg.json               per-angle metrics
  - comparison_summary.json               aggregated metrics
  - summary_table.md                      Markdown validation table

Prerequisites:
  - ANSYS Mechanical APDL (tested with v252) + license server
  - Existing TPS proxy data (data_proxy/influence_phi.bin, gravity_*.bin, etc.)

Usage:
  # APDL vs Proxy only (2-way, default)
  python scripts/post_fea_validation.py \\
      --stroke-file results_4mirror_200iter/North_300m_STROKE_bolts.txt \\
      --angles 29.5 58.5

  # Full 3-way: APDL vs GUI vs Proxy
  python scripts/post_fea_validation.py \\
      --stroke-file results_4mirror_200iter/North_300m_STROKE_bolts.txt \\
      --angles 29.5 58.5 \\
      --gui-csv train_data/my_gui_29.5deg.csv train_data/my_gui_58.5deg.csv

  # Dry-run: generate APDL only, skip ANSYS
  python scripts/post_fea_validation.py \\
      --stroke-file results_4mirror_200iter/North_300m_STROKE_bolts.txt \\
      --angles 29.5 --dry-run

  # Auto-discover stroke file from result directory
  python scripts/post_fea_validation.py \\
      --result-dir results_4mirror_200iter --heliostat-prefix North \\
      --angles 29.5 58.5
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parent.parent

# Allow importing from scripts/ (run_fea_validation.py)
_SCRIPTS_DIR = str(ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from run_fea_validation import (
    load_bolt_layout,
    bolt_positions_from_layout,
    parse_stroke_file,
    find_stroke_file,
    generate_bolt_stroke_apdl,
    run_ansys,
    load_influence_functions,
    load_gravity_bins,
    interpolate_gravity,
    compute_proxy_surface,
    fea_csv_to_plate_local,
    interpolate_fea_to_grid,
    compute_metrics,
    _bolt_positions_7x5,
)

# ── ANSYS executable ──
ANSYS_EXE = "L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe"

# ── Default output directory ──
DEFAULT_OUTPUT_DIR = str(ROOT / "validation" / "post_fea_validation")


# ══════════════════════════════════════════════════════════════════════════════
# Three-way comparison plot
# ══════════════════════════════════════════════════════════════════════════════

def generate_three_way_plot(w_apdl, w_gui, w_proxy, Xg, Zg, angle_deg,
                            label_apdl, label_gui, label_proxy, out_dir):
    """Generate 3-way comparison figure: APDL FEA | GUI FEA | TPS Proxy.

    Layout (3×3 grid):
      Row 1: 3 surface plots (APDL / GUI / Proxy)
      Row 2: 3 residual maps (APDL−Proxy / GUI−Proxy / APDL−GUI)
      Row 3: centre cross-section | per-row RMS | metrics table

    When w_gui is None (no GUI reference), the GUI column is skipped and
    the plot becomes a 2-way APDL-vs-Proxy comparison.

    Args:
        w_apdl:   [GS, GS] APDL FEA surface (m)
        w_gui:    [GS, GS] GUI FEA surface (m), or None
        w_proxy:  [GS, GS] TPS proxy surface (m)
        Xg, Zg:   [GS, GS] grid coordinates
        angle_deg: tilt angle
        label_apdl, label_gui, label_proxy: display labels for each source
        out_dir:  output directory for PNG
    """
    GS = w_proxy.shape[0]
    has_gui = w_gui is not None

    # De-mean all surfaces
    w_a_dm = w_apdl - np.mean(w_apdl)
    w_p_dm = w_proxy - np.mean(w_proxy)
    w_g_dm = (w_gui - np.mean(w_gui)) if has_gui else None

    # Build pair metrics: compute_metrics(proxy_like, fea_like) → PV_ratio = PV_proxy/PV_fea
    # Convention: "A_vs_B" means A is the proxy/prediction, B is the FEA/ground-truth
    pairs = []
    # For APDL_vs_Proxy: Proxy is the "prediction", APDL-FEA is the "ground truth"
    pairs.append(("Proxy", "APDL", w_p_dm, w_a_dm, "APDL-Proxy"))
    if has_gui:
        pairs.append(("Proxy", "GUI", w_p_dm, w_g_dm, "GUI-Proxy"))
        pairs.append(("APDL", "GUI", w_a_dm, w_g_dm, "APDL-GUI"))
    all_metrics = {}
    for n_pred, n_ref, w_pred, w_ref, res_label in pairs:
        m = compute_metrics(w_pred, w_ref)
        all_metrics[f"{n_pred}_vs_{n_ref}"] = m

    # Residuals (for display, using the residual label order)
    res_ap = w_a_dm - w_p_dm   # APDL − Proxy
    res_gp = (w_g_dm - w_p_dm) if has_gui else None   # GUI − Proxy
    res_ag = (w_a_dm - w_g_dm) if has_gui else None   # APDL − GUI

    # Global colour limits
    all_surfs = [w_a_dm, w_p_dm]
    if has_gui:
        all_surfs.append(w_g_dm)
    vm_surf = max(abs(s).max() for s in all_surfs) * 1000

    residuals_list = [res_ap]
    if has_gui:
        residuals_list.extend([res_gp, res_ag])
    vm_err = max(abs(r).max() * 1000 for r in residuals_list if r is not None)
    vm_err = max(vm_err, 0.01)

    # Bolt positions for overlay
    bx, bz = _bolt_positions_7x5()

    # ── Layout ──
    n_cols = 3
    fig = plt.figure(figsize=(10 * n_cols, 18))
    gs = GridSpec(3, n_cols, figure=fig, hspace=0.40, wspace=0.35,
                  height_ratios=[1.0, 1.0, 0.55])

    # Row 1: Surface plots
    col_labels = ["APDL FEA", "GUI FEA" if has_gui else "(no GUI ref)",
                  "TPS Proxy"]
    col_data = [w_a_dm * 1000, (w_g_dm * 1000) if has_gui else None, w_p_dm * 1000]
    col_pvs = [np.ptp(w_a_dm) * 1000,
               np.ptp(w_g_dm) * 1000 if has_gui else None,
               np.ptp(w_p_dm) * 1000]

    for c in range(n_cols):
        ax = fig.add_subplot(gs[0, c])
        data = col_data[c]
        if data is None:
            ax.text(0.5, 0.5, "No GUI reference\nAdd --gui-csv to enable",
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=12, color='gray')
            ax.set_title(col_labels[c], fontsize=11, fontweight='bold')
            continue
        im = ax.pcolormesh(Xg, Zg, data, cmap='RdYlBu_r', shading='auto',
                           vmin=-vm_surf, vmax=vm_surf)
        ax.set_title(f"{col_labels[c]}\nPV={col_pvs[c]:.2f}mm",
                     fontsize=10, fontweight='bold')
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)')
        ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')
        ax.scatter(bx, bz, c='black', s=12, marker='o', zorder=5,
                   edgecolors='white', linewidths=0.3)

    # Row 2: Residual maps
    res_cols = [
        ("APDL − Proxy", res_ap),
        ("GUI − Proxy", res_gp) if has_gui else ("(no GUI ref)", None),
        ("APDL − GUI", res_ag) if has_gui else ("(no GUI ref)", None),
    ]
    for c, (title, res) in enumerate(res_cols):
        ax = fig.add_subplot(gs[1, c])
        if res is None:
            ax.text(0.5, 0.5, "—", transform=ax.transAxes,
                    ha='center', va='center', fontsize=14, color='gray')
            ax.set_title(title, fontsize=11, fontweight='bold')
            continue
        # Build annotation string
        pair_key = title.replace(" − ", "_vs_").replace(" ", "_")
        m = all_metrics.get(pair_key, {})
        anno = f"RMS={m.get('rms_mm', 0):.3f}mm  R²={m.get('r2', 0):.4f}  r={m.get('shape_corr', 0):.4f}"
        im = ax.pcolormesh(Xg, Zg, res * 1000, cmap='RdBu_r', shading='auto',
                           vmin=-vm_err, vmax=vm_err)
        ax.set_title(f"{title}\n{anno}", fontsize=9, fontweight='bold')
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)')
        ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

    # Row 3 left: Centre cross-section overlay
    ax_xs = fig.add_subplot(gs[2, 0])
    mid_row = GS // 2
    x_1d = np.linspace(-12.84 / 2, 12.84 / 2, GS)
    ax_xs.plot(x_1d, w_a_dm[mid_row, :] * 1000, 'b-', lw=1.8, label=label_apdl)
    if has_gui:
        ax_xs.plot(x_1d, w_g_dm[mid_row, :] * 1000, 'g--', lw=1.5, label=label_gui)
    ax_xs.plot(x_1d, w_p_dm[mid_row, :] * 1000, 'r:', lw=1.5, label=label_proxy)
    ax_xs.set_xlabel('x (m)')
    ax_xs.set_ylabel('w (mm)')
    ax_xs.set_title(f'Centre cross-section (z=0)', fontsize=10, fontweight='bold')
    ax_xs.legend(fontsize=8)
    ax_xs.grid(True, alpha=0.3)

    # Row 3 middle: Per-row RMS error
    ax_rms = fig.add_subplot(gs[2, 1])
    z_1d = np.linspace(-9.45 / 2, 9.45 / 2, GS)
    styles = [('b-o', 'APDL−Proxy'), ('g-s', 'GUI−Proxy'), ('r-^', 'APDL−GUI')]
    for (style, lbl), (n_pred, n_ref, w_pred, w_ref, res_label) in zip(styles, pairs):
        row_res = w_pred - w_ref
        rms_row = np.array([np.sqrt(np.mean(row_res[i, :] ** 2)) * 1000 for i in range(GS)])
        ax_rms.plot(z_1d, rms_row, style, ms=3, label=f'{lbl} (mean={rms_row.mean():.2f}mm)')
    ax_rms.set_xlabel('z (m)')
    ax_rms.set_ylabel('RMS error (mm)')
    ax_rms.set_title('Per-row RMS error', fontsize=10, fontweight='bold')
    ax_rms.legend(fontsize=7)
    ax_rms.grid(True, alpha=0.3)

    # Row 3 right: Metrics table
    ax_tbl = fig.add_subplot(gs[2, 2])
    ax_tbl.axis('off')
    lines = [f"Deformation Metrics — {angle_deg}°", "=" * 50]
    for n_pred, n_ref, w_pred, w_ref, res_label in pairs:
        pair_key = f"{n_pred}_vs_{n_ref}"
        m = all_metrics[pair_key]
        lines.append(f"  {n_pred} vs {n_ref}:")
        lines.append(f"    RMS={m['rms_mm']:.4f} mm  R2={m['r2']:.6f}")
        lines.append(f"    shape_corr={m['shape_corr']:.6f}  PV_ratio={m['pv_ratio']:.4f}")
        lines.append("")
    tbl = "\n".join(lines)
    ax_tbl.text(0.05, 0.95, tbl, transform=ax_tbl.transAxes,
                fontsize=8, fontfamily='monospace', va='top',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.85))

    fig.suptitle(f'Post-FEA Validation: {label_apdl} | {label_gui if has_gui else "no GUI"} | {label_proxy}',
                 fontsize=13, fontweight='bold', y=0.99)

    # Save
    safe_ang = f"{angle_deg}".replace('.', 'p')
    png_path = os.path.join(out_dir, f"comparison_{safe_ang}deg.png")
    plt.savefig(png_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"    Plot saved: {png_path}")

    return all_metrics


# ══════════════════════════════════════════════════════════════════════════════
# Summary table
# ══════════════════════════════════════════════════════════════════════════════

def write_summary_table(all_results, out_dir):
    """Write summary_table.md aggregating results across all angles.

    Args:
        all_results: list of dicts, each with keys:
            angle_deg, has_gui, metrics (dict of pair→metrics)
        out_dir: output directory
    """
    rows = []
    for entry in all_results:
        ang = entry["angle_deg"]
        for pair_key, m in entry["metrics"].items():
            n1, n2 = pair_key.split("_vs_")
            rows.append({
                "angle": ang,
                "pair": f"{n1} vs {n2}",
                "rms_mm": m["rms_mm"],
                "r2": m["r2"],
                "shape_corr": m["shape_corr"],
                "pv_ratio": m["pv_ratio"],
            })

    if not rows:
        return

    md = []
    md.append("# Post-FEA Validation Summary\n")
    md.append(f"**Date**: {time.strftime('%Y-%m-%d')}\n")
    md.append("")
    md.append("| Angle | Pair | RMS (mm) | R² | shape_corr | PV ratio |")
    md.append("|:---:|------|:---:|:---:|:---:|:---:|")
    for r in rows:
        md.append(f"| {r['angle']}° | {r['pair']} | "
                  f"{r['rms_mm']:.3f} | {r['r2']:.4f} | "
                  f"{r['shape_corr']:.4f} | {r['pv_ratio']:.4f} |")

    md.append("")
    md.append("## Notes\n")
    md.append("- **APDL**: ANSYS MAPDL batch simulation (automated via this script)")
    md.append("- **GUI**: Workbench Mechanical reference (if provided via `--gui-csv`)")
    md.append("- **Proxy**: TPS influence-function proxy model (`gravity + Σ h_b·φ_b`)")
    md.append("- PV ratio = PV_proxy / PV_fea; values > 1 indicate proxy over-predicts amplitude")
    md.append("")

    table_path = os.path.join(out_dir, "summary_table.md")
    with open(table_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n  Summary table: {table_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Single-angle processing
# ══════════════════════════════════════════════════════════════════════════════

def process_angle(angle_deg, layout, bolt_positions, strokes,
                  gui_csv_path, data_dir, out_dir, args,
                  apdl_csv_override=None):
    """Run APDL for one angle, then do 2- or 3-way comparison.

    Args:
        angle_deg: tilt angle
        layout: bolt layout config dict
        bolt_positions: list of (x,z) bolt positions
        strokes: list of float bolt stroke values (m)
        gui_csv_path: path to GUI reference CSV (or None)
        data_dir: path to TPS proxy data directory
        out_dir: output directory
        args: parsed CLI args
        apdl_csv_override: if provided, use this CSV as APDL source and skip ANSYS

    Returns:
        dict with angle_deg, has_gui, metrics, apdl_csv_path, gui_csv_path
    """
    has_gui = gui_csv_path is not None
    print(f"\n{'=' * 60}")
    print(f"  [{angle_deg}°] "
          f"{'APDL + GUI + Proxy' if has_gui else 'APDL + Proxy'}"
          f"{' (compare-only)' if apdl_csv_override else ''}")
    print(f"{'=' * 60}")

    apdl_csv = None

    if apdl_csv_override:
        # ── Phase A skipped: use existing APDL CSV ──
        if not os.path.exists(apdl_csv_override):
            print(f"  ERROR: APDL CSV not found: {apdl_csv_override}", file=sys.stderr)
            return None
        apdl_csv = os.path.join(out_dir, f"node_dump_{angle_deg}deg.csv")
        shutil.copy(apdl_csv_override, apdl_csv)
        data = np.loadtxt(apdl_csv, delimiter=',', skiprows=1)
        uy = data[:, 4]
        uy_pv = np.ptp(uy) * 1000
        print(f"  Using existing APDL CSV: {apdl_csv_override}")
        print(f"  UY_PV={uy_pv:.1f}mm, nodes={data.shape[0]}")
    else:
        # ── Phase A: APDL generation ──
        work_dir = tempfile.mkdtemp(
            prefix=f"post_fea_{str(angle_deg).replace('.', 'p')}deg_",
            dir=str(ROOT / "build"))
        try:
            dat_path, expected_csv = generate_bolt_stroke_apdl(
                layout, angle_deg, bolt_positions, strokes, work_dir)

            # Save APDL for reproducibility
            apdl_dest = os.path.join(out_dir, f"apdl_bolt_stroke_{angle_deg}deg.dat")
            shutil.copy(dat_path, apdl_dest)
            print(f"  APDL input: {apdl_dest}")

            if args.dry_run:
                apdl_csv = None
                print(f"  DRY RUN — skipping ANSYS")
            else:
                t0 = time.time()
                ok = run_ansys(dat_path, work_dir, args.ansys_exe,
                               timeout_s=args.timeout_s)
                if not ok:
                    print(f"  ERROR: ANSYS failed for {angle_deg}°", file=sys.stderr)
                    return None

                if not os.path.exists(expected_csv):
                    print(f"  ERROR: missing CSV: {expected_csv}", file=sys.stderr)
                    return None

                # Copy CSV to output
                apdl_csv = os.path.join(out_dir, f"node_dump_{angle_deg}deg.csv")
                shutil.copy(expected_csv, apdl_csv)

                elapsed = time.time() - t0
                data = np.loadtxt(apdl_csv, delimiter=',', skiprows=1)
                uy = data[:, 4]
                uy_pv = np.ptp(uy) * 1000
                print(f"  APDL done: UY_PV={uy_pv:.1f}mm, nodes={data.shape[0]}, {elapsed:.0f}s")

        finally:
            if not args.keep_temp:
                shutil.rmtree(work_dir, ignore_errors=True)

    if args.dry_run:
        return None

    # ── Phase B: Comparison ──
    if apdl_csv is None:
        return None

    print(f"\n  Computing proxy surface ...")
    # Load TPS influence data
    phi, phi_u, phi_v, NB = load_influence_functions(data_dir)
    if len(strokes) != NB:
        print(f"  WARN: {len(strokes)} strokes vs {NB} influence functions")
        NB_use = min(len(strokes), NB)
    else:
        NB_use = NB

    # Load and interpolate gravity
    gravity_bins, gravity_angles_arr, GS = load_gravity_bins(data_dir)
    gravity = interpolate_gravity(angle_deg, gravity_bins, gravity_angles_arr)
    print(f"  Gravity PV: {np.ptp(gravity) * 1000:.2f} mm")

    # Compute proxy surface
    w_proxy_flat = compute_proxy_surface(strokes[:NB_use], phi[:NB_use], gravity)
    w_proxy = w_proxy_flat.reshape(GS, GS)

    # Load APDL FEA → plate-local → grid
    x_local, z_local, w_fea_apdl = fea_csv_to_plate_local(apdl_csv, angle_deg)
    w_apdl_grid, Xg, Zg = interpolate_fea_to_grid(x_local, z_local, w_fea_apdl, GS)
    print(f"  APDL FEA grid PV: {np.ptp(w_apdl_grid) * 1000:.2f} mm")

    # Load GUI FEA → plate-local → grid (if available)
    w_gui_grid = None
    label_gui = "GUI (N/A)"
    if has_gui:
        if not os.path.exists(gui_csv_path):
            print(f"  WARN: GUI CSV not found: {gui_csv_path}")
        else:
            x_g_local, z_g_local, w_fea_gui = fea_csv_to_plate_local(gui_csv_path, angle_deg)
            w_gui_grid, _, _ = interpolate_fea_to_grid(x_g_local, z_g_local, w_fea_gui, GS)
            label_gui = f"GUI ({os.path.basename(gui_csv_path)})"
            print(f"  GUI FEA grid PV: {np.ptp(w_gui_grid) * 1000:.2f} mm")

    # ── Generate 3-way comparison plot ──
    label_apdl = f"APDL ({os.path.basename(apdl_csv)})"
    label_proxy = "TPS Proxy"

    all_metrics = generate_three_way_plot(
        w_apdl_grid, w_gui_grid, w_proxy, Xg, Zg, angle_deg,
        label_apdl, label_gui, label_proxy, out_dir)

    # ── Save per-angle metrics ──
    safe_ang = f"{angle_deg}".replace('.', 'p')
    metrics_out = {
        "angle_deg": angle_deg,
        "has_gui": has_gui,
        "apdl_csv": apdl_csv,
        "gui_csv": gui_csv_path,
        "label_apdl": label_apdl,
        "label_gui": label_gui,
        "label_proxy": label_proxy,
        "metrics": {k: v for k, v in all_metrics.items()},
    }
    metrics_path = os.path.join(out_dir, f"metrics_{safe_ang}deg.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics_out, f, indent=2)

    # ── Print per-angle summary ──
    for pair_key, m in all_metrics.items():
        print(f"    {pair_key}: RMS={m['rms_mm']:.3f}mm  R2={m['r2']:.4f}  "
              f"shape_corr={m['shape_corr']:.4f}  PV_ratio={m['pv_ratio']:.4f}")

    return metrics_out


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # Stroke file input (either --stroke-file or --result-dir)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--stroke-file", default=None,
                   help="Path to *_STROKE_bolts.txt")
    g.add_argument("--result-dir", default=None,
                   help="Result directory containing *_STROKE_bolts.txt")

    p.add_argument("--heliostat-prefix", default=None,
                   help="Filter for specific heliostat (used with --result-dir)")
    p.add_argument("--bolt-layout", default="configs/bolt_layouts/7x5_default.json",
                   help="Bolt layout JSON config file")
    p.add_argument("--angles", type=float, nargs="+", default=[29.5, 58.5],
                   help="Tilt angles in degrees (default: 29.5 58.5)")
    p.add_argument("--gui-csv", default=None, nargs="+",
                   help="GUI Workbench FEA CSV(s) for comparison, matched positionally "
                        "to --angles. Omit for 2-way (APDL vs Proxy) comparison only.")
    p.add_argument("--apdl-csv", default=None, nargs="+",
                   help="Existing APDL FEA CSV(s) to use instead of running ANSYS, "
                        "matched positionally to --angles. Skips Phase A entirely.")
    p.add_argument("--data-dir", default="data_proxy",
                   help="Path to TPS proxy data directory (default: data_proxy)")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                   help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    p.add_argument("--ansys-exe", default=ANSYS_EXE,
                   help="Path to ANSYS MAPDL executable")
    p.add_argument("--keep-temp", action="store_true",
                   help="Keep temporary ANSYS working files")
    p.add_argument("--dry-run", action="store_true",
                   help="Generate APDL files but do not run ANSYS")
    p.add_argument("--timeout-s", type=int, default=600,
                   help="ANSYS timeout per angle in seconds (default: 600)")
    args = p.parse_args()

    # ── Resolve stroke file ──
    if args.result_dir:
        result_dir = args.result_dir
        if not os.path.isabs(result_dir):
            result_dir = str(ROOT / result_dir)
        stroke_files = find_stroke_file(result_dir, args.heliostat_prefix)
        if not stroke_files:
            print(f"ERROR: No *_STROKE_bolts.txt in {result_dir}", file=sys.stderr)
            sys.exit(1)
        if len(stroke_files) > 1 and args.heliostat_prefix is None:
            print(f"Found {len(stroke_files)} STROKE files. Use --heliostat-prefix:")
            for name, _ in stroke_files:
                print(f"  {name}")
            sys.exit(1)
        helio_name, stroke_path = stroke_files[0]
    else:
        stroke_path = args.stroke_file
        if not os.path.isabs(stroke_path):
            stroke_path = str(ROOT / stroke_path)
        helio_name = os.path.splitext(os.path.basename(stroke_path))[0]

    if not os.path.exists(stroke_path):
        print(f"ERROR: Stroke file not found: {stroke_path}", file=sys.stderr)
        sys.exit(1)

    print(f"=== Post-FEA Validation: {helio_name} ===")
    print(f"  Stroke file: {stroke_path}")
    print(f"  Angles:      {args.angles}")
    print(f"  Data dir:    {args.data_dir}")

    # ── Parse GUI CSV mapping ──
    gui_map = {}
    if args.gui_csv:
        if len(args.gui_csv) != len(args.angles):
            print(f"ERROR: --gui-csv count ({len(args.gui_csv)}) must match "
                  f"--angles count ({len(args.angles)})", file=sys.stderr)
            sys.exit(1)
        for ang, csv_path in zip(args.angles, args.gui_csv):
            if not os.path.isabs(csv_path):
                csv_path = str(ROOT / csv_path)
            gui_map[ang] = csv_path
        print(f"  GUI CSV:     {len(gui_map)} reference(s)")

    # ── Parse APDL CSV override mapping ──
    apdl_map = {}
    if args.apdl_csv:
        if len(args.apdl_csv) != len(args.angles):
            print(f"ERROR: --apdl-csv count ({len(args.apdl_csv)}) must match "
                  f"--angles count ({len(args.angles)})", file=sys.stderr)
            sys.exit(1)
        for ang, csv_path in zip(args.angles, args.apdl_csv):
            if not os.path.isabs(csv_path):
                csv_path = str(ROOT / csv_path)
            apdl_map[ang] = csv_path
        print(f"  APDL CSV:    {len(apdl_map)} override(s) — skipping ANSYS")

    # ── Load bolt layout ──
    layout_path = args.bolt_layout
    if not os.path.isabs(layout_path):
        layout_path = str(ROOT / layout_path)
    if not os.path.exists(layout_path):
        print(f"ERROR: Bolt layout not found: {layout_path}", file=sys.stderr)
        sys.exit(1)
    layout = load_bolt_layout(str(layout_path))
    bolt_positions = bolt_positions_from_layout(layout)
    strokes = parse_stroke_file(stroke_path)

    print(f"  Layout:      {layout['bolts_x']}×{layout['bolts_z']} = {len(bolt_positions)} bolts")
    print(f"  Strokes:     [{min(strokes) * 1000:.1f}, {max(strokes) * 1000:.1f}] mm")
    if len(strokes) != len(bolt_positions):
        print(f"  WARNING: {len(strokes)} stroke values vs {len(bolt_positions)} bolt positions")

    # ── Data dir ──
    data_dir = args.data_dir
    if not os.path.isabs(data_dir):
        data_dir = str(ROOT / data_dir)

    # ── Output dir ──
    out_dir = args.output_dir
    if not os.path.isabs(out_dir):
        out_dir = str(ROOT / out_dir)
    os.makedirs(out_dir, exist_ok=True)
    print(f"  Output:      {out_dir}/")

    if args.dry_run:
        print(f"  DRY RUN:     APDL generation only, no ANSYS execution")
    print(f"  ANSYS:       {args.ansys_exe}")

    # ── Process each angle ──
    all_results = []
    for ang in args.angles:
        result = process_angle(
            ang, layout, bolt_positions, strokes,
            gui_map.get(ang), data_dir, out_dir, args,
            apdl_csv_override=apdl_map.get(ang))
        if result:
            all_results.append(result)

    # ── Aggregate summary ──
    if all_results:
        summary_path = os.path.join(out_dir, "comparison_summary.json")
        with open(summary_path, "w") as f:
            json.dump(all_results, f, indent=2)
        write_summary_table(all_results, out_dir)
        print(f"\n  Aggregate summary: {summary_path}")

    # ── Final tally ──
    n_ok = len(all_results)
    print(f"\n=== Post-FEA Validation done: {n_ok}/{len(args.angles)} angles ===")
    print(f"\n  Output files in {out_dir}/:")
    for fn in sorted(os.listdir(out_dir)):
        fpath = os.path.join(out_dir, fn)
        if os.path.isfile(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            print(f"    {fn}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
