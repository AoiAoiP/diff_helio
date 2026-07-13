#!/usr/bin/env python3
"""
Ellipse validation deep-dive: slopeCorr (5-bin vs 10-bin) + 52deg R2 root cause.

For 12/35/52 deg, cross two axes:
  gravity set : 5-bin (0/30/45/60/75, from .bak5)  vs  10-bin dense (tik32)
  FEA frame   : global-uy (as validate_ellipse_deform)  vs  local-normal
                projection (uy*cos + uz*sin, = plate-normal delta)

Reports r(shape corr), slopeCorr, k(amplitude), R2 for every combination, to
(a) supply slopeCorr numbers for 5-bin & 10-bin, and
(b) isolate whether the 52deg R2 floor is the gravity-angle interp (fixed by
    dense bins), the comparison frame (global vs local), or a small-signal /
    Z-uncompression artifact.
"""
import numpy as np
from scipy.interpolate import griddata as gd
BASE = 'L:/Code/bezier_opt_desktop'; ELL = f'{BASE}/train_data/ellipse_heights'
W, L, GS, NB = 12.84, 9.45, 32, 35
X = np.linspace(-W/2, W/2, GS); Z = np.linspace(-L/2, L/2, GS); Xg, Zg = np.meshgrid(X, Z)

SPARSE = [0, 30, 45, 60, 75]
DENSE = [0, 12, 22, 30, 35, 45, 52, 60, 67, 75]
g_sparse = {a: np.fromfile(f'{BASE}/data_vsm_mnvn_tik32/gravity_{a}deg.bin.bak5', np.float32).reshape(GS, GS) for a in SPARSE}
g_dense = {a: np.fromfile(f'{BASE}/data_vsm_mnvn_tik32/gravity_{a}deg.bin', np.float32).reshape(GS, GS) for a in DENSE}
phi = np.fromfile(f'{BASE}/data_vsm_mnvn_tik32/influence_phi.bin', np.float32).reshape(NB, GS, GS)
h = np.array([float(l) for l in open(f'{ELL}/bolt_heights.txt') if l.strip() and not l.startswith('#')])
bolt = np.tensordot(h, phi, axes=(0, 0))


def interp(theta, angles, g):
    if theta in g: return g[theta]
    for i in range(len(angles)-1):
        a, b = angles[i], angles[i+1]
        if a <= theta <= b:
            t = (theta-a)/(b-a); return g[a]+t*(g[b]-g[a])
    return g[angles[-1]]


def fea_frame(csv, ang, frame):
    d = np.loadtxt(csv, delimiter=',', skiprows=1)
    x, zt, uy, uz = d[:, 0], d[:, 2], d[:, 4], d[:, 5]
    cth, sth = np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))
    zf = zt if ang == 0 else zt/cth
    u = uy if frame == 'global' else uy*cth + uz*sth   # local plate-normal delta
    inp = (np.abs(x) <= W/2+.02) & (np.abs(zf) <= L/2+.02)
    g = gd((x[inp], zf[inp]), u[inp], (Xg, Zg), 'linear'); m = np.isnan(g)
    if m.any(): g[m] = gd((x[inp], zf[inp]), u[inp], (Xg, Zg), 'nearest')[m]
    return g


def metrics(proxy, fea, t=2):
    a = (proxy-proxy.mean())[t:-t, t:-t]; b = (fea-fea.mean())[t:-t, t:-t]
    a = a-a.mean(); b = b-b.mean()
    r = np.sum(a*b)/np.sqrt(np.sum(a*a)*np.sum(b*b))
    k = np.std(a)/np.std(b)
    R2 = 1 - np.sum((a-b)**2)/np.sum(b*b)
    ax, az = np.gradient(a); bx, bz = np.gradient(b)
    sa = np.concatenate([ax.ravel(), az.ravel()]); sb = np.concatenate([bx.ravel(), bz.ravel()])
    sc = np.corrcoef(sa, sb)[0, 1]; sr = np.std(sa)/np.std(sb)
    return r, sc, k, R2, sr


print(f"{'ang':>4} {'grav':>6} {'frame':>7} {'shapeCorr':>9} {'slopeCorr':>9} {'k':>7} {'R2':>7} {'slopeRat':>8}")
print("-"*66)
for ang in [12, 35, 52]:
    for gname, angles, g in [('5bin', SPARSE, g_sparse), ('10bin', DENSE, g_dense)]:
        proxy = interp(ang, angles, g) + bolt
        for frame in ['global', 'local']:
            fea = fea_frame(f'{ELL}/node_dump_{ang}deg.csv', ang, frame)
            r, sc, k, R2, sr = metrics(proxy, fea)
            print(f"{ang:>4} {gname:>6} {frame:>7} {r:>9.4f} {sc:>9.4f} {k:>7.4f} {R2:>7.4f} {sr:>8.4f}")
    print("-"*66)
