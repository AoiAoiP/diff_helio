#!/usr/bin/env python3
"""
Closed-form gravity-compensated bolt initialization + anchor data generation.

For each mirror in ellipse.txt, decomposes the bolt solution into two
physically interpretable terms:

    h* = h_shape + h_comp

    h_shape = argmin_h || Phi h - s_ellipse ||^2          (height-space, ideal shape)
    h_comp  = argmin_h || grad(Phi h) - grad(-g_bar) ||^2 (slope-space, gravity resistance)

where g_bar(x,z) is the annual mean gravity field over the training sundir set
(the theta-varying part of gravity is structurally irreducible for fixed bolts;
see analysis/gravity_compensability_report.md).

Because the TPS proxy is linear in h, h_comp has a closed form — this is where
the physics proxy does explicit work: the influence matrix Phi maps bolt
commands to a gravity-cancelling shape.

Outputs (per mirror, {name} e.g. North_300m):
  data/init_comp/{name}_bolt_init.txt   pipeline-convention bolt init (h*)
  data/init_comp/{name}_anchor.bin      float32[35*35 + 35]: slope Gram G, then G @ h*
  data/init_comp/comp_summary.csv       per-mirror compensation diagnostics
"""

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

W = 12.84
L = 9.45
GS = 32
NB = None  # auto-detected from influence_phi.bin size (n_floats / GS²)

ANGLES_20BIN = [10, 14, 18, 22, 26, 30, 34, 38, 42, 46,
                50, 54, 58, 62, 66, 70, 73, 76, 78, 80]


def pixel_grid():
    u = (np.arange(GS) + 0.5) / GS
    x = (u - 0.5) * W
    z = (u - 0.5) * L
    Xg, Zg = np.meshgrid(x, z)
    return Xg, Zg


def load_gravity_slopes(data_proxy):
    """angle -> (sx, sz) physical slope planes (m/m)."""
    slopes = {}
    for a in ANGLES_20BIN:
        d = np.fromfile(data_proxy / f'gravity_{a}deg.bin', dtype=np.float32)
        if d.size == 3 * GS * GS:
            sx = d[GS * GS:2 * GS * GS].reshape(GS, GS).astype(np.float64)
            sz = d[2 * GS * GS:].reshape(GS, GS).astype(np.float64)
        elif d.size == GS * GS:
            w = d.reshape(GS, GS).astype(np.float64)
            sz, sx = np.gradient(w, L / GS, W / GS, axis=(0, 1))
        else:
            raise ValueError(f'gravity_{a}deg.bin: unexpected size {d.size}')
        slopes[a] = (sx, sz)
    return slopes


def sample_slopes(slopes, cos_t):
    bin_a = np.array(ANGLES_20BIN, float)
    ang = np.degrees(np.arccos(np.clip(cos_t, -1, 1)))
    ang = np.clip(ang, bin_a[0], bin_a[-1])
    i = int(np.searchsorted(bin_a, ang))
    i = min(max(i, 1), len(bin_a) - 1)
    lo, hi = bin_a[i - 1], bin_a[i]
    t = 0.0 if hi == lo else (ang - lo) / (hi - lo)
    return tuple((1 - t) * slopes[int(lo)][k] + t * slopes[int(hi)][k] for k in range(2))


def mirror_cos_thetas(sun, pos, receiver_y=180.0, receiver_r=10.0):
    dl = np.linalg.norm(pos[[0, 2]])
    aim = np.array([pos[0] / dl * receiver_r, receiver_y, pos[2] / dl * receiver_r])
    r = aim - pos
    r = r / np.linalg.norm(r)
    n = sun + r
    n = n / np.linalg.norm(n, axis=1, keepdims=True)
    return np.abs(n @ np.array([0.0, 1.0, 0.0]))


