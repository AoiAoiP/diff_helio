#!/usr/bin/env python3
"""
NLGEOM impact on the PURE-GRAVITY (zero-bolt) plate response, and the
consequence for the physics proxy's gravity term.

Part A — pure gravity ON vs OFF at all tilt angles (zero bolts):
  isolates the geometric-nonlinearity (membrane stiffening) effect on the
  gravity sag alone, with NO bolt-displacement coupling.

Part B — which gravity baseline the proxy should use (0deg, optimized bolts):
  proxy_ON  = G_on  + Σ h_b·φ_b     (nonlinear gravity + linear bolts)
  proxy_OFF = G_off + Σ h_b·φ_b     (linear    gravity + linear bolts)
  compared against FEA-with-bolts ON (reality) and OFF (linear).

  Linear superposition predicts proxy_OFF ≡ FEA-OFF exactly (φ are the linear
  unit-bolt responses, G_off the linear zero-bolt gravity). The decisive
  question is which proxy best predicts FEA-ON (the real, nonlinear surface).

Data:
  train_data/zero_heights_{ON,OFF}/node_dump_{ang}deg.csv   (pure gravity)
  results_vsm_mnvn_300iter/node_dump_0deg_{ON,OFF}.csv       (gravity + 33mm bolts)
  data_vsm_mnvn_tik32/influence_phi.bin, .../North_300m_STROKE_bolts.txt
"""
import os, json
import numpy as np
from scipy.interpolate import griddata as gd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = 'L:/Code/bezier_opt_desktop'
W, L, GS, NB = 12.84, 9.45, 32, 35
OUT = os.path.join(BASE, 'validation_nlgeom_gravity')
os.makedirs(OUT, exist_ok=True)

X_GRID = np.linspace(-W/2, W/2, GS)
Z_GRID = np.linspace(-L/2, L/2, GS)
Xg, Zg = np.meshgrid(X_GRID, Z_GRID)   # (GS,GS): axis0=z, axis1=x
ANGLES = [0, 30, 45, 60, 75]


def project_uy(csv_path, ang):
    """Project scattered FEA UY onto the flat-plate 32x32 grid (un-compress Z)."""
    d = np.loadtxt(csv_path, delimiter=',', skiprows=1)
    if d.shape[1] >= 7:
        x, z_tilt, uy = d[:, 0], d[:, 2], d[:, 4]
    else:
        x, z_tilt, uy = d[:, 0], d[:, 1], d[:, 2]
    cth = np.cos(np.deg2rad(ang))
    z_flat = z_tilt if ang == 0 else z_tilt / cth
    inp = (np.abs(x) <= W/2 + 0.02) & (np.abs(z_flat) <= L/2 + 0.02)
    g = gd((x[inp], z_flat[inp]), uy[inp], (Xg, Zg), method='linear')
    m = np.isnan(g)
    if m.any():
        g[m] = gd((x[inp], z_flat[inp]), uy[inp], (Xg, Zg), method='nearest')[m]
    return g


def rms_interior(a, b, trim=2):
    """De-meaned interior RMS (mm), ring trimmed to drop griddata edge artifacts."""
    r = (a - a.mean()) - (b - b.mean())
    return np.sqrt(np.mean(r[trim:-trim, trim:-trim]**2)) * 1000


# ══════════════════════════════════════════════════════════════════
# Part A — pure gravity NLGEOM effect, all angles
# ══════════════════════════════════════════════════════════════════
print("="*72)
print("Part A — PURE gravity (zero bolts): NLGEOM ON vs OFF")
print("="*72)
print(f"{'ang':>4} {'PV_ON':>8} {'PV_OFF':>8} {'OFF/ON':>7} {'reduce%':>8} "
      f"{'RMS(on-off)':>12} {'max|diff|':>10}")
