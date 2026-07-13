#!/usr/bin/env python3
"""
North 300m flux validation at tilt 29.5 / 58.5 deg (skip 0deg).

For each tilt: build the proxy surface (gravity_interp + sum h*phi, local frame)
and the FEA surface (uy*cos+uz*sin, z-uncompressed), export both as x-z-uy grids,
render each with the C++ GPU ray tracer (--dump-flux --surface-file) under the
sun direction that produces that mirror tilt for North, then compare the flux
spots (peak, total energy, S95 pixel count, spot shape correlation).

Out: results_vsm_mnvn_300iter/flux_north/  (npy + comparison png + metrics.json)
"""
import os, json, glob, struct, re, subprocess
import numpy as np
from scipy.interpolate import griddata as gd
from scipy.ndimage import gaussian_filter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = 'L:/Code/bezier_opt_desktop'
RES = f'{BASE}/results_vsm_mnvn_300iter'
GDIR = f'{BASE}/data_vsm_mnvn_tik32'
EXE = f'{BASE}/build/src/Release/bezier_opt.exe'
OUT = f'{RES}/flux_north'; os.makedirs(OUT, exist_ok=True)
W, L, GS, NB = 12.84, 9.45, 32, 35
KNOWN = [0, 12, 22, 30, 35, 45, 52, 60, 67, 75]
# tilt -> (FEA csv, sun direction giving that tilt for North)
CASES = [('29.5', 29.5, f'{RES}/node_dump_295deg.csv', [0.0, 0.9999, 0.0145]),
         ('58.5', 58.5, f'{RES}/node_dump_585deg.csv', [0.0, 0.5177, 0.8556])]
X = np.linspace(-W/2, W/2, GS); Z = np.linspace(-L/2, L/2, GS); Xg, Zg = np.meshgrid(X, Z)

gbin = {a: np.fromfile(f'{GDIR}/gravity_{a}deg.bin', np.float32).reshape(GS, GS) for a in KNOWN}
phi = np.fromfile(f'{GDIR}/influence_phi.bin', np.float32).reshape(NB, GS, GS)
h = np.array([float(l) for l in open(f'{RES}/North_300m_STROKE_bolts.txt') if l.strip() and not l.startswith('#')])
bolt = np.tensordot(h, phi, axes=(0, 0))


def grav(theta):
    if theta in gbin: return gbin[theta]
    for i in range(len(KNOWN)-1):
        a, b = KNOWN[i], KNOWN[i+1]
        if a <= theta <= b:
            t = (theta-a)/(b-a); return gbin[a]+t*(gbin[b]-gbin[a])
    return gbin[KNOWN[-1]]


def fea_local(csv, ang):
    d = np.loadtxt(csv, delimiter=',', skiprows=1)
    x, zg_, uy, uz = d[:, 0], d[:, 2], d[:, 4], d[:, 5]
    ct, st = np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))
    u = uy*ct + uz*st
    zext = zg_.max()-zg_.min(); zs = L/zext if zext > 0 else 1.0
    g = gd((x, zg_*zs), u, (Xg, Zg), 'linear'); m = np.isnan(g)
    if m.any(): g[m] = gd((x, zg_*zs), u, (Xg, Zg), 'nearest')[m]
    return g


def export_surface(path, w):
    with open(path, 'w') as f:
        for zi in range(GS):
            for xi in range(GS):
                f.write(f'{Xg[zi,xi]:.6f} {Zg[zi,xi]:.6f} {w[zi,xi]:.12f}\n')


def load_npy(path):
    with open(path, 'rb') as f:
        f.read(6); major, minor = struct.unpack('<BB', f.read(2))
        hl = struct.unpack('<H' if major == 1 else '<I', f.read(2 if major == 1 else 4))[0]
        hdr = f.read(hl).decode(); sm = re.search(r"'shape':\s*\(([^)]+)\)", hdr)
        shape = tuple(int(x) for x in sm.group(1).split(',') if x.strip()) if sm else (50, 157)
        return np.frombuffer(f.read(), dtype=np.float32).reshape(shape)


