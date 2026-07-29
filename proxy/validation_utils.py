#!/usr/bin/env python3
"""
Shared validation utilities for proxy vs FEA comparison.
Provides: FEA loading, coordinate mapping, comparison metrics, visualization.
"""
import numpy as np
from scipy.interpolate import griddata
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import json, os

# ── Plate geometry constants ──
W, L = 12.84, 9.45           # plate width, length (m)
GS = 32                       # render grid size
NB = 35                       # number of bolts
TILT_DEG = 58.5               # FEA tilt angle
THETA = np.radians(TILT_DEG)  # radians
COS_T = np.cos(THETA)         # ≈ 0.5225
SIN_T = np.sin(THETA)         # ≈ 0.8526
Z_SCALE = L / (2 * 2.48)      # 9.45 / 4.96 ≈ 1.905 — map FEA global z to plate-local z

# ── Bolt positions ──
MARGIN = 0.08
BU = np.linspace(MARGIN, 1 - MARGIN, 7)
BV = np.linspace(MARGIN, 1 - MARGIN, 5)
BX = np.array([(u - 0.5) * W for v in BV for u in BU])
BZ = np.array([(v - 0.5) * L for v in BV for u in BU])

# ── Evaluation grid (plate-local) ──
X_GRID = np.linspace(-W / 2, W / 2, GS)
Z_GRID = np.linspace(-L / 2, L / 2, GS)
Xg, Zg = np.meshgrid(X_GRID, Z_GRID)


def load_fea_data(path='proxy/node_dump_585deg_nograv.csv'):
    """Load FEA node dump, extract plate-local coords and normal displacement.

    Returns:
        x_plate, z_plate: plate-local coordinates (m) for each FEA node
        u_local: plate-local normal displacement (m)
        x_grid, z_grid: 25×25 grid coordinates
        u_grid: u_local interpolated to 25×25 grid
    """
    data = np.loadtxt(path, delimiter=',', skiprows=1)
    x_global, z_global = data[:, 0], data[:, 2]
    uy, uz = data[:, 4], data[:, 5]

    # Project global displacement to plate-local normal
    u_local = uy * COS_T + uz * SIN_T  # plate-normal displacement

    # Map global coords to plate-local coords
    x_plate = x_global                  # width direction is horizontal
    z_plate = z_global * Z_SCALE        # scale projected length to actual length

    # Interpolate to 25×25 grid
    u_grid = griddata((x_plate, z_plate), u_local, (Xg, Zg), method='linear')
    nan_mask = np.isnan(u_grid)
    if nan_mask.any():
        u_nn = griddata((x_plate, z_plate), u_local, (Xg, Zg), method='nearest')
        u_grid[nan_mask] = u_nn[nan_mask]

    return x_plate, z_plate, u_local, X_GRID, Z_GRID, u_grid


def load_bolt_strokes(path='proxy/North_300m_STROKE_bolts.txt'):
    """Load 35 bolt stroke heights (m)."""
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    return np.array([float(l) for l in lines])


def compute_proxy_surface(phi, bolt_strokes):
    """Compute proxy surface: w(x,z) = Σ h_b · φ_b(x,z).

    Args:
        phi: [35, GS, GS] influence functions
        bolt_strokes: [35] bolt heights (m)
    Returns:
        w_proxy: [GS, GS] proxy deformation (m)
    """
    w = np.zeros((GS, GS))
    for b in range(NB):
        if abs(bolt_strokes[b]) > 1e-12:
            w += bolt_strokes[b] * phi[b]
    return w


