#!/usr/bin/env python3
"""
2D deformation validation: physics proxy vs FEA for the ellipse-bump bolt
arrangement (train_data/ellipse_heights/bolt_heights.txt), at tilt 12/35/52 deg.

Proxy (local plate-frame surface equation, matches C++ bolt_common.slang):
    UY_proxy(theta) = gravity_interp(theta) + sum_b h_b * phi_b     (NO cos-theta)
  - gravity_interp: linear interp of data_vsm_mnvn_tik32 gravity bins (NLGEOM-ON)
    between bracketing known angles {0,30,45,60,75}.
  - sum_b h_b*phi_b: bolt plate-normal deflection. In the local plate frame the
    bolt response is phi directly (dy/dh = phi), so NO cos-theta factor.
    cos-theta enters ONLY via gravity-angle bin selection, never the bolt term.

FEA reference: train_data/ellipse_heights/node_dump_{theta}deg.csv (gravity+bolts,
tilted). Z is compressed by cos(theta) in the tilted model -> un-compress
(z_flat = z / cos) before interpolating global UY onto the flat 32x32 grid.

Output: train_data/ellipse_heights/deform_proxy_vs_fea.png + metrics.json
"""
import os, json
import numpy as np
from scipy.interpolate import griddata as gd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = 'L:/Code/bezier_opt_desktop'
ELL = os.path.join(BASE, 'train_data/ellipse_heights')
GDIR = os.path.join(BASE, 'data_vsm_mnvn_tik32')
W, L, GS, NB = 12.84, 9.45, 32, 35
ANGLES = [12, 35, 52]
KNOWN = [0, 12, 22, 30, 35, 45, 52, 60, 67, 75]   # dense bins (12/35/52 exact, no interp)

X_GRID = np.linspace(-W/2, W/2, GS)
Z_GRID = np.linspace(-L/2, L/2, GS)
Xg, Zg = np.meshgrid(X_GRID, Z_GRID)          # (GS,GS): axis0=z, axis1=x

# bolt positions (7x5, 8% margin) for per-bolt error
BU = np.linspace(0.08, 0.92, 7); BV = np.linspace(0.08, 0.92, 5)
BX = np.array([(u-0.5)*W for v in BV for u in BU])
BZ = np.array([(v-0.5)*L for v in BV for u in BU])


def project_fea(csv, ang):
    d = np.loadtxt(csv, delimiter=',', skiprows=1)
    x, z_tilt, uy = d[:, 0], d[:, 2], d[:, 4]
    cth = np.cos(np.deg2rad(ang))
    z_flat = z_tilt if ang == 0 else z_tilt / cth
    inp = (np.abs(x) <= W/2 + 0.02) & (np.abs(z_flat) <= L/2 + 0.02)
    g = gd((x[inp], z_flat[inp]), uy[inp], (Xg, Zg), method='linear')
    m = np.isnan(g)
    if m.any():
        g[m] = gd((x[inp], z_flat[inp]), uy[inp], (Xg, Zg), method='nearest')[m]
    return g


# gravity bins + influence
gbin = {a: np.fromfile(f'{GDIR}/gravity_{a}deg.bin', np.float32).reshape(GS, GS) for a in KNOWN}
phi = np.fromfile(f'{GDIR}/influence_phi.bin', np.float32).reshape(NB, GS, GS)
h = np.array([float(l) for l in open(f'{ELL}/bolt_heights.txt') if l.strip() and not l.startswith('#')])
bolt_plate = np.tensordot(h, phi, axes=(0, 0))   # plate-normal deflection Σ h·φ
print(f"ellipse bolts: min={h.min()*1000:.2f} max={h.max()*1000:.2f} PV={np.ptp(h)*1000:.2f} mm")


def grav_interp(theta):
    if theta in gbin:
        return gbin[theta]
    for i in range(len(KNOWN)-1):
        a, b = KNOWN[i], KNOWN[i+1]
        if a <= theta <= b:
            t = (theta - a)/(b - a)
            return gbin[a] + t*(gbin[b] - gbin[a])
    return gbin[KNOWN[-1]]


def stats(proxy, fea, trim=2):
    # interior, piston-invariant (re-center both on the trimmed region — matches
    # shape_corr, which is piston-invariant; the arbitrary reference plane is not error)
    p = (proxy - proxy.mean())[trim:-trim, trim:-trim]
    f = (fea - fea.mean())[trim:-trim, trim:-trim]
    p = p - p.mean(); f = f - f.mean()
    res = p - f
    rms = np.sqrt(np.mean(res**2))*1000
    r2 = 1 - np.sum(res**2)/max(np.sum(f*f), 1e-30)
    return dict(rms_mm=float(rms), r2=float(r2),
                pv_proxy_mm=float(np.ptp(proxy)*1000), pv_fea_mm=float(np.ptp(fea)*1000),
                pv_ratio=float(np.ptp(proxy)/max(np.ptp(fea), 1e-30)),
                max_bolt_err_mm=0.0)


results = {}
fig, axes = plt.subplots(len(ANGLES), 3, figsize=(15, 4.4*len(ANGLES)))
for row, ang in enumerate(ANGLES):
    proxy = grav_interp(ang) + bolt_plate          # local plate-frame: NO cos-theta
    fea = project_fea(f'{ELL}/node_dump_{ang}deg.csv', ang)
    m = stats(proxy, fea)
    # per-bolt error (de-meaned)
    p0, f0 = (proxy-proxy.mean())*1000, (fea-fea.mean())*1000
    berr = []
    for bi in range(NB):
        gi = int(np.argmin(np.abs(Z_GRID - BZ[bi]))); gj = int(np.argmin(np.abs(X_GRID - BX[bi])))
        berr.append(p0[gi, gj]-f0[gi, gj])
    m['max_bolt_err_mm'] = float(np.abs(berr).max())
    results[f'{ang}deg'] = m
    print(f"theta={ang:2d}deg  RMS={m['rms_mm']:.3f}mm  R2={m['r2']:.4f}  "
          f"PV proxy/fea={m['pv_proxy_mm']:.2f}/{m['pv_fea_mm']:.2f}mm  "
          f"maxBoltErr={m['max_bolt_err_mm']:.2f}mm")

    res = p0 - f0
    vm = max(np.abs(p0).max(), np.abs(f0).max())
    vr = np.abs(res).max()
    for col, (title, data, cmap, lim) in enumerate([
            (f'{ang}° Proxy  PV={m["pv_proxy_mm"]:.1f}mm', p0, 'RdYlBu_r', vm),
            (f'{ang}° FEA    PV={m["pv_fea_mm"]:.1f}mm', f0, 'RdYlBu_r', vm),
            (f'Residual  RMS={m["rms_mm"]:.2f}  R²={m["r2"]:.3f}', res, 'RdBu_r', vr)]):
        ax = axes[row, col]
        im = ax.pcolormesh(Xg, Zg, data, cmap=cmap, shading='auto', vmin=-lim, vmax=lim)
        ax.scatter(BX, BZ, c='k', s=8)
        ax.set_title(title, fontsize=10, fontweight='bold'); ax.set_aspect('equal')
        ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

fig.suptitle('Ellipse-bump bolts: physics proxy vs FEA (with gravity, de-meaned)',
             fontsize=13, fontweight='bold', y=0.997)
plt.tight_layout(rect=[0, 0, 1, 0.99])
out = f'{ELL}/deform_proxy_vs_fea.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
plt.close(fig)
json.dump(results, open(f'{ELL}/deform_metrics.json', 'w'), indent=2)
print(f"\nsaved: {out}\nsaved: {ELL}/deform_metrics.json")
