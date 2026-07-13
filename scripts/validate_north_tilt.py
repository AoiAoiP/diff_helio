#!/usr/bin/env python3
"""
North 300m deformation validation at tilt 29.5 / 58.5 deg (skip 0deg).

Proxy (C++ local plate-frame convention, NO cos-theta on bolts):
    w(theta) = gravity_interp(theta) + sum_b h_b * phi_b
FEA reference (node_dump_{295,585}deg.csv, NLGEOM-ON), projected to the plate
normal (= the frame the C++ local2world's the surface in):
    delta = uy*cos(theta) + uz*sin(theta)          [plate-normal displacement]
    z un-compressed via L / (actual z-extent).

Bolt heights: results_vsm_mnvn_300iter/North_300m_STROKE_bolts.txt (10-bin re-opt).
Dense gravity bins (10 angles) from data_vsm_mnvn_tik32.

Out: results_vsm_mnvn_300iter/deform_north_tilt.png + deform_north_tilt.json
"""
import os, json
import numpy as np
from scipy.interpolate import griddata as gd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = 'L:/Code/bezier_opt_desktop'
RES = f'{BASE}/results_vsm_mnvn_300iter'
GDIR = f'{BASE}/data_vsm_mnvn_tik32'
W, L, GS, NB = 12.84, 9.45, 32, 35
KNOWN = [0, 12, 22, 30, 35, 45, 52, 60, 67, 75]
CASES = [('29.5', 29.5, f'{RES}/node_dump_295deg.csv'),
         ('58.5', 58.5, f'{RES}/node_dump_585deg.csv')]
X = np.linspace(-W/2, W/2, GS); Z = np.linspace(-L/2, L/2, GS); Xg, Zg = np.meshgrid(X, Z)
BU = np.linspace(0.08, 0.92, 7); BV = np.linspace(0.08, 0.92, 5)
BX = np.array([(u-0.5)*W for v in BV for u in BU]); BZ = np.array([(v-0.5)*L for v in BV for u in BU])

gbin = {a: np.fromfile(f'{GDIR}/gravity_{a}deg.bin', np.float32).reshape(GS, GS) for a in KNOWN}
phi = np.fromfile(f'{GDIR}/influence_phi.bin', np.float32).reshape(NB, GS, GS)
h = np.array([float(l) for l in open(f'{RES}/North_300m_STROKE_bolts.txt') if l.strip() and not l.startswith('#')])
bolt = np.tensordot(h, phi, axes=(0, 0))
print(f"North bolts: max={h.max()*1000:.2f}mm  bolt term PV={np.ptp(bolt)*1000:.2f}mm")


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
    u_local = uy*ct + uz*st                       # plate-normal delta
    zext = zg_.max()-zg_.min(); zs = L/zext if zext > 0 else 1.0
    g = gd((x, zg_*zs), u_local, (Xg, Zg), 'linear'); m = np.isnan(g)
    if m.any(): g[m] = gd((x, zg_*zs), u_local, (Xg, Zg), 'nearest')[m]
    return g


def stats(proxy, fea, t=2):
    p = (proxy-proxy.mean())[t:-t, t:-t]; f = (fea-fea.mean())[t:-t, t:-t]
    p = p-p.mean(); f = f-f.mean()
    res = p-f
    rms = np.sqrt(np.mean(res**2))*1000
    r = float(np.sum(p*f)/np.sqrt(np.sum(p*p)*np.sum(f*f)))
    r2 = float(1-np.sum(res**2)/np.sum(f*f))
    ax, az = np.gradient(p); bx, bz = np.gradient(f)
    sa = np.concatenate([ax.ravel(), az.ravel()]); sb = np.concatenate([bx.ravel(), bz.ravel()])
    sc = float(np.corrcoef(sa, sb)[0, 1])
    return dict(rms_mm=round(rms, 3), r2=round(r2, 4), shape_corr=round(r, 4), slope_corr=round(sc, 4),
                pv_proxy_mm=round(np.ptp(proxy)*1000, 2), pv_fea_mm=round(np.ptp(fea)*1000, 2),
                pv_ratio=round(np.ptp(proxy)/np.ptp(fea), 4))


results = {}
fig, axes = plt.subplots(len(CASES), 3, figsize=(15, 4.4*len(CASES)))
for row, (name, ang, csv) in enumerate(CASES):
    proxy = grav(ang) + bolt
    fea = fea_local(csv, ang)
    m = stats(proxy, fea); results[name] = m
    print(f"theta={name}deg  RMS={m['rms_mm']}mm  R2={m['r2']}  shapeCorr={m['shape_corr']}  "
          f"slopeCorr={m['slope_corr']}  PV proxy/fea={m['pv_proxy_mm']}/{m['pv_fea_mm']}  k={m['pv_ratio']}")
    p0 = (proxy-proxy.mean())*1000; f0 = (fea-fea.mean())*1000; res = p0-f0
    vm = max(np.abs(p0).max(), np.abs(f0).max()); vr = np.abs(res).max()
    for col, (title, data, cmap, lim) in enumerate([
            (f'{name}° Proxy  PV={m["pv_proxy_mm"]:.1f}mm', p0, 'RdYlBu_r', vm),
            (f'{name}° FEA(local δ)  PV={m["pv_fea_mm"]:.1f}mm', f0, 'RdYlBu_r', vm),
            (f'Residual  RMS={m["rms_mm"]:.2f}  R²={m["r2"]:.3f}\nshapeCorr={m["shape_corr"]:.3f} slopeCorr={m["slope_corr"]:.3f}', res, 'RdBu_r', vr)]):
        ax = axes[row, col]
        im = ax.pcolormesh(Xg, Zg, data, cmap=cmap, shading='auto', vmin=-lim, vmax=lim)
        ax.scatter(BX, BZ, c='k', s=8)
        ax.set_title(title, fontsize=9, fontweight='bold'); ax.set_aspect('equal')
        ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)'); plt.colorbar(im, ax=ax, label='mm')
fig.suptitle('North 300m deformation: proxy vs FEA (NLGEOM-ON, local plate-normal, dense bins)',
             fontsize=13, fontweight='bold', y=0.995)
plt.tight_layout(rect=[0, 0, 1, 0.98])
out = f'{RES}/deform_north_tilt.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)
json.dump(results, open(f'{RES}/deform_north_tilt.json', 'w'), indent=2)
print(f"saved: {out}")
