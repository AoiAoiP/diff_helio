#!/usr/bin/env python3
"""
Why does R^2 sit ~0.1 below the shape correlation, while normals match FEA well?

Decomposition (de-meaned interior fields a=proxy, b=fea):
    r  = Pearson corr(a,b)          -> SHAPE agreement (scale-invariant)
    k  = std(a)/std(b)              -> AMPLITUDE ratio (proxy/fea)
    R2 = 2*r*k - k^2 = r^2 - (k-r)^2

  => R2 <= r^2 always; the gap r - R2 is driven by k<1 (PV under-prediction).
     shape penalty   = 1 - r^2      (pattern mismatch)
     amplitude pen.  = r^2 - R2      = (k-r)^2   (wrong scale)

Also compares surface slopes (normals): slope_corr (pattern) vs slope_ratio
(magnitude). If slope_corr high but slope_ratio~k<1, the flux SHAPE matches but
the flux SIZE is under-predicted -> the "small spot" is partly an artifact.

Cases: ellipse-bump bolts @12/35/52deg, and North 0deg with 33mm optimized bolts.
"""
import os
import numpy as np
from scipy.interpolate import griddata as gd

BASE = 'L:/Code/bezier_opt_desktop'
GDIR = f'{BASE}/data_vsm_mnvn_tik32'
W, L, GS, NB = 12.84, 9.45, 32, 35
KNOWN = [0, 30, 45, 60, 75]
X = np.linspace(-W/2, W/2, GS); Z = np.linspace(-L/2, L/2, GS)
Xg, Zg = np.meshgrid(X, Z)

gbin = {a: np.fromfile(f'{GDIR}/gravity_{a}deg.bin', np.float32).reshape(GS, GS) for a in KNOWN}
phi = np.fromfile(f'{GDIR}/influence_phi.bin', np.float32).reshape(NB, GS, GS)


def grav(theta):
    if theta in gbin: return gbin[theta]
    for i in range(len(KNOWN)-1):
        a, b = KNOWN[i], KNOWN[i+1]
        if a <= theta <= b:
            t = (theta-a)/(b-a); return gbin[a] + t*(gbin[b]-gbin[a])
    return gbin[KNOWN[-1]]


def fea(csv, ang):
    d = np.loadtxt(csv, delimiter=',', skiprows=1)
    x, zt, uy = d[:, 0], d[:, 2], d[:, 4]
    c = np.cos(np.deg2rad(ang)); zf = zt if ang == 0 else zt/c
    inp = (np.abs(x) <= W/2+0.02) & (np.abs(zf) <= L/2+0.02)
    g = gd((x[inp], zf[inp]), uy[inp], (Xg, Zg), 'linear')
    m = np.isnan(g)
    if m.any(): g[m] = gd((x[inp], zf[inp]), uy[inp], (Xg, Zg), 'nearest')[m]
    return g


def decomp(proxy, feaf, trim=2):
    a = (proxy - proxy.mean()); b = (feaf - feaf.mean())
    a = a[trim:-trim, trim:-trim]; b = b[trim:-trim, trim:-trim]
    a = a - a.mean(); b = b - b.mean()
    r = float(np.sum(a*b)/np.sqrt(np.sum(a*a)*np.sum(b*b)))
    k = float(np.std(a)/np.std(b))
    R2 = 1 - np.sum((a-b)**2)/np.sum(b*b)
    # slopes (normals): gradient magnitude fields
    ax, az = np.gradient(proxy[trim:-trim, trim:-trim])
    bx, bz = np.gradient(feaf[trim:-trim, trim:-trim])
    sa = np.stack([ax, az]).ravel(); sb = np.stack([bx, bz]).ravel()
    sa -= sa.mean(); sb -= sb.mean()
    scorr = float(np.sum(sa*sb)/np.sqrt(np.sum(sa*sa)*np.sum(sb*sb)))
    sratio = float(np.std(sa)/np.std(sb))
    return dict(r=r, k=k, R2=float(R2), R2_check=float(2*r*k-k*k),
                R2max=float(r*r), amp_pen=float(r*r-R2), shape_pen=float(1-r*r),
                pv_ratio=float(np.ptp(proxy)/np.ptp(feaf)),
                slope_corr=scorr, slope_ratio=sratio)