partA = {}
G = {}  # G[(ang,tag)] grid
for ang in ANGLES:
    on = project_uy(f'{BASE}/train_data/zero_heights_ON/node_dump_{ang}deg.csv', ang)
    off = project_uy(f'{BASE}/train_data/zero_heights_OFF/node_dump_{ang}deg.csv', ang)
    G[(ang, 'ON')] = on; G[(ang, 'OFF')] = off
    pv_on, pv_off = np.ptp(on)*1000, np.ptp(off)*1000
    diff = (off - on)*1000
    rms = rms_interior(off, on)
    reduce_pct = 100*(pv_off - pv_on)/pv_off
    partA[ang] = dict(pv_on=float(pv_on), pv_off=float(pv_off),
                      reduce_pct=float(reduce_pct), rms_on_off_mm=float(rms),
                      maxabs_diff_mm=float(np.abs(diff).max()))
    print(f"{ang:>4} {pv_on:>8.2f} {pv_off:>8.2f} {pv_off/pv_on:>7.3f} "
          f"{reduce_pct:>7.1f}% {rms:>11.3f}  {np.abs(diff).max():>9.3f}")

# ══════════════════════════════════════════════════════════════════
# Part B — proxy gravity choice at 0deg (optimized 33mm bolts)
# ══════════════════════════════════════════════════════════════════
print("\n" + "="*72)
print("Part B — proxy gravity baseline (0deg, optimized bolts): ON vs OFF")
print("="*72)

h = np.array([float(l) for l in open(f'{BASE}/results_vsm_mnvn_300iter/North_300m_STROKE_bolts.txt')
              if l.strip() and not l.startswith('#')])
phi = np.fromfile(f'{BASE}/data_vsm_mnvn_tik32/influence_phi.bin', np.float32).reshape(NB, GS, GS)
bolt = np.tensordot(h, phi, axes=(0, 0))                    # Σ h_b φ_b

G_on0, G_off0 = G[(0, 'ON')], G[(0, 'OFF')]
proxy_on = G_on0 + bolt
proxy_off = G_off0 + bolt
fea_on = project_uy(f'{BASE}/results_vsm_mnvn_300iter/node_dump_0deg_ON.csv', 0)
fea_off = project_uy(f'{BASE}/results_vsm_mnvn_300iter/node_dump_0deg_OFF.csv', 0)

pairs = {
    'proxy_OFF vs FEA-OFF (superposition check)': (proxy_off, fea_off),
    'proxy_ON  vs FEA-ON  (reality, ON gravity)': (proxy_on, fea_on),
    'proxy_OFF vs FEA-ON  (reality, OFF gravity)': (proxy_off, fea_on),
    'proxy_ON  vs FEA-OFF                        ': (proxy_on, fea_off),
    'FEA-ON    vs FEA-OFF (bolted NLGEOM effect) ': (fea_on, fea_off),
}
partB = {}
print(f"{'comparison':46s} {'RMS_int(mm)':>12}")
for name, (a, b) in pairs.items():
    r = rms_interior(a, b)
    partB[name.strip()] = float(r)
    print(f"{name:46s} {r:>12.3f}")

print(f"\nraw PV (mm): G_on0={np.ptp(G_on0)*1000:.2f}  G_off0={np.ptp(G_off0)*1000:.2f}  "
      f"bolt={np.ptp(bolt)*1000:.2f}")
print(f"             proxy_ON={np.ptp(proxy_on)*1000:.2f}  proxy_OFF={np.ptp(proxy_off)*1000:.2f}  "
      f"FEA_ON={np.ptp(fea_on)*1000:.2f}  FEA_OFF={np.ptp(fea_off)*1000:.2f}")

verdict = ('USE ON  gravity' if partB['proxy_ON  vs FEA-ON  (reality, ON gravity)'] <
           partB['proxy_OFF vs FEA-ON  (reality, OFF gravity)'] else 'USE OFF gravity')
print(f"\n>>> Which gravity predicts reality (FEA-ON) better?  {verdict}")

with open(os.path.join(OUT, 'metrics.json'), 'w') as f:
    json.dump({'partA_pure_gravity': partA, 'partB_proxy_choice_0deg': partB,
               'verdict': verdict}, f, indent=2)

