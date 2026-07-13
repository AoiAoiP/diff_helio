#!/usr/bin/env python3
"""
Angle interpolation validation: 35° and 75°.

Proxy formula:
  UY_proxy(θ) = UY_grav_interp(θ) + cosθ × Σ h_b·φ_b_VSM

Gravity interpolation:
  35°: lerp(gravity_30deg, gravity_45deg, t=1/3)
  75°: extrapolate from 60° trend (⚠ beyond known range)

FEA references expected at:
  train_data/zero_heights/node_dump_{35,75}deg.csv      (gravity)
  train_data/ellipse_heights/node_dump_{35,75}deg.csv    (gravity + bolts)
"""
import numpy as np
from pathlib import Path
from scipy.interpolate import griddata as gd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

W, L, GS = 12.84, 9.45, 32          # matches current pipeline (was 25)
NB = 35
extent = [-W/2, W/2, -L/2, L/2]

base_dir = Path(__file__).parent.parent.parent
DATA_DIR = base_dir / "data_vsm_mnvn_tik32"            # influence + gravity bins (was data_vsm_tik25)
SRC_DIR = base_dir / "train_data" / "zero_heights_ON"  # zero-bolt FEA gravity (NLGEOM-ON)
out_dir = base_dir / "train_data" / "correction_output"
out_dir.mkdir(parents=True, exist_ok=True)

u = np.linspace(0, 1, GS); v = np.linspace(0, 1, GS)
Ug, Vg = np.meshgrid(u, v)
X_flat = (Ug - 0.5) * W; Z_flat = (Vg - 0.5) * L
margin = 0.08
bu = np.linspace(margin, 1-margin, 7); bv = np.linspace(margin, 1-margin, 5)
bx_arr = np.array([(u-0.5)*W for v in bv for u in bu])
bz_arr = np.array([(v-0.5)*L for v in bv for u in bu])

# ---- Load influence + bolt heights ----
phi = np.fromfile(str(DATA_DIR / 'influence_phi.bin'),
                   dtype=np.float32).reshape(NB, GS, GS)
# Bolt heights: ellipse reference if present, else zeros (gravity-only check).
h_path = base_dir / 'train_data' / 'ellipse_heights' / 'bolt_heights.txt'
if h_path.exists():
    h_ellip = np.loadtxt(str(h_path))
else:
    print(f"WARN: {h_path} missing -> zero bolts (gravity-only validation)")
    h_ellip = np.zeros(NB)
w_bolt_plate = np.tensordot(h_ellip, phi, axes=([0], [0]))

# ---- Load pre-computed gravity bins ----
known_angles = [0, 30, 45, 60, 75]
gravity_bins = {}
for ang in known_angles:
    bin_path = DATA_DIR / f'gravity_{ang}deg.bin'
    gravity_bins[ang] = np.fromfile(str(bin_path), dtype=np.float32).reshape(GS, GS)
print("Loaded gravity bins:", list(gravity_bins.keys()))

# ---- Interpolation function ----
def interpolate_gravity(theta):
    """Linear interpolation of gravity UY at angle theta (degrees)."""
    if theta in known_angles:
        return gravity_bins[theta]

    if theta < known_angles[0]:
        # Extrapolate below 0° — clamp to 0°
        print(f"  ⚠ θ={theta}° below known range, clamped to 0°")
        return gravity_bins[0]

    if theta > known_angles[-1]:
        # Extrapolate above 60° — use trend from last two angles
        a1, a2 = known_angles[-2], known_angles[-1]
        t_extrap = (theta - a2) / (a2 - a1)
        result = gravity_bins[a2] + t_extrap * (gravity_bins[a2] - gravity_bins[a1])
        print(f"  ⚠ θ={theta}° beyond known range (max={known_angles[-1]}°): "
              f"extrapolated from {a1}°→{a2}° (t_extrap={t_extrap:.2f})")
        return result

    # Linear interpolation between two nearest angles
    for i in range(len(known_angles) - 1):
        if known_angles[i] <= theta <= known_angles[i+1]:
            a1, a2 = known_angles[i], known_angles[i+1]
            t = (theta - a1) / (a2 - a1)
            g1, g2 = gravity_bins[a1], gravity_bins[a2]
            return g1 + t * (g2 - g1)

    return gravity_bins[known_angles[-1]]  # fallback


