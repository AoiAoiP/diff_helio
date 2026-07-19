#!/usr/bin/env python3
"""
Pre-compute FEA-direct (interpolation) gravity fields (local-plate UY) at the
known FEA tilt angles, for the C++ GPU pipeline.

For each angle θ:
  1. Load <source-dir>/node_dump_{θ}deg.csv  (zero-bolt FEA, NLGEOM-ON)
  2. Un-compress tilted Z:  z_flat = z_fea / cosθ   (θ=0 kept as-is)
  3. Interpolate scattered UY onto the flat-plate GS×GS grid (linear + nearest fill)
  4. Store as local-plate UY (m), row-major

Output: <output-dir>/gravity_{θ}deg.bin   (float32, GS×GS, row-major)
        <output-dir>/gravity_angles.json    (metadata)

The GPU pipeline lerps between the two bracketing angle bins at run time
(bolt_common.slang: sampleGravityUY).

Defaults match the CURRENT 32×32 pipeline. Override --grid-size / --source-dir /
--output-dir to regenerate at another resolution or from another FEA set (e.g. a
future NLGEOM-OFF zero_heights_OFF for a pure-linear gravity reference).

Usage:
  python scripts/train_residual/precompute_gravity_bins.py                    # 32x32, ON, tik32
  python scripts/train_residual/precompute_gravity_bins.py --grid-size 25 \
      --output-dir data_vsm_mnvn_tik25                                        # 25x25 rebuild
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import griddata as gd

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── plate geometry ──
W, L = 12.84, 9.45


def main():
    base_dir = Path(__file__).resolve().parent.parent.parent

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--grid-size', type=int, default=32,
                    help='render grid resolution GS (default 32, matches current pipeline)')
    ap.add_argument('--source-dir', default='train_data/zero_heights_ON',
                    help='dir holding node_dump_{ang}deg.csv (default zero_heights_ON, NLGEOM-ON)')
    ap.add_argument('--output-dir', default='data_proxy',
                    help='dir to write gravity_{ang}deg.bin + gravity_angles.json')
    ap.add_argument('--angles', type=int, nargs='+', default=[0, 30, 45, 60, 75],
                    help='FEA tilt angles to process (default 0 30 45 60 75)')
    args = ap.parse_args()

    GS = args.grid_size
    src_dir = base_dir / args.source_dir
    out_dir = base_dir / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # flat-plate evaluation grid
    u = np.linspace(0, 1, GS)
    Ug, Vg = np.meshgrid(u, u)
    X_flat = (Ug - 0.5) * W
    Z_flat = (Vg - 0.5) * L

    print(f"Grid: {GS}x{GS}   source: {src_dir}   output: {out_dir}")
    metadata = {"angles": {}, "grid_size": GS, "plate_W_m": W, "plate_L_m": L}

    for ang in args.angles:
        cos_th = np.cos(np.deg2rad(ang))
        csv_path = src_dir / f'node_dump_{ang}deg.csv'
        if not csv_path.exists():
            print(f"  WARN theta={ang}deg: {csv_path} not found -- skipped")
            continue

        fea_raw = np.loadtxt(str(csv_path), delimiter=',', skiprows=1)
        # 7-col: x,y,z,ux,uy,uz,usum   |   3-col: x,z,uy
        if fea_raw.shape[1] >= 7:
            x_fea, z_fea_tilt, uy_fea = fea_raw[:, 0], fea_raw[:, 2], fea_raw[:, 4]
        else:
            x_fea, z_fea_tilt, uy_fea = fea_raw[:, 0], fea_raw[:, 1], fea_raw[:, 2]

        # un-compress tilted Z back to flat-plate length
        z_fea_flat = z_fea_tilt if ang == 0 else z_fea_tilt / cos_th

        in_plate = (np.abs(x_fea) <= W / 2 + 0.02) & (np.abs(z_fea_flat) <= L / 2 + 0.02)
        grid = gd((x_fea[in_plate], z_fea_flat[in_plate]), uy_fea[in_plate],
                  (X_flat.ravel(), Z_flat.ravel()), method='linear').reshape(GS, GS)

        nan_mask = np.isnan(grid)
        n_nan = int(nan_mask.sum())
        if n_nan:
            near = gd((x_fea[in_plate], z_fea_flat[in_plate]), uy_fea[in_plate],
                      (X_flat.ravel(), Z_flat.ravel()), method='nearest').reshape(GS, GS)
            grid[nan_mask] = near[nan_mask]

        out_path = out_dir / f'gravity_{ang}deg.bin'
        grid.astype(np.float32).ravel().tofile(str(out_path))

        metadata["angles"][str(ang)] = {
            "cos_theta": float(cos_th),
            "pv_mm": float(np.ptp(grid) * 1000),
            "min_mm": float(grid.min() * 1000),
            "max_mm": float(grid.max() * 1000),
            "nan_filled": n_nan,
            "source": f"{args.source_dir}/node_dump_{ang}deg.csv",
        }
        print(f"  theta={ang}deg: PV={np.ptp(grid)*1000:.1f}mm  "
              f"range=[{grid.min()*1000:.1f},{grid.max()*1000:.1f}]mm  "
              f"NaN={n_nan}  ->  gravity_{ang}deg.bin")

    meta_path = out_dir / 'gravity_angles.json'
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"\nMetadata: {meta_path}\nDone.")


if __name__ == '__main__':
    main()
