#!/usr/bin/env python3
"""
0-degree (flat plate) deformation comparison: linear TPS proxy vs FEA.

Compares three surfaces on the 32x32 render grid, all WITH gravity, for the
optimized bolt-height distribution from results_vsm_mnvn_300iter:

  proxy    = gravity_0deg(FEA, zero-bolt) + Σ h_b · φ_b        (linear superposition)
  FEA-OFF  = geometrically-linear FEA (NLGEOM off)
  FEA-ON   = large-deflection FEA      (NLGEOM on)

The proxy is an inherently LINEAR model, so proxy≈FEA-OFF validates the TPS
surrogate, while (FEA-ON − FEA-OFF) isolates the pure NLGEOM (membrane
stiffening) effect that the proxy cannot represent.

Bolts are prescribed-displacement BCs → at bolt nodes ON==OFF; NLGEOM only
acts in the free spans between bolts.

Usage:
  python scripts/validate_nlgeom_0deg.py
"""
import os, sys, json
import numpy as np
from scipy.interpolate import griddata
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# ── constants ──
W, L = 12.84, 9.45
GS, NB = 32, 35
RESULT_DIR = 'results_vsm_mnvn_300iter'
INFLU_DIR  = 'data_vsm_mnvn_tik32'
OUT_DIR    = 'validation_nlgeom_0deg'

X_GRID = np.linspace(-W/2, W/2, GS)
Z_GRID = np.linspace(-L/2, L/2, GS)
Xg, Zg = np.meshgrid(X_GRID, Z_GRID)   # (GS,GS): axis0=z, axis1=x

# bolt positions (7x5, 8% margin)
BU = np.linspace(0.08, 0.92, 7)
BV = np.linspace(0.08, 0.92, 5)
BX = np.array([(u-0.5)*W for v in BV for u in BU])
BZ = np.array([(v-0.5)*L for v in BV for u in BU])


def load_strokes(path):
    with open(path) as f:
        vals = [float(l) for l in f if l.strip() and not l.startswith('#')]
    return np.array(vals)


def load_fea_0deg(path):
    """Flat plate: normal disp = uy, plate-local coords = global (x, z)."""
    d = np.loadtxt(path, delimiter=',', skiprows=1)
    x, z, uy = d[:, 0], d[:, 2], d[:, 4]
    u = griddata((x, z), uy, (Xg, Zg), method='linear')
    m = np.isnan(u)
    if m.any():
        u[m] = griddata((x, z), uy, (Xg, Zg), method='nearest')[m]
    return u


