#!/usr/bin/env python3
"""
Material-swap feasibility analysis: glass baseline vs steel-variant gravity fields.

For each scan dir (steel variant) vs the baseline dir (glass 7x5), per common angle:

  - alpha_w   : least-squares optimal scale <w_s, w_g>/<w_g, w_g>
                (compare with the linear-theory prediction in
                docs/material_steel_feasibility.md)
  - cos_sim   : cosine similarity of the two w-fields (= sqrt of post-scaling R^2).
                >=0.99 means the swap is a pure rescaling and all Phase 0-4
                conclusions (three-band ratios, compensability %, theta
                irreducibility) transfer unchanged.
  - alpha_slp : FD slope-RMS ratio (the optically relevant scale)
  - mean_w    : mean plate-normal deflection (mm) — tracks the 46 deg NLGEOM
                sign flip; a shift of the zero-crossing angle is the main
                risk identified in the feasibility doc.

Also emits each dir's per-angle stats table (PV / slope RMS / three-band),
same method as gravity_decomposition.py.

Pure read-only; no ANSYS license required. Reuses loaders from
layout_scan_analysis.py. Intended to run on the FEA machine after
`generate_proxy_model.py gravity-ansys` has produced the steel dirs.

Usage:
  python scripts/material_swap_analysis.py \
      --baseline data_proxy \
      --scan steel_t3=data_proxy_steel/t3mm \
      --scan steel_t4=data_proxy_steel/t4mm \
      --scan steel_t6=data_proxy_steel/t6mm \
      --output analysis/material_swap_report.md
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout_scan_analysis import load_bins, pixel_grid, stats_table, slope_rms  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def compare_fields(w_s, w_g):
    """Optimal scale + cosine similarity between steel and glass w-fields."""
    s = w_s.ravel()
    g = w_g.ravel()
    gg = float(g @ g)
    alpha = float(s @ g) / gg if gg > 0 else float('nan')
    ns = float(s @ s)
    cos = float(s @ g) / np.sqrt(ns * gg) if ns > 0 and gg > 0 else float('nan')
    return alpha, cos


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--baseline', default=str(ROOT / 'data_proxy'),
                    help='Glass baseline dir with gravity bins (default: data_proxy)')
    ap.add_argument('--scan', action='append', required=True, metavar='LABEL=DIR',
                    help='Steel variant dir; repeatable')
    ap.add_argument('--output', default=str(ROOT / 'analysis' / 'material_swap_report.md'))
    args = ap.parse_args()

    Xg, Zg = pixel_grid()
    base = load_bins(args.baseline)
    base_stats = {r['angle']: r for r in stats_table(base, Xg, Zg)}

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
    w('# 材料替换可行性分析（material_swap_analysis.py 自动生成）')
    w('')
    w(f'- 基线（玻璃 4mm）：`{args.baseline}`')
    for label, _, _ in scans:
        w(f'- 变体：`{label}`')
    w('')
    w('alpha_w = 最小二乘最优缩放；cos_sim = 形场余弦相似度（≥0.99 即纯缩放，'
      'Phase 0-4 结论可直接迁移）；alpha_slp = FD 斜率 RMS 比（光学相关缩放）；'
      'mean_w = 平均法向挠度（追踪 46° NLGEOM 变号点）。')
    w('')

    verdicts = []
    for label, grav, stats in scans:
        common = sorted(set(grav) & set(base))
        w(f'## {label} vs 基线（{len(common)} 公共角度）')
        w('')
        w('| 角度 | alpha_w | cos_sim | alpha_slp | mean_w 钢 (mm) | mean_w 玻璃 (mm) |')
        w('|---|---|---|---|---|---|')
        cos_list, alpha_list = [], []
        for a in common:
            w_s, _, _ = grav[a]
            w_g, _, _ = base[a]
            alpha, cos = compare_fields(w_s, w_g)
            a_slp = stats[a]['slp'] / base_stats[a]['slp'] if base_stats[a]['slp'] > 0 else float('nan')
            cos_list.append(cos)
            alpha_list.append(alpha)
            w(f"| {a}° | {alpha:.3f} | {cos:.4f} | {a_slp:.3f} | "
              f"{np.mean(w_s)*1e3:+.3f} | {np.mean(w_g)*1e3:+.3f} |")
        w('')
        # stats table for this variant
        w(f'<details><summary>{label} 全场统计（PV/斜率/三频带）</summary>')
        w('')
        w('| 角度 | PV (mm) | 斜率RMS (mrad) | 仿射 | 二次 | 高阶(凹陷) |')
        w('|---|---|---|---|---|---|')
        for a in sorted(stats):
            r = stats[a]
            w(f"| {a}° | {r['pv']:.2f} | {r['slp']:.2f} | {r['aff']:.2f} | "
              f"{r['quad']:.2f} | **{r['high']:.2f}** |")
        w('')
        w('</details>')
        w('')
        if cos_list:
            amin, amax = min(alpha_list), max(alpha_list)
            cmin = min(cos_list)
            verdicts.append((label, cmin, amin, amax))
            w(f'- **{label} 小结**：min cos_sim = {cmin:.4f}；'
              f'alpha_w 范围 [{amin:.3f}, {amax:.3f}]（spread {amax/max(amin,1e-12):.2f}x）')
            w('')

    if verdicts:
        w('## 判定速览（标准见 docs/material_steel_feasibility.md §4.4）')
        w('')
        for label, cmin, amin, amax in verdicts:
            grade = ('纯缩放（Go）' if cmin >= 0.99
                     else '近似缩放（低角度需专属 bins）' if cmin >= 0.95
                     else '形状漂移（需全量重跑+重做分解）')
            w(f'- **{label}**：cos_sim_min={cmin:.4f} → {grade}')
        w('')

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(out), encoding='utf-8')
    print(f"Report written: {out_path}")
    for label, cmin, amin, amax in verdicts:
        print(f"  {label}: cos_sim_min={cmin:.4f}, alpha_w in [{amin:.3f}, {amax:.3f}]")


if __name__ == '__main__':
    main()
