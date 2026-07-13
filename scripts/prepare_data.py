#!/usr/bin/env python3
"""
One-shot data preparation for the diff_helio optimization pipeline.

Generates all required .bin files:
  1. TPS influence functions  (scripts/generate_tps_influence.py)
  2. Gravity angle bins:
     a. From pre-existing FEA CSV     (scripts/train_residual/precompute_gravity_bins.py)
     b. From ANSYS MAPDL batch        (scripts/ansys_gravity.py)  [--use-ansys]

Usage:
  # Default (32x32, 35 bolts 7x5, pre-existing 10-bin gravity)
  python scripts/prepare_data.py

  # Custom bolt layout (reads bolt positions from JSON)
  python scripts/prepare_data.py --bolt-layout configs/bolt_layouts/6x6.json

  # With ANSYS: generate 20-bin gravity from scratch
  python scripts/prepare_data.py --use-ansys --bolt-layout configs/bolt_layouts/7x5_default.json

  # With ANSYS + custom angles
  python scripts/prepare_data.py --use-ansys --gravity-angles 10 15 20 25 30 35 40 45 50 55 60 65 70 75 80

Output: <output-dir>/
  influence_phi.bin, influence_phi_u.bin, influence_phi_v.bin
  influence_kxx.bin, influence_kzz.bin, influence_kxz.bin
  gravity_{angle}deg.bin (for each angle)
  gravity_angles.json
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Defaults (match CURRENT 32×32 pipeline) ──
DEFAULT_GRID = 32
DEFAULT_BOLTS_X = 7
DEFAULT_BOLTS_Z = 5
DEFAULT_MARGIN = 0.08
DEFAULT_GRAVITY_ANGLES = [0, 12, 22, 30, 35, 45, 52, 60, 67, 75]
DEFAULT_ANSYS_ANGLES = [10, 14, 18, 22, 26, 30, 34, 38, 42, 46,
                        50, 54, 58, 62, 66, 70, 73, 76, 78, 80]
DEFAULT_GRAVITY_SOURCE = "train_data/zero_heights_ON"
DEFAULT_OUTPUT = "data_vsm_mnvn_tik32"
DEFAULT_TPS_REG = 1e-6


def run_tps_influence(output_dir, grid_size, bolts_x, bolts_z, margin, reg):
    """Generate TPS influence functions by calling generate_tps_influence.py."""
    script = ROOT / "scripts" / "generate_tps_influence.py"

    cmd = [
        sys.executable, str(script),
        "--output", str(output_dir),
        "--grid-size", str(grid_size),
        "--bolts-x", str(bolts_x),
        "--bolts-z", str(bolts_z),
        "--margin", str(margin),
        "--reg", str(reg),
    ]
    print(f"\n{'='*60}")
    print(f"Step 1/2: TPS Influence Functions")
    print(f"{'='*60}")
    print(f"  Grid: {grid_size}x{grid_size}  Bolts: {bolts_x}x{bolts_z}  Margin: {margin}")
    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: TPS influence generation failed", file=sys.stderr)
        sys.exit(1)
    print("  OK")


def run_gravity_bins(output_dir, grid_size, source_dir, angles):
    """Generate gravity bins by calling precompute_gravity_bins.py."""
    script = ROOT / "scripts" / "train_residual" / "precompute_gravity_bins.py"

    cmd = [
        sys.executable, str(script),
        "--output-dir", str(output_dir),
        "--grid-size", str(grid_size),
        "--source-dir", str(source_dir),
        "--angles", *[str(a) for a in angles],
    ]
    print(f"\n{'='*60}")
    print(f"Step 2/2: Gravity Bins")
    print(f"{'='*60}")
    print(f"  Grid: {grid_size}x{grid_size}  Angles: {angles}")
    print(f"  Source: {source_dir}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: Gravity bin generation failed", file=sys.stderr)
        sys.exit(1)
    print("  OK")


def run_gravity_bins_ansys(output_dir, grid_size, bolt_layout, angles, ansys_exe=None):
    """Generate gravity bins via ANSYS MAPDL batch."""
    script = ROOT / "scripts" / "ansys_gravity.py"
    bolt_layout_path = ROOT / bolt_layout if not bolt_layout.endswith('.json') else bolt_layout
    if not str(bolt_layout_path).endswith('.json'):
        bolt_layout_path = ROOT / "configs" / "bolt_layouts" / f"{bolt_layout}.json"

    cmd = [
        sys.executable, str(script),
        "--bolt-layout", str(bolt_layout_path),
        "--output-dir", str(output_dir),
        "--grid-size", str(grid_size),
        "--angles", *[str(a) for a in angles],
    ]
    if ansys_exe:
        cmd.extend(["--ansys-exe", ansys_exe])

    print(f"\n{'='*60}")
    print(f"Step 2/2: Gravity Bins (ANSYS MAPDL)")
    print(f"{'='*60}")
    print(f"  Bolt layout: {bolt_layout_path}")
    print(f"  Grid: {grid_size}x{grid_size}  Angles: {len(angles)} bins ({angles[0]}-{angles[-1]}deg)")
    print(f"  This will run {len(angles)} ANSYS simulations (~1-2 min each)")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: ANSYS gravity generation failed", file=sys.stderr)
        sys.exit(1)
    print("  OK")


def validate_output(output_dir, grid_size, bolts_x, bolts_z, gravity_angles):
    """Quick sanity check on generated files."""
    import numpy as np
    n_bolts = bolts_x * bolts_z
    n_grid = grid_size * grid_size
    errors = []

    # Check influence files
    for name in ["influence_phi", "influence_phi_u", "influence_phi_v",
                 "influence_kxx", "influence_kzz", "influence_kxz"]:
        path = os.path.join(output_dir, f"{name}.bin")
        if not os.path.exists(path):
            errors.append(f"MISSING: {path}")
            continue
        data = np.fromfile(path, dtype=np.float32)
        expected = n_bolts * n_grid
        if len(data) != expected:
            errors.append(f"SIZE: {path} has {len(data)}, expected {expected}")
    if errors:
        print("\nVALIDATION ERRORS:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    # Unit decomposition check
    phi = np.fromfile(os.path.join(output_dir, "influence_phi.bin"),
                      dtype=np.float32).reshape(n_bolts, n_grid)
    unit_sum = phi.sum(axis=0)
    pv = unit_sum.max() - unit_sum.min()
    print(f"\n  Validation OK: {len(phi)} influence functions, "
          f"unit decomp PV={pv:.2e}")
    if pv > 1e-4:
        print(f"  WARNING: unit decomposition PV={pv:.2e} > 1e-4!")

    # Check gravity bins
    for ang in gravity_angles:
        path = os.path.join(output_dir, f"gravity_{ang}deg.bin")
        if not os.path.exists(path):
            errors.append(f"MISSING: {path}")
        else:
            data = np.fromfile(path, dtype=np.float32)
            if len(data) != n_grid:
                errors.append(f"SIZE: {path} has {len(data)}, expected {n_grid}")
    if errors:
        print("GRAVITY ERRORS:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    # gravity_angles.json
    meta_path = os.path.join(output_dir, "gravity_angles.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print(f"  Gravity bins: {len(meta.get('angles',{}))} angles, grid={meta.get('grid_size')}")
    print(f"  All checks passed.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT,
                   help=f"Output directory (default: {DEFAULT_OUTPUT})")
    p.add_argument("--grid-size", type=int, default=DEFAULT_GRID,
                   help=f"Render grid resolution (default: {DEFAULT_GRID})")
    p.add_argument("--bolts", default=f"{DEFAULT_BOLTS_X}x{DEFAULT_BOLTS_Z}",
                   help=f"Bolt grid 'NxMz' (used if --bolt-layout not set)")
    p.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                   help=f"Bolt margin fraction (used if --bolt-layout not set)")
    p.add_argument("--bolt-layout", default=None,
                   help="Path to bolt layout JSON (overrides --bolts/--margin)")
    p.add_argument("--reg", type=float, default=DEFAULT_TPS_REG,
                   help=f"TPS regularization lambda (default: {DEFAULT_TPS_REG})")
    p.add_argument("--gravity-angles", type=int, nargs="+", default=None,
                   help="Gravity FEA angles in degrees")
    p.add_argument("--gravity-source", default=DEFAULT_GRAVITY_SOURCE,
                   help=f"Dir with node_dump_{{ang}}deg.csv (pre-existing mode)")
    p.add_argument("--use-ansys", action="store_true",
                   help="Generate gravity bins via ANSYS MAPDL (requires ANSYS license)")
    p.add_argument("--ansys-exe", default=None,
                   help="Path to ANSYS MAPDL executable")
    p.add_argument("--influence-only", action="store_true",
                   help="Only generate influence functions")
    p.add_argument("--gravity-only", action="store_true",
                   help="Only generate gravity bins")
    p.add_argument("--no-validate", action="store_true",
                   help="Skip validation")
    args = p.parse_args()

    # ── Bolt layout resolution ──
    if args.bolt_layout:
        layout_path = ROOT / args.bolt_layout
        if not layout_path.exists():
            print(f"ERROR: Bolt layout not found: {layout_path}", file=sys.stderr)
            sys.exit(1)
        with open(layout_path) as f:
            layout_cfg = json.load(f)
        bolts_x = layout_cfg["bolts_x"]
        bolts_z = layout_cfg["bolts_z"]
        margin = layout_cfg.get("margin", DEFAULT_MARGIN)
    else:
        bolts_parts = args.bolts.split("x")
        bolts_x = int(bolts_parts[0])
        bolts_z = int(bolts_parts[1])
        margin = args.margin

    # ── Gravity angles ──
    if args.gravity_angles:
        gravity_angles = args.gravity_angles
    elif args.use_ansys:
        gravity_angles = DEFAULT_ANSYS_ANGLES
    else:
        gravity_angles = DEFAULT_GRAVITY_ANGLES

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Data Preparation ===")
    print(f"  Output:    {output_dir}")
    print(f"  Grid:      {args.grid_size}x{args.grid_size}")
    print(f"  Bolts:     {bolts_x}x{bolts_z} ({bolts_x*bolts_z} total), margin={args.margin}")
    print(f"  Gravity:   {len(args.gravity_angles)} angles from {args.gravity_source}")
    print(f"  TPS reg:   {args.reg}")

    if not args.gravity_only:
        run_tps_influence(str(output_dir), args.grid_size,
                         bolts_x, bolts_z, args.margin, args.reg)

    if not args.influence_only:
        if args.use_ansys:
            run_gravity_bins_ansys(str(output_dir), args.grid_size,
                                   args.bolt_layout or "7x5_default",
                                   gravity_angles, args.ansys_exe)
        else:
            run_gravity_bins(str(output_dir), args.grid_size,
                            args.gravity_source, gravity_angles)

    if not args.no_validate:
        print(f"\n{'='*60}")
        print(f"Validation")
        print(f"{'='*60}")
        validate_output(str(output_dir), args.grid_size, bolts_x, bolts_z,
                       args.gravity_angles)

    print(f"\n=== Data ready in {output_dir} ===")
    print(f"  Next: ./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_300iter.json")


if __name__ == "__main__":
    main()