def s95_level(flux):
    sf = np.sort(flux.ravel())[::-1]
    return sf[max(0, min(np.searchsorted(np.cumsum(sf), 0.95*flux.sum()), len(sf)-1))]


def run_flux(surf, sun, tag):
    with open(f'{OUT}/sun_{tag}.txt', 'w') as f: f.write(f'{sun[0]} {sun[1]} {sun[2]}\n')
    cfg = {"sun_train_file": f'{OUT}/sun_{tag}.txt', "sun_validation_file": f'{OUT}/sun_{tag}.txt',
           "ellipse_file": "data/ellipse_north.txt", "output_dir": f'{OUT}/f_{tag}',
           "receiver_radius": 10, "receiver_height": 20, "pixel_width": 157, "pixel_height": 50,
           "heliostat_width": 12.84, "heliostat_length": 9.45, "grid_size": 32,
           "glass_depth": 0.003, "refractive_index": 1.523, "slope_error": 0.001, "reflectivity": 0.88,
           "sun_type": "buie", "dni": 1000, "csr": 0.01, "sun_sigma": 0.00251, "sun_theta_max": 0.00465,
           "iterations": 1, "patience": 1, "learning_rate": 2e-4, "beta1": 0.9, "beta2": 0.999,
           "adam_epsilon": 1e-8, "use_bolt": 1, "num_bolts": 35, "num_bolts_x": 7, "num_bolts_z": 5,
           "influence_data_path": "data_vsm_mnvn_tik32", "bolt_init_file": "", "disable_gravity": 1,
           "enable_mse_loss": 0}
    os.makedirs(f'{OUT}/f_{tag}', exist_ok=True)
    cp = f'{OUT}/cfg_{tag}.json'; json.dump(cfg, open(cp, 'w'), indent=2)
    subprocess.run([EXE, '--dump-flux', '--surface-file', surf, '--config', cp],
                   capture_output=True, text=True, encoding='utf-8', errors='replace',
                   timeout=180, cwd=BASE)
    npy = glob.glob(f'{OUT}/f_{tag}/*_sun0_flux.npy')
    return load_npy(npy[0]) if npy else None


results = {}
fig, axes = plt.subplots(len(CASES), 2, figsize=(16, 4.5*len(CASES)))
if len(CASES) == 1: axes = axes.reshape(1, -1)  # ensure 2D if single row
for row, (name, ang, csv, sun) in enumerate(CASES):
    w_proxy = grav(ang) + bolt
    w_fea = fea_local(csv, ang)
    export_surface(f'{OUT}/surf_proxy_{name}.txt', w_proxy)
    export_surface(f'{OUT}/surf_fea_{name}.txt', w_fea)
    print(f"theta={name}deg: rendering proxy & FEA flux (sun={sun})...")
    fp = run_flux(f'{OUT}/surf_proxy_{name}.txt', sun, f'proxy_{name}')
    ff = run_flux(f'{OUT}/surf_fea_{name}.txt', sun, f'fea_{name}')
    if fp is None or ff is None:
        print(f"  FAILED to render {name}"); continue
    # No rotation — flux orientation matches C++ output convention
    fps = gaussian_filter(fp, 1.5); ffs = gaussian_filter(ff, 1.5)
    # S95 computed on RAW flux (matches C++ pipeline; smoothing is visual-only)
    lp, lf = s95_level(fp), s95_level(ff)
    s95p = int((fp >= lp).sum()); s95f = int((ff >= lf).sum())
    # pixel area on cylindrical receiver: 2*pi*R*H / (W_px * H_px)
    pxA = 2.0 * np.pi * 10.0 * 20.0 / (157.0 * 50.0)  # 0.1601 m²/px (matches pipeline.cpp:1542)
    corr = float(np.corrcoef(fps.ravel(), ffs.ravel())[0, 1])
    # S95 in m²
    s95m2_p = round(s95p * pxA, 2); s95m2_f = round(s95f * pxA, 2)
    m = dict(peak_proxy=round(float(fp.max()), 1), peak_fea=round(float(ff.max()), 1),
             total_proxy=round(float(fp.sum()), 0), total_fea=round(float(ff.sum()), 0),
             s95_px_proxy=s95p, s95_px_fea=s95f,
             s95_m2_proxy=s95m2_p, s95_m2_fea=s95m2_f,
             flux_corr=round(corr, 4))
    results[name] = m
    print(f"  peak {m['peak_proxy']}/{m['peak_fea']}  total {m['total_proxy']:.0f}/{m['total_fea']:.0f}  "
          f"S95 {s95m2_p:.1f}/{s95m2_f:.1f} m2  fluxCorr={corr:.4f}")
    vm = max(fps.max(), ffs.max())
    flux_cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        'flux_rwb', [(0.0, '#1a237e'), (0.3, '#1976d2'), (0.5, '#ffffff'),
                     (0.7, '#e53935'), (1.0, '#b71c1c')])
    for col, (data, lev, pfx) in enumerate([
            (fps, lp, 'Proxy'), (ffs, lf, 'FEA')]):
        ax = axes[row, col]
        im = ax.imshow(data, cmap=flux_cmap, origin='lower', aspect='auto', vmin=0, vmax=vm)
        ax.contour(data, levels=[lev], colors='#00ff40', linewidths=1.5)
        s95val = s95m2_p if col == 0 else s95m2_f
        ax.set_title(f'{name}° {pfx}  fluxCorr={corr:.4f}  S95={s95val:.1f} m$^2$  peak={fp.max() if col==0 else ff.max():.0f}',
                     fontsize=9, fontweight='bold')
        plt.colorbar(im, ax=ax, label='W/m²')
