#!/usr/bin/env python3
"""
Run ANSYS FEA validation for optimized bolt configurations.

Reads optimized bolt strokes from a result directory (results_xxx/), runs ANSYS
MAPDL batch simulations with actual bolt displacements (nonzero stroke), and
outputs deformed plate point clouds for validation against the proxy model.

Key difference from gravity-only sim (ansys_gravity.py):
  - Gravity sim: D,ALL,ALL,0.0 at bolt nodes (all DOF fixed, zero displacement)
  - This script: D,UX,0 + D,UY,stroke*cos(θ) + D,UZ,-stroke*sin(θ)
    (prescribed displacement in plate normal direction at each bolt)

Prerequisites:
  - ANSYS Mechanical APDL (tested with v252)
  - License server running

Usage:
  # Validate at representative angles
  python scripts/run_fea_validation.py --result-dir results_north_300iter --angles 0 29.5 58.5

  # Dry run: generate APDL only
  python scripts/run_fea_validation.py --result-dir results_north_300iter --dry-run

  # Multi-heliostat results
  python scripts/run_fea_validation.py --result-dir results_4mirror_300iter --heliostat-prefix North

Output (<result_dir>/fea_validation/):
  fea_deformed_{angle}deg.txt   — x,y,z,ux,uy,uz (global coords, full FEA mesh)
  fea_pointcloud_{angle}deg.txt — x,y,z only (deformed coords for external tools)
  fea_metadata.json             — bolt strokes, simulation params, per-angle PV/RMS
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
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parent.parent

# ── ANSYS executable ──
ANSYS_EXE = "L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe"

# ── Default validation angles ──
DEFAULT_ANGLES = [0, 29.5, 58.5]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def load_bolt_layout(path):
    """Load bolt layout configuration from JSON."""
    with open(path) as f:
        cfg = json.load(f)
    for k in ["bolts_x", "bolts_z", "margin", "plate_width_m", "plate_length_m",
              "plate_thickness_m"]:
        if k not in cfg:
            raise ValueError(f"Bolt layout config missing key: {k}")
    return cfg


def bolt_positions_from_layout(layout):
    """Compute bolt (x,z) positions from layout config (row-major: z outer, x inner)."""
    nx, nz = layout["bolts_x"], layout["bolts_z"]
    m = layout["margin"]
    pW, pL = layout["plate_width_m"], layout["plate_length_m"]
    positions = []
    for j in range(nz):
        v = m + (1.0 - 2.0 * m) * j / (nz - 1)
        for i in range(nx):
            u = m + (1.0 - 2.0 * m) * i / (nx - 1)
            x = (u - 0.5) * pW
            z = (v - 0.5) * pL
            positions.append((x, z))
    return positions


def find_stroke_file(result_dir, prefix=None):
    """Find *_STROKE_bolts.txt in result directory. Returns list of (name, path)."""
    files = []
    for f in os.listdir(result_dir):
        if f.endswith('_STROKE_bolts.txt'):
            name = f.replace('_STROKE_bolts.txt', '')
            if prefix is None or prefix in name:
                files.append((name, os.path.join(result_dir, f)))
    return files


def parse_stroke_file(path):
    """Parse STROKE_bolts.txt (one stroke value per line, zero-based, meters).
    Returns list of float stroke values.
    """
    strokes = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                strokes.append(float(line))
            except ValueError:
                pass
    return strokes


# ══════════════════════════════════════════════════════════════════════════════
# APDL generation — bolt stroke simulation
# ══════════════════════════════════════════════════════════════════════════════

def generate_bolt_stroke_apdl(layout, angle_deg, bolt_xy, bolt_strokes, work_dir):
    """Generate ANSYS APDL input for bolt-stroke FEA simulation.

    Key difference from gravity-only APDL:
    - Bolt nodes are NOT fixed to zero. Instead, prescribed displacements are
      applied along the plate normal direction: (0, cosθ, +sinθ) in global coords.
    - Gravity (ACEL,0,9.81,0) is still active.
    - Matches ANSYS Workbench GUI convention (train_data/APDL_pre.txt).

    Args:
        layout: bolt layout config dict
        angle_deg: tilt angle from horizontal (degrees)
        bolt_xy: list of (x, z) bolt positions in plate-local coordinates (m)
        bolt_strokes: list of float bolt stroke values (m), same length as bolt_xy
        work_dir: working directory for ANSYS scratch files

    Returns:
        (dat_path, node_csv_path)
    """
    pW = layout["plate_width_m"]
    pL = layout["plate_length_m"]
    t = layout["plate_thickness_m"]
    E = layout.get("youngs_modulus_pa", 7.0e10)
    nu = layout.get("poisson_ratio", 0.22)
    rho = layout.get("density_kg_m3", 2500)

    theta = np.radians(angle_deg)
    sin_t = np.sin(theta)
    cos_t = np.cos(theta)

    # Plate corners in global coords (tilted about X).
    # GUI convention: when z_local=+hl (top edge), global Y=-hl*sin_t (below origin).
    # Plate normal in global = (0, cosθ, +sinθ).
    hw, hl = pW / 2.0, pL / 2.0
    corners_global = [
        (-hw, -hl * sin_t,  hl * cos_t),
        ( hw, -hl * sin_t,  hl * cos_t),
        ( hw,  hl * sin_t, -hl * cos_t),
        (-hw,  hl * sin_t, -hl * cos_t),
    ]

    dat_path = os.path.join(work_dir, f"bolt_stroke_{angle_deg}deg.dat")
    node_csv = os.path.join(work_dir, f"node_dump_{angle_deg}deg.csv")

    ndiv_x = layout.get("mesh_ndiv_x", 64)
    ndiv_z = layout.get("mesh_ndiv_z", 48)
    n_bolts = len(bolt_xy)

    lines = []
    lines.append(f"! Bolt-stroke FEA: tilt={angle_deg}deg, {n_bolts} bolts")
    lines.append(f"! Auto-generated by scripts/run_fea_validation.py")
    lines.append(f"! Bolt displacements applied in plate normal direction")
    lines.append("")
    lines.append("/NOPR")
    lines.append("")
    lines.append(f"! ── Parameters ──")
    lines.append(f"W = {pW}")
    lines.append(f"L = {pL}")
    lines.append(f"thick = {t}")
    lines.append(f"E_mod = {E}")
    lines.append(f"nu = {nu}")
    lines.append(f"rho = {rho}")
    lines.append(f"ang = {angle_deg}")
    lines.append(f"nbolts = {n_bolts}")
    lines.append("")
    lines.append("/PREP7")
    lines.append("")
    lines.append("! ── Material & Element ──")
    lines.append("MP,EX,1,E_mod")
    lines.append("MP,NUXY,1,nu")
    lines.append("MP,DENS,1,rho")
    lines.append("ET,1,SHELL181          ! 4-node structural shell")
    lines.append("KEYOPT,1,3,2           ! incompatible modes (match Workbench GUI)")
    lines.append("R,1,thick")
    lines.append("")
    lines.append("! ── Geometry: clean 4-sided area ──")
    lines.append(f"K,1,{corners_global[0][0]:.6f},{corners_global[0][1]:.6f},{corners_global[0][2]:.6f}")
    lines.append(f"K,2,{corners_global[1][0]:.6f},{corners_global[1][1]:.6f},{corners_global[1][2]:.6f}")
    lines.append(f"K,3,{corners_global[2][0]:.6f},{corners_global[2][1]:.6f},{corners_global[2][2]:.6f}")
    lines.append(f"K,4,{corners_global[3][0]:.6f},{corners_global[3][1]:.6f},{corners_global[3][2]:.6f}")
    lines.append("A,1,2,3,4")
    lines.append("")
    lines.append(f"! ── Mesh: mapped quad mesh {ndiv_x}x{ndiv_z} (matching Workbench GUI) ──")
    lines.append("MSHAPE,0,2D             ! quad elements")
    lines.append("MSHKEY,1                ! mapped mesh (deterministic)")
    lines.append(f"LESIZE,1,,,{ndiv_x}           ! L1 (K1-K2): X-parallel, {ndiv_x} divs")
    lines.append(f"LESIZE,2,,,{ndiv_z}           ! L2 (K2-K3): Z-parallel, {ndiv_z} divs")
    lines.append(f"LESIZE,3,,,{ndiv_x}           ! L3 (K3-K4): X-parallel, {ndiv_x} divs")
    lines.append(f"LESIZE,4,,,{ndiv_z}           ! L4 (K4-K1): Z-parallel, {ndiv_z} divs")
    lines.append("AMESH,ALL")
    lines.append("")
    lines.append("! ── BC: prescribed bolt displacement in plate normal direction ──")
    lines.append(f"! Plate normal (global) = (0, cos({angle_deg}), +sin({angle_deg}))")
    lines.append(f"! Bolt stroke pushes plate in +normal direction")
    lines.append("HALF_WIN=0.3")
    for i, (bx, bz_local) in enumerate(bolt_xy):
        gx = bx
        gz = bz_local * cos_t
        stroke = bolt_strokes[i] if i < len(bolt_strokes) else 0.0
        # Plate normal in global: (0, cosθ, +sinθ) — matching GUI convention
        uy_prescribed = stroke * cos_t
        uz_prescribed = stroke * sin_t

        lines.append(f"! Bolt {i}: stroke={stroke*1000:.3f}mm → UY={uy_prescribed*1000:.3f}mm, UZ={uz_prescribed*1000:.3f}mm")
        lines.append(f"NSEL,S,LOC,X,{gx:.6f}-HALF_WIN,{gx:.6f}+HALF_WIN")
        lines.append(f"NSEL,R,LOC,Z,{gz:.6f}-HALF_WIN,{gz:.6f}+HALF_WIN")
        lines.append(f"D,ALL,UX,0.0                        ! fix lateral X")
        lines.append(f"D,ALL,UY,{uy_prescribed:.9f}            ! prescribed Y (normal comp)")
        lines.append(f"D,ALL,UZ,{uz_prescribed:.9f}            ! prescribed Z (normal comp)")
        lines.append("ALLSEL,ALL")
    lines.append("")
    lines.append("! ── Solution ──")
    lines.append("/SOLU")
    lines.append("ANTYPE,STATIC")
    lines.append("NLGEOM,ON")
    lines.append("AUTOTS,ON              ! auto time stepping (match GUI)")
    lines.append("NSUBST,1,10,1           ! initial=1, max=10, min=1 (match GUI)")
    lines.append("OUTRES,ALL,ALL")
    lines.append("PIVCHECK,0             ! disable pivot checking")
    lines.append("PRED,ON                ! predictor (match GUI)")
    lines.append("")
    lines.append("! Gravity: always vertical (global +Y direction)")
    lines.append("ACEL,0,9.81,0")
    lines.append("SOLVE")
    lines.append("FINISH")
    lines.append("")
    lines.append("! ── Post: 7-col CSV ──")
    lines.append("/POST1")
    lines.append("SET,LAST")
    lines.append("ALLSEL,ALL")
    lines.append("")
    lines.append("*GET,N_NODES,NODE,0,COUNT")
    lines.append("*GET,N_MIN,NODE,0,NUM,MIN")
    lines.append("")
    lines.append("*CFOPEN,'" + node_csv.replace('\\', '/') + "',,,")
    lines.append("*VWRITE,'x','y','z','ux','uy','uz','usum'")
    lines.append("%C,%C,%C,%C,%C,%C,%C")
    lines.append("")
    lines.append("nd = N_MIN")
    lines.append("*DO,idx,1,N_NODES,1")
    lines.append("  *GET,ux_val,NODE,nd,U,X")
    lines.append("  *GET,uy_val,NODE,nd,U,Y")
    lines.append("  *GET,uz_val,NODE,nd,U,Z")
    lines.append("  *GET,usum_val,NODE,nd,U,SUM")
    lines.append("  *VWRITE,NX(nd),NY(nd),NZ(nd),ux_val,uy_val,uz_val,usum_val")
    lines.append("  %12.6F,%12.6F,%12.6F,%14.9F,%14.9F,%14.9F,%14.9F")
    lines.append("  nd = NDNEXT(nd)")
    lines.append("*ENDDO")
    lines.append("*CFCLOSE")
    lines.append("")
    lines.append("FINISH")
    lines.append("/EXIT,NOSAVE")

    with open(dat_path, 'w') as f:
        f.write('\n'.join(lines))

    return dat_path, node_csv


# ══════════════════════════════════════════════════════════════════════════════
# ANSYS runner
# ══════════════════════════════════════════════════════════════════════════════

def run_ansys(dat_path, work_dir, ansys_exe=ANSYS_EXE, timeout_s=600):
    """Run ANSYS MAPDL in batch mode. Returns True on success."""
    jobname = os.path.splitext(os.path.basename(dat_path))[0]
    cmd = [
        ansys_exe,
        "-b", "-np", "4",
        "-dir", work_dir,
        "-j", jobname,
        "-i", dat_path,
        "-o", os.path.join(work_dir, f"{jobname}.out"),
    ]
    print(f"  ANSYS: {' '.join(cmd[:2])} -j {jobname} ...")
    try:
        subprocess.run(cmd, cwd=work_dir, timeout=timeout_s,
                       capture_output=True, text=True)
        return True
    except subprocess.TimeoutExpired:
        print(f"  ERROR: ANSYS timed out after {timeout_s}s", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"  ERROR: ANSYS not found at {ansys_exe}", file=sys.stderr)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Run ANSYS FEA validation for optimized bolt configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--result-dir', required=True,
                        help='Path to result directory containing *_STROKE_bolts.txt')
    parser.add_argument('--bolt-layout', default='configs/bolt_layouts/7x5_default.json',
                        help='Bolt layout JSON config file')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: <result_dir>/fea_validation/)')
    parser.add_argument('--angles', type=float, nargs='+', default=DEFAULT_ANGLES,
                        help=f'Tilt angles in degrees (default: {DEFAULT_ANGLES})')
    parser.add_argument('--heliostat-prefix', default=None,
                        help='Filter for specific heliostat (e.g. "North_300m"); auto-detect if only one')
    parser.add_argument('--ansys-exe', default=ANSYS_EXE,
                        help='Path to ANSYS MAPDL executable')
    parser.add_argument('--keep-temp', action='store_true',
                        help='Keep temporary ANSYS working files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Generate APDL files but do not run ANSYS')
    parser.add_argument('--compare', action='store_true',
                        help='Run proxy-vs-FEA comparison after FEA simulation')
    parser.add_argument('--compare-csv', default=None, nargs='+',
                        help='Run comparison using existing FEA CSV(s) (skips ANSYS). '
                             'Usage: --compare-csv train_data/node_dump_295deg_ON.csv')
    parser.add_argument('--compare-label', default=None,
                        help='Label for comparison plot (used with --compare-csv)')
    parser.add_argument('--influence-dir', default='data_proxy',
                        help='Path to influence/gravity data directory (default: data_proxy)')
    args = parser.parse_args()

    # ── Resolve result directory ──
    result_dir = args.result_dir
    if not os.path.isabs(result_dir):
        result_dir = str(ROOT / result_dir)
    if not os.path.isdir(result_dir):
        print(f"ERROR: Result directory not found: {result_dir}", file=sys.stderr)
        sys.exit(1)

    # ── Find STROKE bolt files ──
    stroke_files = find_stroke_file(result_dir, args.heliostat_prefix)
    if not stroke_files:
        print(f"ERROR: No *_STROKE_bolts.txt found in {result_dir}", file=sys.stderr)
        sys.exit(1)
    if len(stroke_files) > 1 and args.heliostat_prefix is None:
        print(f"Found {len(stroke_files)} STROKE files. Use --heliostat-prefix to filter:")
        for name, _ in stroke_files:
            print(f"  {name}")
        sys.exit(1)

    helio_name, stroke_path = stroke_files[0]
    print(f"=== FEA Validation: {helio_name} ===")
    print(f"  Result dir:  {result_dir}")
    print(f"  Stroke file: {stroke_path}")

    # ── Load bolt layout ──
    layout_path = ROOT / args.bolt_layout
    if not os.path.isabs(args.bolt_layout):
        layout_path = str(ROOT / args.bolt_layout) if not os.path.isabs(args.bolt_layout) else args.bolt_layout
    if not os.path.exists(layout_path):
        print(f"ERROR: Bolt layout not found: {layout_path}", file=sys.stderr)
        sys.exit(1)
    layout = load_bolt_layout(str(layout_path))
    positions = bolt_positions_from_layout(layout)

    # ── Parse bolt strokes ──
    strokes = parse_stroke_file(stroke_path)
    print(f"  Bolts:       {layout['bolts_x']}x{layout['bolts_z']} = {len(positions)}")
    print(f"  Strokes:     {len(strokes)} values, range [{min(strokes)*1000:.1f}, {max(strokes)*1000:.1f}] mm")

    if len(strokes) != len(positions):
        print(f"  WARNING: {len(strokes)} stroke values but {len(positions)} bolt positions!")

    # ── Output directory ──
    out_dir = args.output_dir
    if out_dir is None:
        out_dir = os.path.join(result_dir, 'fea_validation')
    if not os.path.isabs(out_dir):
        out_dir = str(ROOT / out_dir)
    os.makedirs(out_dir, exist_ok=True)

    print(f"  Angles:      {args.angles}")
    print(f"  Output:      {out_dir}/")
    print(f"  ANSYS:       {args.ansys_exe}")
    if args.dry_run:
        print(f"  DRY RUN:     APDL only, no ANSYS")

    # ── Process each angle ──
    metadata = {
        "heliostat": helio_name,
        "stroke_file": stroke_path,
        "num_bolts": len(positions),
        "bolt_strokes_mm": [round(s * 1000, 3) for s in strokes],
        "max_stroke_mm": round(max(strokes) * 1000, 3),
        "angles": {},
    }

    failed = []
    for ang in args.angles:
        print(f"\n  [{ang:.1f}deg] ", end="", flush=True)

        work_dir = tempfile.mkdtemp(prefix=f"fea_val_{int(ang)}deg_",
                                    dir=str(ROOT / "build"))
        try:
            dat_path, expected_csv = generate_bolt_stroke_apdl(
                layout, ang, positions, strokes, work_dir)

            # Save APDL for inspection
            apdl_dest = os.path.join(out_dir, f"apdl_bolt_stroke_{ang:.1f}deg.dat")
            shutil.copy(dat_path, apdl_dest)

            if args.dry_run:
                print(f"APDL: {apdl_dest} (dry-run)")
                continue

            t0 = time.time()
            ok = run_ansys(dat_path, work_dir, args.ansys_exe)
            if not ok:
                failed.append(ang)
                continue

            if not os.path.exists(expected_csv):
                print(f"MISSING CSV: {expected_csv}", flush=True)
                failed.append(ang)
                continue

            # ── Parse ANSYS output ──
            data = np.loadtxt(expected_csv, delimiter=',', skiprows=1)
            x_fea = data[:, 0]
            y_fea = data[:, 1]
            z_fea = data[:, 2]
            ux = data[:, 3]
            uy = data[:, 4]
            uz = data[:, 5]
            usum = data[:, 6]

            # Deformed coordinates
            x_def = x_fea + ux
            y_def = y_fea + uy
            z_def = z_fea + uz

            elapsed = time.time() - t0
            n_nodes = data.shape[0]
            uy_pv = (uy.max() - uy.min()) * 1000
            usum_pv = (usum.max() - usum.min()) * 1000
            total_pv = np.ptp(usum) * 1000

            print(f"UY_PV={uy_pv:.1f}mm, USUM_PV={usum_pv:.1f}mm, "
                  f"nodes={n_nodes}, {elapsed:.0f}s", flush=True)

            # Save deformed point cloud (full FEA mesh)
            deformed_path = os.path.join(out_dir, f"fea_deformed_{ang:.1f}deg.txt")
            with open(deformed_path, 'w') as f:
                f.write("# x_def y_def z_def ux uy uz usum\n")
                for i in range(n_nodes):
                    f.write(f"{x_def[i]:.9f} {y_def[i]:.9f} {z_def[i]:.9f} "
                            f"{ux[i]:.9f} {uy[i]:.9f} {uz[i]:.9f} {usum[i]:.9f}\n")

            # Save coordinates-only point cloud
            pc_path = os.path.join(out_dir, f"fea_pointcloud_{ang:.1f}deg.txt")
            with open(pc_path, 'w') as f:
                f.write("# x y z (deformed plate mid-surface)\n")
                for i in range(n_nodes):
                    f.write(f"{x_def[i]:.9f} {y_def[i]:.9f} {z_def[i]:.9f}\n")

            metadata["angles"][str(ang)] = {
                "n_nodes": int(n_nodes),
                "uy_pv_mm": float(uy_pv),
                "usum_pv_mm": float(usum_pv),
                "uy_min_mm": float(uy.min() * 1000),
                "uy_max_mm": float(uy.max() * 1000),
                "elapsed_s": round(elapsed, 1),
            }

            # Save CSV copy in output dir
            csv_dest = os.path.join(out_dir, f"node_dump_{ang:.1f}deg.csv")
            shutil.copy(expected_csv, csv_dest)

        finally:
            if not args.keep_temp:
                shutil.rmtree(work_dir, ignore_errors=True)

    # ── Save metadata ──
    metadata["failed_angles"] = [float(f) for f in failed]
    meta_path = os.path.join(out_dir, "fea_metadata.json")
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    # ── Summary ──
    n_ok = len(args.angles) - len(failed)
    print(f"\n=== FEA Validation done: {n_ok}/{len(args.angles)} angles ===")
    if failed:
        print(f"  Failed: {failed}")
    print(f"\n  Output: {out_dir}/")
    for f in sorted(os.listdir(out_dir)):
        fpath = os.path.join(out_dir, f)
        if os.path.isfile(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            print(f"    {f}  ({size_kb:.1f} KB)")

    # ── Proxy-vs-FEA comparison (if requested) ──
    if args.compare and n_ok > 0:
        print(f"\n{'='*60}")
        print(f"Proxy vs FEA Comparison")
        print(f"{'='*60}")
        compare_dir = os.path.join(out_dir, 'comparison')
        all_metrics = []
        for ang in args.angles:
            if ang in failed:
                continue
            csv_path = os.path.join(out_dir, f"node_dump_{ang:.1f}deg.csv")
            if not os.path.exists(csv_path):
                continue
            label = f"{helio_name}, {ang:.1f}deg, NLGEOM-ON"
            m = run_comparison(csv_path, ang, stroke_path, compare_dir,
                               label=label, influence_dir=args.influence_dir)
            all_metrics.append(m)

        if all_metrics:
            summary_path = os.path.join(compare_dir, 'comparison_summary.json')
            with open(summary_path, 'w') as f:
                json.dump(all_metrics, f, indent=2)
            print(f"\n  Comparison summary: {summary_path}")

    # ── Standalone comparison mode (--compare-csv) ──
    if args.compare_csv:
        print(f"\n{'='*60}")
        print(f"Standalone Proxy vs FEA Comparison")
        print(f"{'='*60}")
        compare_dir = args.output_dir
        if compare_dir is None:
            compare_dir = os.path.join(os.path.dirname(args.compare_csv[0]), 'comparison')
        all_metrics = []
        for csv_path in args.compare_csv:
            # Parse angle from filename (handles "295deg"=29.5°, "29.5deg", "585deg"=58.5°, etc.)
            import re
            ang_match = re.search(r'(\d+\.?\d*)deg', os.path.basename(csv_path))
            ang = float(ang_match.group(1)) if ang_match else 29.5
            # If angle > 90, it's likely in tenths of degrees (e.g., 295 → 29.5)
            if ang > 90:
                ang = ang / 10.0
            label = args.compare_label
            if label is None:
                base = os.path.basename(csv_path).replace('.csv', '')
                label = f"{base}"
            m = run_comparison(csv_path, ang, stroke_path, compare_dir,
                               label=label, influence_dir=args.influence_dir)
            all_metrics.append(m)

        if all_metrics:
            summary_path = os.path.join(compare_dir, 'comparison_summary.json')
            with open(summary_path, 'w') as f:
                json.dump(all_metrics, f, indent=2)
            # Print summary table
            print(f"\n  {'='*70}")
            print(f"  Comparison Summary")
            print(f"  {'='*70}")
            print(f"  {'Label':<35s} {'RMS(mm)':>8s} {'R2':>8s} {'shape_corr':>10s} {'PV_ratio':>8s}")
            print(f"  {'-'*70}")
            for m in all_metrics:
                print(f"  {m['label']:<35s} {m['rms_mm']:8.3f} {m['r2']:8.4f} {m['shape_corr']:10.4f} {m['pv_ratio']:8.4f}")
            print(f"  {'='*70}")
            print(f"\n  Summary: {summary_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Proxy vs FEA comparison pipeline
# ══════════════════════════════════════════════════════════════════════════════

def load_influence_functions(data_dir, grid_size=32):
    """Load TPS influence functions from data_proxy/*.bin files.

    Returns:
        phi:   [NB, GS*GS] float32 — displacement influence
        phi_u: [NB, GS*GS] float32 — ∂φ/∂u derivative
        phi_v: [NB, GS*GS] float32 — ∂φ/∂v derivative
        NB: number of bolts
    """
    def _load(name):
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing influence data: {path}. Run generate_proxy_model.py tps first.")
        return np.fromfile(path, dtype=np.float32)

    phi_raw   = _load('influence_phi.bin')
    phi_u_raw = _load('influence_phi_u.bin')
    phi_v_raw = _load('influence_phi_v.bin')

    n_grid = grid_size * grid_size
    NB = len(phi_raw) // n_grid
    if NB * n_grid != len(phi_raw):
        raise ValueError(f"influence_phi.bin size {len(phi_raw)} not divisible by grid_size²={n_grid}")

    phi   = phi_raw.reshape(NB, n_grid)
    phi_u = phi_u_raw.reshape(NB, n_grid)
    phi_v = phi_v_raw.reshape(NB, n_grid)
    return phi, phi_u, phi_v, NB


def load_gravity_bins(data_dir):
    """Load 20-bin gravity data and angle list from data_proxy/.

    Returns:
        gravity_bins: [20, GS*GS] float32 — raw UY displacement per bin
        gravity_angles: [20] float — angle in degrees
        GS: grid size
    """
    meta_path = os.path.join(data_dir, 'gravity_angles.json')
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Missing {meta_path}")
    with open(meta_path) as f:
        meta = json.load(f)

    angles = sorted([float(k) for k in meta['angles'].keys()])
    GS = meta['grid_size']
    n_grid = GS * GS

    bins = np.zeros((len(angles), n_grid), dtype=np.float32)
    for i, ang in enumerate(angles):
        ang_int = int(ang) if ang == int(ang) else ang
        path = os.path.join(data_dir, f'gravity_{ang_int}deg.bin')
        if os.path.exists(path):
            raw = np.fromfile(path, dtype=np.float32)
            if len(raw) == n_grid:
                bins[i] = raw
            else:
                print(f"  WARN: gravity_{ang_int}deg.bin has {len(raw)} floats, expected {n_grid}")
        else:
            print(f"  WARN: {path} not found, using zeros")

    return bins, np.array(angles), GS


def interpolate_gravity(angle_deg, gravity_bins, gravity_angles):
    """Bilinear interpolation of gravity at target angle.

    Matches shader-side sampleGravityUY() in bolt_common.slang.

    Args:
        angle_deg: target tilt angle in degrees
        gravity_bins: [N_bins, GS*GS] float32
        gravity_angles: [N_bins] sorted angles in degrees

    Returns:
        gravity: [GS*GS] float32 — interpolated gravity UY field
    """
    n_bins = len(gravity_angles)
    # Find bracket
    lo, hi = 0, n_bins - 1
    for i in range(n_bins - 1):
        if gravity_angles[i] <= angle_deg <= gravity_angles[i + 1]:
            lo, hi = i, i + 1
            break
    if angle_deg <= gravity_angles[0]:
        lo, hi = 0, 0
    if angle_deg >= gravity_angles[-1]:
        lo, hi = n_bins - 1, n_bins - 1

    if lo == hi:
        return gravity_bins[lo].copy()

    t = (angle_deg - gravity_angles[lo]) / (gravity_angles[hi] - gravity_angles[lo] + 1e-30)
    return (1.0 - t) * gravity_bins[lo] + t * gravity_bins[hi]


def compute_proxy_surface(bolt_strokes, phi, gravity):
    """Compute TPS proxy surface with gravity.

    w(x,z) = gravity(x,z) + Σ_b h_b · φ_b(x,z)

    Args:
        bolt_strokes: [NB] float — bolt stroke heights (m)
        phi: [NB, GS*GS] float32 — influence functions
        gravity: [GS*GS] float32 — gravity UY field

    Returns:
        w_proxy: [GS*GS] float32 — proxy surface displacement (m)
    """
    w = gravity.astype(np.float64).copy()
    for b in range(len(bolt_strokes)):
        if abs(bolt_strokes[b]) > 1e-12:
            w += bolt_strokes[b] * phi[b].astype(np.float64)
    return w


def fea_csv_to_plate_local(csv_path, angle_deg):
    """Load FEA 7-col CSV and transform to plate-local coordinates.

    Plate normal (global) = (0, cosθ, +sinθ), matching both GUI Workbench
    and the APDL generated by generate_bolt_stroke_apdl().

    Coordinate mapping:
      z_local = z_global / cosθ     (un-project tilted Z to flat-plate length)
      w_fea   = uy·cosθ + uz·sinθ   (project displacement to plate normal)

    Args:
        csv_path: path to node_dump_*deg.csv (7-col: x,y,z,ux,uy,uz,usum)
        angle_deg: plate tilt angle in degrees

    Returns:
        x_local:  [N] float — plate-local X (same as global X)
        z_local:  [N] float — plate-local Z (un-projected)
        w_fea:    [N] float — plate-normal displacement (m)
    """
    data = np.loadtxt(csv_path, delimiter=',', skiprows=1)
    theta = np.radians(angle_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)

    x_global = data[:, 0]
    z_global = data[:, 2]
    uy = data[:, 4]
    uz = data[:, 5]

    x_local = x_global
    z_local = z_global / max(cos_t, 1e-6)
    # Plate normal = (0, cosθ, +sinθ) in global
    w_fea = uy * cos_t + uz * sin_t

    return x_local, z_local, w_fea


def interpolate_fea_to_grid(x_local, z_local, w_fea, grid_size=32):
    """Interpolate scattered FEA displacement to render grid.

    Args:
        x_local, z_local: [N] plate-local node coordinates (m)
        w_fea: [N] plate-normal displacement (m)
        grid_size: render grid resolution

    Returns:
        w_grid: [GS, GS] interpolated displacement on render grid
        Xg, Zg: [GS, GS] grid coordinate arrays
    """
    from scipy.interpolate import griddata as gd

    # Pixel-centered grid, matching shader's gridToPlate() and generate_proxy_model.py
    W, L = 12.84, 9.45
    u = (np.arange(grid_size) + 0.5) / grid_size
    x_grid = (u - 0.5) * W
    z_grid = (u - 0.5) * L
    Xg, Zg = np.meshgrid(x_grid, z_grid)

    w_grid = gd((x_local, z_local), w_fea, (Xg, Zg), method='linear')

    # Fill NaNs (outside convex hull) with nearest-neighbor
    nan_mask = np.isnan(w_grid)
    if nan_mask.any():
        w_nn = gd((x_local, z_local), w_fea, (Xg, Zg), method='nearest')
        w_grid[nan_mask] = w_nn[nan_mask]
        print(f"    Interpolation: {nan_mask.sum()}/{grid_size*grid_size} NaN points filled with nearest")

    return w_grid, Xg, Zg


def compute_metrics(w_proxy, w_fea):
    """Compute comparison metrics between proxy and FEA surfaces.

    Both inputs are de-meaned before comparison (piston removal).

    Args:
        w_proxy: [GS, GS] or [N] proxy surface (m)
        w_fea:   [GS, GS] or [N] FEA surface (m)

    Returns:
        dict with rms_mm, r2, shape_corr, pv_proxy_mm, pv_fea_mm, pv_ratio
    """
    w_p = np.asarray(w_proxy, dtype=np.float64).ravel()
    w_f = np.asarray(w_fea, dtype=np.float64).ravel()

    # De-mean
    w_p_dm = w_p - np.mean(w_p)
    w_f_dm = w_f - np.mean(w_f)

    # Residual
    residual = w_p_dm - w_f_dm
    rms = np.sqrt(np.mean(residual ** 2)) * 1000  # mm

    # R2
    sst = np.sum(w_f_dm ** 2)
    r2 = 1.0 - np.sum(residual ** 2) / max(sst, 1e-30)

    # Shape correlation (Pearson r)
    num = np.sum(w_p_dm * w_f_dm)
    den = np.sqrt(np.sum(w_p_dm ** 2) * np.sum(w_f_dm ** 2))
    shape_corr = num / max(den, 1e-30)

    # PV
    pv_proxy = np.ptp(w_p_dm) * 1000
    pv_fea = np.ptp(w_f_dm) * 1000
    pv_ratio = pv_proxy / max(pv_fea, 1e-10)

    return {
        'rms_mm': float(rms),
        'r2': float(r2),
        'shape_corr': float(shape_corr),
        'pv_proxy_mm': float(pv_proxy),
        'pv_fea_mm': float(pv_fea),
        'pv_ratio': float(pv_ratio),
    }


def _bolt_positions_7x5():
    """Return (bx, bz) arrays for the standard 7×5 bolt layout (35 bolts)."""
    nx, nz = 7, 5
    m = 0.08
    pW, pL = 12.84, 9.45
    bx, bz = [], []
    for j in range(nz):
        v = m + (1.0 - 2.0 * m) * j / (nz - 1)
        for i in range(nx):
            u = m + (1.0 - 2.0 * m) * i / (nx - 1)
            bx.append((u - 0.5) * pW)
            bz.append((v - 0.5) * pL)
    return np.array(bx), np.array(bz)


def generate_comparison_plot(w_proxy, w_fea, Xg, Zg, angle_deg, label, out_dir):
    """Generate side-by-side comparison figure: proxy, FEA, residual, cross-section.

    Args:
        w_proxy: [GS, GS] proxy surface (m)
        w_fea:   [GS, GS] FEA surface (m)
        Xg, Zg:  [GS, GS] grid coordinates
        angle_deg: tilt angle
        label:   string label for title (e.g. "NLGEOM-ON, 29.5°")
        out_dir: output directory
    """
    metrics = compute_metrics(w_proxy, w_fea)

    # De-mean
    w_p_dm = w_proxy - np.mean(w_proxy)
    w_f_dm = w_fea - np.mean(w_fea)
    residual = w_p_dm - w_f_dm

    rms, r2, sc = metrics['rms_mm'], metrics['r2'], metrics['shape_corr']
    pv_p, pv_f = metrics['pv_proxy_mm'], metrics['pv_fea_mm']

    # Bolt positions for overlay
    bx, bz = _bolt_positions_7x5()

    fig = plt.figure(figsize=(20, 10))
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35,
                  width_ratios=[1, 1, 1], height_ratios=[1, 0.7])

    vm_surf = max(abs(w_p_dm).max(), abs(w_f_dm).max()) * 1000
    vm_err = max(abs(residual).max() * 1000, 0.01)
    GS = w_proxy.shape[0]

    # Row 1: Proxy | FEA | Residual
    titles = [
        f'TPS Proxy\nPV={pv_p:.2f}mm',
        f'FEA ({label})\nPV={pv_f:.2f}mm',
        f'Residual (Proxy − FEA)\nRMS={rms:.3f}mm  R2={r2:.4f}  shape_corr={sc:.4f}'
    ]
    data_list = [w_p_dm * 1000, w_f_dm * 1000, residual * 1000]
    cmaps = ['RdYlBu_r', 'RdYlBu_r', 'RdBu_r']
    vmins = [(-vm_surf, vm_surf), (-vm_surf, vm_surf), (-vm_err, vm_err)]

    for col in range(3):
        ax = fig.add_subplot(gs[0, col])
        im = ax.pcolormesh(Xg, Zg, data_list[col], cmap=cmaps[col], shading='auto',
                           vmin=vmins[col][0], vmax=vmins[col][1])
        ax.set_title(titles[col], fontsize=10, fontweight='bold')
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')
        # Bolt positions on proxy and FEA subplots
        if col < 2:
            ax.scatter(bx, bz, c='black', s=12, marker='o', zorder=5,
                      edgecolors='white', linewidths=0.3)

    # Row 2 left: center cross-section
    ax_xs = fig.add_subplot(gs[1, 0])
    mid_row = GS // 2
    x_1d = np.linspace(-12.84 / 2, 12.84 / 2, GS)
    ax_xs.plot(x_1d, w_p_dm[mid_row, :] * 1000, 'b-', lw=2, label='TPS Proxy')
    ax_xs.plot(x_1d, w_f_dm[mid_row, :] * 1000, 'r--', lw=1.5, label='FEA')
    ax_xs.set_xlabel('x (m)'); ax_xs.set_ylabel('w (mm)')
    ax_xs.set_title(f'Center cross-section (z=0)', fontsize=10, fontweight='bold')
    ax_xs.legend(fontsize=8); ax_xs.grid(True, alpha=0.3)

    # Row 2 middle: per-row RMS
    ax_rms = fig.add_subplot(gs[1, 1])
    z_1d = np.linspace(-9.45 / 2, 9.45 / 2, GS)
    rms_per_row = np.array([np.sqrt(np.mean(residual[i, :] ** 2)) * 1000 for i in range(GS)])
    ax_rms.plot(z_1d, rms_per_row, 'b-o', ms=3, label=f'Mean={rms_per_row.mean():.2f}mm')
    ax_rms.fill_between(z_1d, 0, rms_per_row, alpha=0.15, color='blue')
    ax_rms.axhline(y=2.0, color='gray', ls='--', alpha=0.5, label='2mm')
    ax_rms.set_xlabel('z (m)'); ax_rms.set_ylabel('RMS error (mm)')
    ax_rms.set_title('Per-row RMS error', fontsize=10, fontweight='bold')
    ax_rms.legend(fontsize=8); ax_rms.grid(True, alpha=0.3)

    # Row 2 right: metrics table
    ax_tbl = fig.add_subplot(gs[1, 2])
    ax_tbl.axis('off')
    tbl_text = (
        f"Metrics — {label}\n"
        f"{'='*45}\n"
        f"  RMS error:       {rms:.4f} mm\n"
        f"  R-squared:       {r2:.6f}\n"
        f"  Shape corr:      {sc:.6f}\n"
        f"  PV ratio:        {metrics['pv_ratio']:.4f}\n"
        f"  Proxy PV:        {pv_p:.2f} mm\n"
        f"  FEA PV:          {pv_f:.2f} mm\n"
        f"{'='*45}\n"
    )
    ax_tbl.text(0.05, 0.95, tbl_text, transform=ax_tbl.transAxes,
                fontsize=9, fontfamily='monospace', va='top',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    fig.suptitle(f'Proxy Model vs FEA: {label}',
                 fontsize=13, fontweight='bold', y=0.98)

    safe_label = label.replace(' ', '_').replace(',', '').replace('°', 'deg')
    png_path = os.path.join(out_dir, f'comparison_{safe_label}.png')
    plt.savefig(png_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"    Plot saved: {png_path}")

    return metrics


def run_comparison(fea_csv_path, angle_deg, bolt_strokes_path, out_dir,
                   label=None, influence_dir='data_proxy'):
    """Full comparison pipeline: FEA CSV → proxy surface → metrics → plots.

    Args:
        fea_csv_path: path to FEA node_dump_*deg.csv (7-col)
        angle_deg: tilt angle
        bolt_strokes_path: path to *_STROKE_bolts.txt
        out_dir: output directory for plots and metrics JSON
        label: display label (auto-generated if None)
        influence_dir: path to data_proxy/

    Returns:
        metrics dict
    """
    if label is None:
        base = os.path.basename(fea_csv_path)
        label = f"{base}, {angle_deg}°"

    print(f"\n  Comparing: {label}")
    print(f"    FEA CSV: {fea_csv_path}")
    print(f"    Bolts:   {bolt_strokes_path}")

    # ── Load bolt strokes ──
    strokes = parse_stroke_file(bolt_strokes_path)
    strokes = np.array(strokes, dtype=np.float64)
    print(f"    Strokes: [{strokes.min()*1000:.1f}, {strokes.max()*1000:.1f}] mm")

    # ── Load influence data ──
    phi, phi_u, phi_v, NB = load_influence_functions(influence_dir)
    if len(strokes) != NB:
        print(f"    WARN: {len(strokes)} strokes vs {NB} influence functions")
        NB = min(len(strokes), NB)

    # ── Load gravity and interpolate ──
    gravity_bins, gravity_angles, GS = load_gravity_bins(influence_dir)
    gravity = interpolate_gravity(angle_deg, gravity_bins, gravity_angles)
    print(f"    Gravity PV: {np.ptp(gravity)*1000:.2f} mm")

    # ── Compute proxy surface ──
    w_proxy_flat = compute_proxy_surface(strokes[:NB], phi[:NB], gravity)
    w_proxy = w_proxy_flat.reshape(GS, GS)

    # ── Load FEA and transform to plate-local ──
    x_local, z_local, w_fea_scatter = fea_csv_to_plate_local(fea_csv_path, angle_deg)
    print(f"    FEA nodes: {len(x_local)}, w_fea PV: {np.ptp(w_fea_scatter)*1000:.2f} mm")

    # ── Interpolate FEA to render grid ──
    w_fea_grid, Xg, Zg = interpolate_fea_to_grid(x_local, z_local, w_fea_scatter, GS)
    print(f"    FEA grid PV: {np.ptp(w_fea_grid)*1000:.2f} mm")

    # ── Compare ──
    metrics = compute_metrics(w_proxy, w_fea_grid)

    # ── Plot ──
    os.makedirs(out_dir, exist_ok=True)
    generate_comparison_plot(w_proxy, w_fea_grid, Xg, Zg, angle_deg, label, out_dir)

    # ── Save metrics JSON ──
    safe_label = label.replace(' ', '_').replace(',', '').replace('°', 'deg')
    metrics_path = os.path.join(out_dir, f'metrics_{safe_label}.json')
    metrics['label'] = label
    metrics['angle_deg'] = angle_deg
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)

    # ── Print summary ──
    print(f"    Results: RMS={metrics['rms_mm']:.3f}mm, R2={metrics['r2']:.4f}, "
          f"shape_corr={metrics['shape_corr']:.4f}, "
          f"PV_ratio={metrics['pv_ratio']:.4f}")

    return metrics


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    main()
