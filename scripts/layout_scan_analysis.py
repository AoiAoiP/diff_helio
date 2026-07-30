#!/usr/bin/env python3
"""
Layout scan analysis: compare gravity-field statistics across bolt-layout variants.

For each layout directory containing gravity_{ang}deg.bin files (3-plane
[w | dw/dx | dw/dz] "w_du_dv_v2", or legacy 1-plane), computes per angle:

  - height PV (mm)
  - slope RMS (mrad, FD of w — consistent with gravity_decomposition.py's
    report table; the bins' stored derivative planes are Gaussian-smoothed
    and understate the high-frequency sag band ~2x)
  - three-band decomposition (affine / quadratic / high-order) slope RMS (mrad),
    identical method to scripts/gravity_decomposition.py

and, vs the baseline layout dir, PV / slope-RMS ratios at common angles.

Pure read-only; no ANSYS license required. Intended to run on the FEA machine
after `generate_proxy_model.py gravity-ansys` has produced the scan dirs.

Usage:
  python scripts/layout_scan_analysis.py \
      --baseline data_proxy \
      --scan L1_8x6=data_proxy_scan/8x6_dense \
      --scan L2_7x7=data_proxy_scan/7x7_zdense \
      --scan L3_9x7=data_proxy_scan/9x7_dense \
      --output analysis/layout_scan_report.md
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

# Plate / grid constants (must match generate_proxy_model.py and shaders)
W = 12.84   # plate width  (x), m
L = 9.45    # plate length (z), m
GS = 32     # surface grid size
DX = W / GS
DZ = L / GS


def pixel_grid():
    u = (np.arange(GS) + 0.5) / GS
    x = (u - 0.5) * W
    z = (u - 0.5) * L
    Xg, Zg = np.meshgrid(x, z)          # axis0 = z (outer), axis1 = x (inner)
    return Xg, Zg


def load_bins(d):
    """Load all gravity_{ang}deg.bin in dir d. Returns {angle: (w, sx, sz)}."""
    d = Path(d)
    if not d.is_dir():
        raise FileNotFoundError(f"scan dir not found: {d}")
    grav = {}
    for p in sorted(d.glob("gravity_*deg.bin")):
        m = re.match(r"gravity_(\d+)deg\.bin", p.name)
        if not m:
            continue
        a = int(m.group(1))
        arr = np.fromfile(p, dtype=np.float32)
        if arr.size == 3 * GS * GS:
            w = arr[:GS * GS].reshape(GS, GS).astype(np.float64)
            sx = arr[GS * GS:2 * GS * GS].reshape(GS, GS).astype(np.float64)
            sz = arr[2 * GS * GS:].reshape(GS, GS).astype(np.float64)
        elif arr.size == GS * GS:
            w = arr.reshape(GS, GS).astype(np.float64)
            sz, sx = np.gradient(w, DZ, DX, axis=(0, 1))
        else:
            raise ValueError(f"{p}: unexpected size {arr.size}")
        grav[a] = (w, sx, sz)
    if not grav:
        raise FileNotFoundError(f"no gravity_*deg.bin in {d}")
    return grav


def phys_grads(f):
    df_dz, df_dx = np.gradient(f, DZ, DX, axis=(0, 1))
    return df_dx, df_dz


def slope_rms_of(sx, sz):
    return float(np.sqrt(np.mean(sx**2 + sz**2)))


def slope_rms(f):
    gx, gz = phys_grads(f)
    return slope_rms_of(gx, gz)


def band_decomp(f, Xg, Zg):
    """Split field into affine / quadratic / high-order bands; return slope-RMS of each.
    Same lstsq method as gravity_decomposition.py."""
    A = np.column_stack([np.ones(GS * GS), Xg.ravel(), Zg.ravel(),
                         Xg.ravel()**2, Zg.ravel()**2, (Xg * Zg).ravel()])
    c, *_ = np.linalg.lstsq(A, f.ravel(), rcond=None)
    aff = c[0] + c[1] * Xg + c[2] * Zg
    quad = c[3] * Xg**2 + c[4] * Zg**2 + c[5] * Xg * Zg
    hi = f - aff - quad
    return slope_rms(aff), slope_rms(quad), slope_rms(hi)


def stats_table(grav, Xg, Zg):
    """Per-angle stats rows. Headline slope RMS uses FD-of-w (consistent with the
    three-band decomposition and the §1.1.2 report table; stored slopes are
    Gaussian-smoothed and understate high-frequency content ~2x)."""
    rows = []
    for a in sorted(grav):
        w, sx, sz = grav[a]
        sa, sq, sh = band_decomp(w, Xg, Zg)
        rows.append(dict(angle=a,
                         pv=np.ptp(w) * 1e3,
                         slp=slope_rms(w) * 1e3,
                         aff=sa * 1e3, quad=sq * 1e3, high=sh * 1e3))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--baseline', default=str(ROOT / 'data_proxy'),
                    help='Baseline layout dir with gravity bins (default: data_proxy = 7x5)')
    ap.add_argument('--scan', action='append', required=True, metavar='LABEL=DIR',
                    help='Scan layout dir; repeatable')
    ap.add_argument('--output', default=str(ROOT / 'analysis' / 'layout_scan_report.md'))
    args = ap.parse_args()

    Xg, Zg = pixel_grid()
    base = load_bins(args.baseline)
    base_rows = {r['angle']: r for r in stats_table(base, Xg, Zg)}

    scans = []
    for spec in args.scan:
        label, _, d = spec.partition('=')
        if not d:
            print(f"ERROR: --scan expects LABEL=DIR, got: {spec}", file=sys.stderr)
            sys.exit(1)
        grav = load_bins(ROOT / d if not Path(d).is_absolute() else d)
        scans.append((label, grav, {r['angle']: r for r in stats_table(grav, Xg, Zg)}))

    out = []
    w = out.append
    w('# 布局扫描重力场统计（layout_scan_analysis.py 自动生成）')
    w('')
    w(f'- 基线：`{args.baseline}`（7x5，35 螺栓）')
    for label, _, _ in scans:
        w(f'- 扫描：`{label}`')
    w('')
    w('单位：PV = mm，斜率类 = mrad。三频带分解方法同 gravity_decomposition.py。')
    w('')

    # Per-layout detail tables
    for label, grav, rows_by_a in scans:
        w(f'## {label}（{len(rows_by_a)} 角度 bin）')
        w('')
        w('| 角度 | PV | 斜率RMS | 仿射 | 二次 | 高阶(凹陷) |')
        w('|---|---|---|---|---|---|')
        for a in sorted(rows_by_a):
            r = rows_by_a[a]
            w(f"| {a}° | {r['pv']:.2f} | {r['slp']:.2f} | {r['aff']:.2f} | "
              f"{r['quad']:.2f} | **{r['high']:.2f}** |")
        w('')

    # Comparison vs baseline at common angles
    common = sorted(set(base_rows) & set.intersection(*[set(g) for _, g, _ in scans]))
    if common:
        w('## 与基线对比（公共角度，比值 = 扫描/基线）')
        w('')
        header = '| 角度 | 基线 PV | 基线斜率 |'
        sep = '|---|---|---|'
        for label, _, _ in scans:
            header += f' {label} PV(比) | {label} 斜率(比) |'
            sep += '---|---|'
        w(header)
        w(sep)
        for a in common:
            b = base_rows[a]
            row = f"| {a}° | {b['pv']:.2f} | {b['slp']:.2f} |"
            for label, _, rows_by_a in scans:
                r = rows_by_a[a]
                row += (f" {r['pv']:.2f} ({r['pv']/b['pv']:.3f}) |"
                        f" {r['slp']:.2f} ({r['slp']/b['slp']:.3f}) |")
            w(row)
        w('')

        # Go/no-go helper at 10 deg (worst case)
        if 10 in common:
            w('## 10°（最坏工况）地板比值速览')
            w('')
            for label, _, rows_by_a in scans:
                r = rows_by_a[10]
                b = base_rows[10]
                w(f"- **{label}**: 斜率比 {r['slp']/b['slp']:.3f}，PV 比 {r['pv']/b['pv']:.3f}")
            w('')
    else:
        w('（扫描与基线无公共角度，跳过对比）')

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(out), encoding='utf-8')
    print(f"Report written: {out_path}")
    # Echo the key table to stdout for quick inspection
    if common and 10 in common:
        print("\n10deg slope-RMS ratio vs baseline:")
        for label, _, rows_by_a in scans:
            print(f"  {label}: {rows_by_a[10]['slp']/base_rows[10]['slp']:.3f}")


if __name__ == '__main__':
    main()