# ---- Helper: load tilted FEA ----
def load_tilted_fea(csv_path, ang):
    if not csv_path.exists():
        return None, 0
    cos_th = np.cos(np.deg2rad(ang))
    fea_raw = np.loadtxt(str(csv_path), delimiter=',', skiprows=1)
    if fea_raw.shape[1] >= 7:
        x_fea, z_fea_tilt, uy_fea = fea_raw[:,0], fea_raw[:,2], fea_raw[:,4]
    else:
        x_fea, z_fea_tilt, uy_fea = fea_raw[:,0], fea_raw[:,1], fea_raw[:,2]
    z_fea_flat = z_fea_tilt if ang == 0 else z_fea_tilt / cos_th
    in_plate = (np.abs(x_fea) <= W/2 + 0.02) & (np.abs(z_fea_flat) <= L/2 + 0.02)
    grid = gd((x_fea[in_plate], z_fea_flat[in_plate]), uy_fea[in_plate],
              (X_flat.ravel(), Z_flat.ravel()), method='linear').reshape(GS, GS)
    n_nan = 0
    nan_mask = np.isnan(grid)
    n_nan = nan_mask.sum()
    if n_nan:
        near = gd((x_fea[in_plate], z_fea_flat[in_plate]), uy_fea[in_plate],
                  (X_flat.ravel(), Z_flat.ravel()), method='nearest').reshape(GS, GS)
        grid[nan_mask] = near[nan_mask]
    return grid, n_nan


# ---- Validate target angles ----
target_angles = [12, 35, 52, 75]
results = {}

fig = plt.figure(figsize=(18, 18), facecolor='white')
fig.suptitle("Angle Interpolation Validation\n"
             "12°/35°/52°: lerp between known bins  |  75°: now a known bin",
             fontsize=13, fontweight='bold', y=0.995)