def load_mirrors(ellipse_file):
    mirrors = []
    for line in open(ellipse_file):
        p = line.split()
        if len(p) < 7 or p[0].startswith('#'):
            continue
        pos = np.array([float(p[1]), float(p[2]), float(p[3])])
        mirrors.append({'name': f"{p[0]}_{int(round(np.linalg.norm(pos)))}m",
                        'pos': pos, 'cx': float(p[4]), 'cy': float(p[5]), 'cxy': float(p[6])})
    return mirrors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-proxy', default=str(ROOT / 'data_proxy'))
    ap.add_argument('--ellipse-file', default=str(ROOT / 'data' / 'ellipse.txt'))
    ap.add_argument('--sundir', default=str(ROOT / 'data' / '334_sundir_balanced.txt'))
    ap.add_argument('--output-dir', default=str(ROOT / 'data' / 'init_comp'))
    args = ap.parse_args()

    data_proxy = Path(args.data_proxy)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    Xg, Zg = pixel_grid()

    # --- influence data: values + analytic derivatives ---
    phi_raw = np.fromfile(data_proxy / 'influence_phi.bin', dtype=np.float32)
    nb = len(phi_raw) // (GS * GS)
    if NB is not None and NB > 0:
        nb = NB
    phi = phi_raw.reshape(nb, GS * GS)
    phi_u = np.fromfile(data_proxy / 'influence_phi_u.bin', dtype=np.float32).reshape(nb, GS * GS)
    phi_v = np.fromfile(data_proxy / 'influence_phi_v.bin', dtype=np.float32).reshape(nb, GS * GS)
    Phi = phi.T                                          # (GS*GS, nb) height design
    # physical slope design: d phi/dx = phi_u / W, d phi/dz = phi_v / L
    A = np.vstack([(phi_u / W).T, (phi_v / L).T])        # (2*GS*GS, nb) slope design

    # --- slope Gram for the anchor metric: G_bb' = <grad phi_b, grad phi_b'> ---
    G = A.T @ A                                          # (nb, nb)

    slopes = load_gravity_slopes(data_proxy)
    mirrors = load_mirrors(args.ellipse_file)
    sun = np.loadtxt(args.sundir, comments='#')
    sun = sun / np.linalg.norm(sun, axis=1, keepdims=True)

    rows = []
    for m in mirrors:
        # --- h_shape: height-space LS fit to ideal elliptic sag ---
        s_target = (m['cx'] * Xg**2 + m['cy'] * Zg**2 + m['cxy'] * Xg * Zg).ravel()
        h_shape, *_ = np.linalg.lstsq(Phi, s_target, rcond=None)

        # --- g_bar: annual mean gravity SLOPE field over the training set ---
        cos_t = mirror_cos_thetas(sun, m['pos'])
        sx_bar = np.mean([sample_slopes(slopes, c)[0] for c in cos_t], axis=0)
        sz_bar = np.mean([sample_slopes(slopes, c)[1] for c in cos_t], axis=0)
        gbar_slp = float(np.sqrt(np.mean(sx_bar**2 + sz_bar**2)))

        # --- h_comp: closed-form slope-space cancellation of g_bar ---
        # NOTE: the slope design has one near-null "piston" direction (sv ~ 2e-7;
        # uniform bolt offset -> ~zero slope). rcond=None keeps it and pollutes
        # h_comp with a ~km-scale constant — optically irrelevant in slope space
        # but catastrophic as a height init. Truncate it (rcond=1e-6).
        bvec = -np.concatenate([sx_bar.ravel(), sz_bar.ravel()])
        h_comp, *_ = np.linalg.lstsq(A, bvec, rcond=1e-6)

        h_star = h_shape + h_comp
        if np.max(np.abs(h_star)) > 0.2:  # sanity: bolt strokes are O(10-100 mm)
            raise RuntimeError(f"{m['name']}: |h*| max = {np.max(np.abs(h_star)):.3f} m "
                               f"— unphysical, check lstsq conditioning")

        # compensation diagnostics
        rx = sx_bar + (A[:GS * GS] @ h_comp).reshape(GS, GS)
        rz = sz_bar + (A[GS * GS:] @ h_comp).reshape(GS, GS)
        res_slp = float(np.sqrt(np.mean(rx**2 + rz**2)))
        removed = 100 * (1 - res_slp**2 / gbar_slp**2) if gbar_slp > 0 else 0.0

        # --- write bolt init (pipeline convention) ---
        init_path = out_dir / f"{m['name']}_bolt_init.txt"
        with open(init_path, 'w') as f:
            f.write('# Gravity-compensated bolt init: h* = h_shape + h_comp (closed form)\n')
            f.write(f"# Mirror: {m['name']} | sundir: {os.path.basename(args.sundir)}\n")
            f.write('# idx  h_pipe(m)\n')
            for i, hi in enumerate(h_star):
                f.write(f'{i} {hi:.8f}\n')

        # --- write anchor buffer: [G (nb*nb row-major)] + [G @ h* (nb)] ---
        anchor_path = out_dir / f"{m['name']}_anchor.bin"
        target = G @ h_star
        np.concatenate([G.ravel(), target]).astype(np.float32).tofile(anchor_path)
        meta = {'mirror': m['name'], 'layout': f'float32[{nb}*{nb}] G row-major, then float32[{nb}] G@h*',
                'nb': nb, 'sundir': os.path.basename(args.sundir),
                'h_shape_pv_mm': float(np.ptp(h_shape) * 1e3),
                'h_comp_pv_mm': float(np.ptp(h_comp) * 1e3)}
        (out_dir / f"{m['name']}_anchor.json").write_text(json.dumps(meta, indent=1))

        rows.append({
            'mirror': m['name'],
            'h_shape_pv_mm': float(np.ptp(h_shape) * 1e3),
            'h_comp_pv_mm': float(np.ptp(h_comp) * 1e3),
            'h_star_max_abs_mm': float(np.max(np.abs(h_star)) * 1e3),
            'gbar_slope_mrad': gbar_slp * 1e3,
            'residual_slope_mrad': res_slp * 1e3,
            'mean_slope_removed_pct': removed,
            'theta_min_deg': float(np.degrees(np.arccos(cos_t.min()))),
            'theta_max_deg': float(np.degrees(np.arccos(cos_t.max()))),
        })
        print(f"{m['name']:<14} h_shape PV={np.ptp(h_shape)*1e3:7.2f}mm  "
              f"h_comp PV={np.ptp(h_comp)*1e3:5.2f}mm  "
              f"gbar slope={gbar_slp*1e3:5.3f} mrad -> {res_slp*1e3:5.3f} mrad "
              f"({removed:4.1f}% removed)")

    csv_path = out_dir / 'comp_summary.csv'
    with open(csv_path, 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f'\nWrote {len(rows)} mirrors -> {out_dir}/')
    print(f'Summary: {csv_path}')


if __name__ == '__main__':
    main()