fig.suptitle('North 300m flux: proxy vs FEA (GPU ray trace, NLGEOM-ON FEA, dense bins)',
             fontsize=13, fontweight='bold', y=0.995)
plt.tight_layout(rect=[0, 0, 1, 0.99])
plt.savefig(f'{OUT}/flux_north_compare.png', dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)
json.dump(results, open(f'{OUT}/flux_metrics.json', 'w'), indent=2)
print(f"saved: {OUT}/flux_north_compare.png")

# ==================================================================
# Loss curve (from North_300m_history.csv, 10-bin dense optimization)
# ==================================================================
history = np.loadtxt(f'{RES}/North_300m_history.csv', delimiter=',', skiprows=1)
iters, loss, s95 = history[:, 0].astype(int), history[:, 1], history[:, 2]

# only plot S95 at evaluation points (every ~10th iter)
val_mask = np.array([i % 10 == 0 for i in iters])
fig, ax1 = plt.subplots(figsize=(14, 6)); ax2 = ax1.twinx()
ax1.plot(iters, loss, 'steelblue', lw=1.2, alpha=0.85, label='Loss')
ax2.plot(iters[val_mask], s95[val_mask], 'darkorange', marker='o', ms=4, lw=1.5, label='S95 (m²)')
ax1.set_xlabel('Iteration'); ax1.set_ylabel('Loss', color='steelblue')
ax2.set_ylabel('S95 (m²)', color='darkorange')
# mark best
ibest = int(s95.argmin())
ax2.axhline(s95.min(), color='darkorange', ls='--', lw=1, alpha=0.5)
ax2.annotate(f'Best S95 = {s95.min():.2f} m²\n(iter {iters[ibest]})',
             (iters[ibest], s95.min()), textcoords='offset points', xytext=(10, 15),
             fontsize=9, color='darkorange')
lines1, labs1 = ax1.get_legend_handles_labels(); lines2, labs2 = ax2.get_legend_handles_labels()
ax1.legend(lines1+lines2, labs1+labs2, loc='upper right')
ax1.set_title(f'North 300m Optimization — 10-bin Dense Gravity  |  '
              f'{len(iters)} Iter, LR Decay  |  Best S95 = {s95.min():.2f} m²', fontweight='bold')
ax1.grid(True, alpha=0.3)
fig.tight_layout()
loss_path = f'{RES}/loss_curve_dense_10bin.png'
plt.savefig(loss_path, dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)
print(f"saved: {loss_path}")