for row, ang in enumerate(target_angles):
    cos_th = np.cos(np.deg2rad(ang))

    print(f"\n{'='*70}")
    print(f"θ={ang}°  cosθ={cos_th:.4f}")

    # Gravity: interpolated
    grav_uy = interpolate_gravity(ang)
    print(f"  Gravity (interp):  PV={np.ptp(grav_uy)*1000:.1f}mm")

    # Bolt
    uy_bolt = w_bolt_plate * cos_th

    # Total proxy
    uy_proxy = grav_uy + uy_bolt
    print(f"  Proxy total:       PV={np.ptp(uy_proxy)*1000:.1f}mm")

    # FEA reference (if available)
    fea_zero_path = SRC_DIR / f'node_dump_{ang}deg.csv'
    fea_ellip_path = base_dir / 'train_data' / 'ellipse_heights' / f'node_dump_{ang}deg.csv'

    fea_grav, _ = load_tilted_fea(fea_zero_path, ang)
    fea_ref, _ = load_tilted_fea(fea_ellip_path, ang)

    if fea_ref is not None:
        diff = uy_proxy - fea_ref
        rms = np.sqrt(np.mean(diff**2)) * 1000
        ss_res = np.sum(diff**2)
        ss_tot = np.sum((fea_ref - fea_ref.mean())**2)
        r2 = 1 - ss_res / max(ss_tot, 1e-30)

        bolt_errs = []
        for bi in range(NB):
            gi = np.argmin(np.abs(u - bv[bi//7]))
            gj = np.argmin(np.abs(u - bu[bi%7]))
            bolt_errs.append(diff[gi, gj] * 1000)
        bolt_errs = np.array(bolt_errs)

        print(f"  FEA ref PV:        {np.ptp(fea_ref)*1000:.1f}mm")
        print(f"  RMS:  {rms:.4f} mm")
        print(f"  R²:   {r2:.4f}")
        print(f"  max|Δbolt|: {abs(bolt_errs).max():.4f} mm")

        results[ang] = dict(uy_proxy=uy_proxy, fea_ref=fea_ref, diff=diff,
                            rms=rms, r2=r2,
                            pv_proxy=np.ptp(uy_proxy)*1000,
                            pv_ref=np.ptp(fea_ref)*1000)
    else:
        print(f"  ⚠ FEA reference NOT FOUND at {fea_ellip_path}")
        print(f"    → Please generate: ellipse_heights/node_dump_{ang}deg.csv in Ansys")
        results[ang] = dict(uy_proxy=uy_proxy, fea_ref=None, diff=None)

    # ---- Plot ----
    last_row = (row == len(target_angles) - 1)
    im_args = dict(cmap='RdBu_r', aspect='auto', extent=extent, origin='lower',
                   interpolation='bilinear')

    vlim_row = max(abs(uy_proxy.max()), abs(uy_proxy.min()))
    if fea_ref is not None:
        vlim_row = max(vlim_row, abs(fea_ref.max()), abs(fea_ref.min()))
    vlim_row *= 1000

    # Proxy
    ax = fig.add_subplot(len(target_angles), 3, row*3 + 1)
    im = ax.imshow(uy_proxy*1000, vmin=-vlim_row, vmax=vlim_row, **im_args)
    ax.set_title(f"θ={ang}°  Proxy (interp)\nPV={np.ptp(uy_proxy)*1000:.1f}mm",
                 fontsize=10, pad=4)
    if last_row: ax.set_xlabel("x (m)"); ax.set_ylabel("z (m)")
    else: ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=ax, shrink=0.82, label="UY (mm)")

    # FEA Reference
    ax = fig.add_subplot(len(target_angles), 3, row*3 + 2)
    if fea_ref is not None:
        im = ax.imshow(fea_ref*1000, vmin=-vlim_row, vmax=vlim_row, **im_args)
        ax.set_title(f"FEA Reference\nPV={np.ptp(fea_ref)*1000:.1f}mm", fontsize=10, pad=4)
        fig.colorbar(im, ax=ax, shrink=0.82, label="UY (mm)")
    else:
        ax.text(0.5, 0.5, f"FEA data missing\n\nPlease generate:\nellipse_heights/\nnode_dump_{ang}deg.csv",
                ha='center', va='center', fontsize=10, transform=ax.transAxes)
        ax.set_title(f"FEA Reference (MISSING)", fontsize=10, pad=4)
    if last_row: ax.set_xlabel("x (m)")
    else: ax.set_xticks([]); ax.set_yticks([])

    # Residual
    ax = fig.add_subplot(len(target_angles), 3, row*3 + 3)
    if fea_ref is not None:
        vlim_res = max(abs(diff.max()), abs(diff.min())) * 1000
        im = ax.imshow(diff*1000, vmin=-vlim_res, vmax=vlim_res, **im_args)
        ax.set_title(f"Residual  RMS={rms:.4f}mm  R²={r2:.4f}", fontsize=10, pad=4)
        fig.colorbar(im, ax=ax, shrink=0.82, label="ΔUY (mm)")
    else:
        ax.axis('off')
    if last_row: ax.set_xlabel("x (m)")
    else: ax.set_xticks([]); ax.set_yticks([])

plt.tight_layout(pad=1.2)
out_path = out_dir / "validation_interpolation.png"
fig.savefig(str(out_path), dpi=150, bbox_inches='tight', facecolor='white')
plt.close(fig)

# ---- Summary ----
print(f"\n{'='*70}")
print(f"Interpolation Validation Summary")
print(f"{'='*70}")
for ang in target_angles:
    if ang in results and results[ang]['fea_ref'] is not None:
        r = results[ang]
        print(f"  θ={ang}°: PV_proxy={r['pv_proxy']:.1f}mm  PV_ref={r['pv_ref']:.1f}mm  "
              f"RMS={r['rms']:.4f}mm  R²={r['r2']:.4f}")
    else:
        print(f"  θ={ang}°: FEA reference PENDING — waiting for Ansys data")

print(f"\nSaved: {out_path}")
print(f"\nNext step: generate FEA data in Ansys for 35° and 75°:")
print(f"  1. zero_heights/node_dump_35deg.csv and node_dump_75deg.csv")
print(f"  2. ellipse_heights/node_dump_35deg.csv and node_dump_75deg.csv")
print(f"  3. Re-run this script to validate")