ELL = f'{BASE}/train_data/ellipse_heights'
h_ell = np.array([float(l) for l in open(f'{ELL}/bolt_heights.txt') if l.strip() and not l.startswith('#')])
cases = []
for ang in [12, 35, 52]:
    proxy = grav(ang) + np.tensordot(h_ell, phi, axes=(0, 0))
    cases.append((f'ellipse {ang}deg', proxy, fea(f'{ELL}/node_dump_{ang}deg.csv', ang)))

# North 0deg, optimized 33mm bolts
h_n = np.array([float(l) for l in open(f'{BASE}/results_vsm_mnvn_300iter/North_300m_STROKE_bolts.txt')
                if l.strip() and not l.startswith('#')])
proxy_n = grav(0) + np.tensordot(h_n, phi, axes=(0, 0))
cases.append(('North 0deg(33mm)', proxy_n, fea(f'{BASE}/results_vsm_mnvn_300iter/node_dump_0deg_ON.csv', 0)))

print("="*104)
print(f"{'case':18s} {'r(shape)':>9} {'k(ampl)':>8} {'R2':>7} {'2rk-k2':>7} "
      f"{'R2max=r2':>9} {'shapePen':>9} {'ampPen':>7} {'PVratio':>8} {'slopeCorr':>10} {'slopeRat':>9}")
print("-"*104)
for name, p, f in cases:
    m = decomp(p, f)
    print(f"{name:18s} {m['r']:9.4f} {m['k']:8.4f} {m['R2']:7.4f} {m['R2_check']:7.4f} "
          f"{m['R2max']:9.4f} {m['shape_pen']:9.4f} {m['amp_pen']:7.4f} {m['pv_ratio']:8.4f} "
          f"{m['slope_corr']:10.4f} {m['slope_ratio']:9.4f}")
print("="*104)
print("r=Pearson shape corr | k=std(proxy)/std(fea) | R2=2rk-k^2 | shapePen=1-r^2 | ampPen=r^2-R2=(k-r)^2")
print("Read: high r & slopeCorr = shape/normals match; k<1 & slopeRatio<1 = amplitude(PV) & slopes under-predicted")

# ── illustrative slope scatter: correlated (aligned) but under-scaled ──
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def slopes(f, trim=2):
    ax, az = np.gradient(f[trim:-trim, trim:-trim])
    return np.stack([ax, az]).ravel()

fig, axs = plt.subplots(1, 2, figsize=(13, 6))
for ax, (name, p, f) in zip(axs, [cases[0], cases[3]]):  # ellipse 12deg, North 0deg
    sp, sf = slopes(p)*1000, slopes(f)*1000
    r = np.corrcoef(sp, sf)[0, 1]; k = np.std(sp)/np.std(sf)
    ax.scatter(sf, sp, s=4, alpha=0.35, color='#3366aa')
    lim = np.abs(np.concatenate([sf, sp])).max()
    xs = np.array([-lim, lim])
    ax.plot(xs, xs, 'k--', lw=1.2, label='y=x (perfect)')
    ax.plot(xs, k*xs, 'r-', lw=1.6, label=f'y={k:.2f}·x (proxy under-scaled)')
    ax.set_xlabel('FEA slope (mm/cell)'); ax.set_ylabel('proxy slope (mm/cell)')
    ax.set_title(f'{name}\nslopeCorr={r:.3f}  slopeRatio={k:.3f}', fontweight='bold')
    ax.legend(fontsize=9); ax.set_aspect('equal'); ax.grid(alpha=0.3)
fig.suptitle('Normals point right (high corr) but are under-scaled (slope<1) -> flux shape ok, size too small',
             fontsize=12, fontweight='bold')
plt.tight_layout()
out = f'{BASE}/train_data/ellipse_heights/r2_gap_slopes.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
plt.close(fig)
print(f"\nsaved: {out}")