# ══════════════════════════════════════════════════════════════════
# Figures
# ══════════════════════════════════════════════════════════════════
# Fig 1: pure gravity NLGEOM — PV bar + 0deg fields + difference
fig = plt.figure(figsize=(18, 9))
gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.32)

ax = fig.add_subplot(gs[0, 0])
x = np.arange(len(ANGLES)); w = 0.38
ax.bar(x-w/2, [partA[a]['pv_on'] for a in ANGLES], w, label='ON (NLGEOM)', color='#c44')
ax.bar(x+w/2, [partA[a]['pv_off'] for a in ANGLES], w, label='OFF (linear)', color='#48a')
for i, a in enumerate(ANGLES):
    ax.text(i, partA[a]['pv_off']+0.4, f"-{partA[a]['reduce_pct']:.0f}%", ha='center', fontsize=8)
ax.set_xticks(x); ax.set_xticklabels([f'{a}°' for a in ANGLES])
ax.set_ylabel('gravity sag PV (mm)'); ax.set_title('Pure-gravity sag: NLGEOM vs linear', fontweight='bold')
ax.legend(); ax.grid(alpha=0.3, axis='y')

vm = max(np.ptp(G_off0), np.ptp(G_on0))*1000/2
for col, (name, fld) in enumerate([('G_on (NLGEOM)', G_on0), ('G_off (linear)', G_off0)]):
    ax = fig.add_subplot(gs[0, 1+col])
    im = ax.pcolormesh(Xg, Zg, (fld-fld.mean())*1000, cmap='RdYlBu_r', shading='auto', vmin=-vm, vmax=vm)
    ax.set_title(f'0°  {name}\nPV={np.ptp(fld)*1000:.1f}mm', fontweight='bold')
    ax.set_aspect('equal'); ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
    plt.colorbar(im, ax=ax, label='mm')

ax = fig.add_subplot(gs[1, 0])
d = (G_off0 - G_on0)*1000
im = ax.pcolormesh(Xg, Zg, d, cmap='Reds', shading='auto')
ax.set_title(f'0°  G_off − G_on (linear over-predicts sag)\nmax={d.max():.1f}mm', fontweight='bold')
ax.set_aspect('equal'); ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
plt.colorbar(im, ax=ax, label='mm')

# center cross-sections at 0deg
ax = fig.add_subplot(gs[1, 1])
r = GS//2
ax.plot(X_GRID, (G_on0-G_on0.mean())[r]*1000, 'r-', lw=2, label='G_on (NLGEOM)')
ax.plot(X_GRID, (G_off0-G_off0.mean())[r]*1000, 'b--', lw=1.8, label='G_off (linear)')
ax.set_title('0° gravity cross-section z=0', fontweight='bold')
ax.set_xlabel('x (m)'); ax.set_ylabel('sag (mm)'); ax.legend(fontsize=8); ax.grid(alpha=0.3)

ax = fig.add_subplot(gs[1, 2]); ax.axis('off')
txt = "Part B — 0° proxy gravity choice\n" + "="*38 + "\n"
for k, v in partB.items():
    txt += f"{v:6.3f} mm  {k}\n"
txt += "="*38 + f"\n>>> {verdict}\n(smaller RMS vs FEA-ON wins)"
ax.text(0.0, 0.98, txt, transform=ax.transAxes, va='top', fontsize=9,
        family='monospace', bbox=dict(boxstyle='round', facecolor='lightyellow'))

fig.suptitle('NLGEOM on pure gravity  &  proxy gravity-baseline choice',
             fontsize=14, fontweight='bold', y=0.98)
p = os.path.join(OUT, 'nlgeom_gravity.png')
plt.savefig(p, dpi=150, bbox_inches='tight', facecolor='white')
plt.close(fig)
print(f"\nsaved: {p}")
print(f"saved: {os.path.join(OUT, 'metrics.json')}")