def compare_with_fea(w_proxy, u_grid_fea, method_name, out_dir):
    """Compare proxy surface with FEA and generate visualization.

    Args:
        w_proxy: [GS, GS] proxy deformation (m)
        u_grid_fea: [GS, GS] FEA deformation on same grid (m)
        method_name: string label
        out_dir: directory to save outputs

    Returns:
        metrics: dict with rms_mm, r2, pv_ratio, max_err_mm
    """
    os.makedirs(out_dir, exist_ok=True)

    # De-mean both fields
    w_proxy_dm = w_proxy - np.mean(w_proxy)
    u_fea_dm = u_grid_fea - np.mean(u_grid_fea)

    # Residual
    residual = w_proxy_dm - u_fea_dm

    # Metrics
    rms = np.sqrt(np.mean(residual ** 2)) * 1000  # mm
    max_err = np.max(np.abs(residual)) * 1000      # mm
    sst = np.sum((u_fea_dm - np.mean(u_fea_dm)) ** 2)
    r2 = 1.0 - np.sum(residual ** 2) / max(sst, 1e-30)
    pv_proxy = (w_proxy_dm.max() - w_proxy_dm.min()) * 1000
    pv_fea = (u_fea_dm.max() - u_fea_dm.min()) * 1000
    pv_ratio = pv_proxy / max(pv_fea, 1e-10)

    metrics = {
        'method': method_name,
        'rms_mm': float(rms),
        'max_err_mm': float(max_err),
        'r2': float(r2),
        'pv_proxy_mm': float(pv_proxy),
        'pv_fea_mm': float(pv_fea),
        'pv_ratio': float(pv_ratio),
    }

    # Save metrics
    with open(os.path.join(out_dir, 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)

    # ── Visualization ──
    fig = plt.figure(figsize=(20, 10))
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35,
                  width_ratios=[1, 1, 1], height_ratios=[1, 0.7])

    vm_surf = max(abs(w_proxy_dm).max(), abs(u_fea_dm).max()) * 1000
    vm_err = max(abs(residual).max() * 1000, 0.01)

    # Row 1: Proxy | FEA | Residual
    titles_top = [
        f'{method_name}\nPV={pv_proxy:.2f}mm',
        f'FEA (nograv, {TILT_DEG}°)\nPV={pv_fea:.2f}mm',
        f'Residual\nRMS={rms:.3f}mm  R²={r2:.4f}'
    ]
    data_top = [w_proxy_dm * 1000, u_fea_dm * 1000, residual * 1000]
    cmaps = ['RdYlBu_r', 'RdYlBu_r', 'RdBu_r']
    vmin_vmax = [(-vm_surf, vm_surf), (-vm_surf, vm_surf), (-vm_err, vm_err)]

    for col in range(3):
        ax = fig.add_subplot(gs[0, col])
        im = ax.pcolormesh(Xg, Zg, data_top[col], cmap=cmaps[col], shading='auto',
                           vmin=vmin_vmax[col][0], vmax=vmin_vmax[col][1])
        ax.set_title(titles_top[col], fontsize=10, fontweight='bold')
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

    # Row 2 left: center cross-section
    ax_xs = fig.add_subplot(gs[1, 0])
    mid_row = GS // 2
    ax_xs.plot(X_GRID, w_proxy_dm[mid_row, :] * 1000, 'b-', lw=2, label=f'{method_name}')
    ax_xs.plot(X_GRID, u_fea_dm[mid_row, :] * 1000, 'r--', lw=1.5, label='FEA')
    ax_xs.set_xlabel('x (m)'); ax_xs.set_ylabel('w (mm)')
    ax_xs.set_title(f'Center cross-section (z=0)', fontsize=10, fontweight='bold')
    ax_xs.legend(fontsize=8); ax_xs.grid(True, alpha=0.3)

    # Row 2 middle: per-row RMS
    ax_rms = fig.add_subplot(gs[1, 1])
    rms_per_row = np.array([np.sqrt(np.mean(residual[i, :] ** 2)) * 1000 for i in range(GS)])
    ax_rms.plot(Z_GRID, rms_per_row, 'b-o', ms=3, label=f'Mean={rms_per_row.mean():.2f}mm')
    ax_rms.fill_between(Z_GRID, 0, rms_per_row, alpha=0.15, color='blue')
    ax_rms.axhline(y=2.0, color='gray', ls='--', alpha=0.5, label='2mm')
    ax_rms.set_xlabel('z (m)'); ax_rms.set_ylabel('RMS error (mm)')
    ax_rms.set_title('Per-row RMS error', fontsize=10, fontweight='bold')
    ax_rms.legend(fontsize=8); ax_rms.grid(True, alpha=0.3)

    # Row 2 right: metrics table
    ax_tbl = fig.add_subplot(gs[1, 2])
    ax_tbl.axis('off')
    tbl_text = (
        f"Metrics — {method_name}\n"
        f"{'='*40}\n"
        f"  RMS error:     {rms:.4f} mm\n"
        f"  Max error:     {max_err:.4f} mm\n"
        f"  R-squared:     {r2:.6f}\n"
        f"  PV ratio:      {pv_ratio:.4f}\n"
        f"  Proxy PV:      {pv_proxy:.2f} mm\n"
        f"  FEA PV:        {pv_fea:.2f} mm\n"
        f"{'='*40}\n"
        f"  Bolt strokes:  {os.path.basename(str(load_bolt_strokes.__defaults__[0]))}\n"
    )
    ax_tbl.text(0.05, 0.95, tbl_text, transform=ax_tbl.transAxes,
                fontsize=9, fontfamily='monospace', va='top',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    fig.suptitle(f'Proxy Model Validation: {method_name} vs FEA',
                 fontsize=13, fontweight='bold', y=0.98)
    plt.savefig(os.path.join(out_dir, 'comparison.png'), dpi=150,
                bbox_inches='tight', facecolor='white')
    plt.close(fig)

    return metrics


def validate_method(phi, phi_u, phi_v, method_name, out_dir,
                     bolt_path='proxy/North_300m_STROKE_bolts.txt',
                     fea_path='proxy/node_dump_585deg_nograv.csv'):
    """Full validation pipeline for one method.

    Args:
        phi, phi_u, phi_v: [35, GS, GS] influence functions
        method_name: label for outputs
        out_dir: output directory
        bolt_path, fea_path: data file paths

    Returns:
        metrics dict
    """
    print(f"\n{'='*60}")
    print(f"Validating: {method_name}")
    print(f"{'='*60}")

    # Load bolt strokes and FEA
    h = load_bolt_strokes(bolt_path)
    _, _, _, _, _, u_grid_fea = load_fea_data(fea_path)

    print(f"  Bolt strokes: [{h.min()*1000:.2f}, {h.max()*1000:.2f}] mm")
    print(f"  FEA u_local PV: {np.ptp(u_grid_fea)*1000:.2f} mm")

    # Compute proxy surface
    w_proxy = compute_proxy_surface(phi, h)
    print(f"  Proxy PV: {np.ptp(w_proxy)*1000:.2f} mm")

    # Compare
    metrics = compare_with_fea(w_proxy, u_grid_fea, method_name, out_dir)

    # Save influence data
    np.save(os.path.join(out_dir, 'influence_phi.npy'), phi)
    np.save(os.path.join(out_dir, 'influence_phi_u.npy'), phi_u)
    np.save(os.path.join(out_dir, 'influence_phi_v.npy'), phi_v)
    np.save(os.path.join(out_dir, 'proxy_surface.npy'), w_proxy)

    # Print summary
    print(f"\n  Results for {method_name}:")
    print(f"    RMS = {metrics['rms_mm']:.4f} mm")
    print(f"    R^2  = {metrics['r2']:.4f}")
    print(f"    PV ratio = {metrics['pv_ratio']:.4f}")
    print(f"  Outputs: {out_dir}/")

    return metrics


# ── TPS kernel and derivatives (shared across methods) ──
def tps_kernel(r2):
    """TPS kernel r²·log(r²), safe at r=0."""
    r2 = np.maximum(r2, 1e-30)
    return r2 * np.log(r2)


def tps_dx(dx, dz):
    """∂φ/∂x = 2x(1+log(r²))"""
    r2 = np.maximum(dx * dx + dz * dz, 1e-30)
    return 2.0 * dx * (np.log(r2) + 1.0)


def tps_dz(dx, dz):
    """∂φ/∂z = 2z(1+log(r²))"""
    r2 = np.maximum(dx * dx + dz * dz, 1e-30)
    return 2.0 * dz * (np.log(r2) + 1.0)


def tps_d2x(dx, dz):
    """∂²φ/∂x²"""
    r2 = np.maximum(dx * dx + dz * dz, 1e-30)
    return 2.0 * np.log(r2) + 2.0 + 4.0 * dx * dx / r2


def tps_d2z(dx, dz):
    """∂²φ/∂z²"""
    r2 = np.maximum(dx * dx + dz * dz, 1e-30)
    return 2.0 * np.log(r2) + 2.0 + 4.0 * dz * dz / r2


def tps_d2xz(dx, dz):
    """∂²φ/∂x∂z"""
    r2 = np.maximum(dx * dx + dz * dz, 1e-30)
    return 4.0 * dx * dz / r2