def metrics(a, b, trim=2):
    """De-meaned shape comparison a vs b (reference=b). Returns dict in mm.

    Reports both full-grid and interior (edge-trimmed) values. griddata linear
    interpolation produces nearest-fill artifacts at the plate corners, so the
    interior (trim-ring removed) numbers are the physically meaningful ones.
    """
    a0, b0 = a - a.mean(), b - b.mean()
    res = a0 - b0
    def _stats(r, ref):
        rms = np.sqrt(np.mean(r**2)) * 1000
        mx = np.abs(r).max() * 1000
        sst = np.sum((ref - ref.mean())**2)
        r2 = 1.0 - np.sum(r**2)/max(sst, 1e-30)
        return float(rms), float(mx), float(r2)
    rms, mx, r2 = _stats(res, b0)
    ri, mi, r2i = _stats(res[trim:-trim, trim:-trim], b0[trim:-trim, trim:-trim])
    return dict(rms_mm=ri, max_mm=mi, r2=r2i,              # interior = primary
                rms_full_mm=rms, max_full_mm=mx, r2_full=r2,
                pv_a_mm=float(np.ptp(a0)*1000), pv_b_mm=float(np.ptp(b0)*1000),
                pv_ratio=float(np.ptp(a0)/max(np.ptp(b0), 1e-30)))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # ── load ──
    h = load_strokes(os.path.join(RESULT_DIR, 'North_300m_STROKE_bolts.txt'))
    grav = np.fromfile(os.path.join(INFLU_DIR, 'gravity_0deg.bin'),
                       dtype=np.float32).reshape(GS, GS)          # [z,x], m, signed
    phi = np.fromfile(os.path.join(INFLU_DIR, 'influence_phi.bin'),
                      dtype=np.float32).reshape(NB, GS, GS)        # [b,z,x]

    bolt_term = np.tensordot(h, phi, axes=(0, 0))                  # Σ h_b φ_b  [z,x]
    proxy = grav + bolt_term                                       # m

    fea_on  = load_fea_0deg(os.path.join(RESULT_DIR, 'node_dump_0deg_ON.csv'))
    fea_off = load_fea_0deg(os.path.join(RESULT_DIR, 'node_dump_0deg_OFF.csv'))

    # ── surfaces (de-meaned, mm) ──
    surfs = {'proxy': proxy, 'FEA-OFF': fea_off, 'FEA-ON': fea_on}
    dm = {k: (v - v.mean())*1000 for k, v in surfs.items()}

    # ── pairwise metrics ──
    M = {
        'proxy_vs_FEAoff': metrics(proxy, fea_off),   # TPS linear fidelity
        'proxy_vs_FEAon':  metrics(proxy, fea_on),    # total proxy error vs reality
        'FEAon_vs_FEAoff': metrics(fea_on, fea_off),  # pure NLGEOM effect
    }
    # raw (non-demeaned) PV for physical magnitudes
    raw_pv = {k: float(np.ptp(v)*1000) for k, v in surfs.items()}
    nlgeom_diff = (fea_on - fea_off)*1000  # mm, signed
    M['raw_pv_mm'] = raw_pv
    M['nlgeom_reduces_PV_mm'] = raw_pv['FEA-OFF'] - raw_pv['FEA-ON']
    M['nlgeom_reduces_PV_pct'] = 100*(raw_pv['FEA-OFF'] - raw_pv['FEA-ON'])/raw_pv['FEA-OFF']
    M['nlgeom_maxabs_diff_mm'] = float(np.abs(nlgeom_diff).max())
    # NLGEOM spatial structure: is the stiffening co-located with the gravity sag?
    grav_dm = (grav - grav.mean()).ravel()
    M['corr_nlgeom_vs_gravity'] = float(np.corrcoef(nlgeom_diff.ravel(), grav_dm)[0, 1])
    M['gravity_term_PV_mm'] = float(np.ptp(grav)*1000)
    M['bolt_term_PV_mm'] = float(np.ptp(bolt_term)*1000)

    with open(os.path.join(OUT_DIR, 'metrics.json'), 'w') as f:
        json.dump(M, f, indent=2)

    # ── print summary ──
    print("="*70)
    print("0deg flat-plate deformation: linear TPS proxy vs FEA (with gravity)")
    print("="*70)
    print(f"bolt strokes: min={h.min()*1000:.2f}  max={h.max()*1000:.2f} mm  (plate 4mm)")
    print(f"proxy terms:  gravity PV={M['gravity_term_PV_mm']:.2f}  "
          f"bolt PV={M['bolt_term_PV_mm']:.2f} mm")
    print(f"raw PV (mm):  proxy={raw_pv['proxy']:.2f}  "
          f"FEA-OFF={raw_pv['FEA-OFF']:.2f}  FEA-ON={raw_pv['FEA-ON']:.2f}")
    print("-"*70)
    print(f"{'comparison':22s} {'RMS_int':>8s} {'max_int':>8s} {'R2_int':>7s}"
          f" | {'RMS_full':>8s}")
    for k in ['proxy_vs_FEAoff', 'proxy_vs_FEAon', 'FEAon_vs_FEAoff']:
        m = M[k]
        print(f"{k:22s} {m['rms_mm']:7.3f}  {m['max_mm']:7.3f}  {m['r2']:6.3f}"
              f" | {m['rms_full_mm']:7.3f}")
    print("  (int = interior, 2-cell boundary ring trimmed to drop interp artifacts)")
    print("-"*70)
    print(f"NLGEOM reduces PV by {M['nlgeom_reduces_PV_mm']:.2f} mm "
          f"({M['nlgeom_reduces_PV_pct']:.1f}%),  max|ON-OFF|={M['nlgeom_maxabs_diff_mm']:.2f} mm")
    print(f"corr(ON-OFF, gravity_shape) = {M['corr_nlgeom_vs_gravity']:+.3f}  "
          f"(negative => stiffening lifts gravity-sag valleys)")
    print("="*70)

    # ── figure: 3 surfaces (row0) + 3 residuals (row1) + 2 cross-sections (row2) ──
    fig = plt.figure(figsize=(18, 15))
    gs = GridSpec(3, 3, figure=fig, hspace=0.32, wspace=0.30)

    vm = max(abs(dm['proxy']).max(), abs(dm['FEA-OFF']).max(), abs(dm['FEA-ON']).max())
    # row 0: surfaces
    for col, key in enumerate(['proxy', 'FEA-OFF', 'FEA-ON']):
        ax = fig.add_subplot(gs[0, col])
        im = ax.pcolormesh(Xg, Zg, dm[key], cmap='RdYlBu_r', shading='auto', vmin=-vm, vmax=vm)
        ax.scatter(BX, BZ, c='k', s=14, marker='o', label='bolts')
        ax.set_title(f'{key}  (de-meaned)\nrawPV={raw_pv[key]:.2f} mm', fontweight='bold')
        ax.set_aspect('equal'); ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

    # row 1: residual maps
    resid = {
        'proxy − FEA-OFF\n(TPS linear error)': dm['proxy'] - dm['FEA-OFF'],
        'proxy − FEA-ON\n(total proxy error)': dm['proxy'] - dm['FEA-ON'],
        'FEA-ON − FEA-OFF\n(pure NLGEOM effect)': dm['FEA-ON'] - dm['FEA-OFF'],
    }
    vmr = max(abs(v).max() for v in resid.values())
    for col, (title, data) in enumerate(resid.items()):
        ax = fig.add_subplot(gs[1, col])
        im = ax.pcolormesh(Xg, Zg, data, cmap='RdBu_r', shading='auto', vmin=-vmr, vmax=vmr)
        ax.scatter(BX, BZ, c='k', s=10, marker='o')
        rms = np.sqrt(np.mean((data)**2))
        ax.set_title(f'{title}\nRMS={rms:.3f} mm', fontweight='bold')
        ax.set_aspect('equal'); ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

    # row 2 left: center cross-section z=0 (along x)
    ax = fig.add_subplot(gs[2, 0])
    r = GS//2
    ax.plot(X_GRID, dm['proxy'][r], 'b-', lw=2, label='proxy (linear)')
    ax.plot(X_GRID, dm['FEA-OFF'][r], 'g--', lw=1.6, label='FEA-OFF (linear)')
    ax.plot(X_GRID, dm['FEA-ON'][r], 'r-.', lw=1.6, label='FEA-ON (NLGEOM)')
    ax.set_title('Cross-section z=0 (along x)', fontweight='bold')
    ax.set_xlabel('x (m)'); ax.set_ylabel('w (mm)'); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # row 2 mid: center cross-section x=0 (along z)
    ax = fig.add_subplot(gs[2, 1])
    c = GS//2
    ax.plot(Z_GRID, dm['proxy'][:, c], 'b-', lw=2, label='proxy (linear)')
    ax.plot(Z_GRID, dm['FEA-OFF'][:, c], 'g--', lw=1.6, label='FEA-OFF (linear)')
    ax.plot(Z_GRID, dm['FEA-ON'][:, c], 'r-.', lw=1.6, label='FEA-ON (NLGEOM)')
    ax.set_title('Cross-section x=0 (along z)', fontweight='bold')
    ax.set_xlabel('z (m)'); ax.set_ylabel('w (mm)'); ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # row 2 right: metrics text
    ax = fig.add_subplot(gs[2, 2]); ax.axis('off')
    txt = (
        "0° flat plate — with gravity\n" + "="*40 + "\n"
        f"bolt stroke max: {h.max()*1000:.2f} mm  (plate 4mm)\n"
        f"raw PV:  proxy   {raw_pv['proxy']:6.2f} mm\n"
        f"         FEA-OFF {raw_pv['FEA-OFF']:6.2f} mm\n"
        f"         FEA-ON  {raw_pv['FEA-ON']:6.2f} mm\n"
        + "-"*40 + "\n"
        f"proxy vs FEA-OFF (TPS fidelity):\n"
        f"   RMS {M['proxy_vs_FEAoff']['rms_mm']:.3f}  R² {M['proxy_vs_FEAoff']['r2']:.4f}\n"
        f"proxy vs FEA-ON  (vs reality):\n"
        f"   RMS {M['proxy_vs_FEAon']['rms_mm']:.3f}  R² {M['proxy_vs_FEAon']['r2']:.4f}\n"
        f"FEA-ON vs FEA-OFF (NLGEOM):\n"
        f"   RMS {M['FEAon_vs_FEAoff']['rms_mm']:.3f}  R² {M['FEAon_vs_FEAoff']['r2']:.4f}\n"
        + "-"*40 + "\n"
        f"NLGEOM stiffening:\n"
        f"   PV  {raw_pv['FEA-OFF']:.2f} → {raw_pv['FEA-ON']:.2f} mm "
        f"(−{M['nlgeom_reduces_PV_pct']:.1f}%)\n"
        f"   max|ON−OFF| = {M['nlgeom_maxabs_diff_mm']:.2f} mm\n"
    )
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, fontsize=10,
            fontfamily='monospace', va='top',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.85))

    fig.suptitle('0° Deformation: Linear TPS Proxy vs FEA (NLGEOM on/off)  —  '
                 'optimized 300-iter bolts', fontsize=14, fontweight='bold', y=0.995)
    out = os.path.join(OUT_DIR, 'deformation_0deg_nlgeom.png')
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"saved: {out}")
    print(f"saved: {os.path.join(OUT_DIR, 'metrics.json')}")


if __name__ == '__main__':
    main()
