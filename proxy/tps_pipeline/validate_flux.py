#!/usr/bin/env python3
"""
TPS Proxy Pipeline: Flux Spot Validation.

Uses the TPS-computed surface normals to ray-trace reflected sunlight
onto a cylindrical receiver. Compares the flux spot from:
  1. Flat reference surface (all bolt heights = 0)
  2. TPS proxy surface (optimized bolt heights)

Provides a simplified geometric optics validation proving the
surface -> normal -> ray -> flux pipeline is correct.
"""

import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validation_utils import W, L, NB, X_GRID, Z_GRID, Xg, Zg

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = SCRIPT_DIR

# Receiver parameters matching C++ pipeline
RECEIVER_RADIUS = 10.0   # m (cylinder radius)
RECEIVER_HEIGHT = 20.0   # m
RECEIVER_Y = 180.0        # m above origin

# Heliostat position
HELIO_POS = np.array([0.0, 0.0, 300.0])  # (x, y, z)

# Receiver pixel grid
RECE_PW = 157  # pixels around cylinder
RECE_PH = 50   # pixels vertically


def build_receiver_grid():
    """Build cylindrical receiver pixel centers in world coordinates."""
    angle = np.linspace(0, 2 * np.pi, RECE_PW, endpoint=False)
    height = np.linspace(RECEIVER_Y - RECEIVER_HEIGHT / 2,
                         RECEIVER_Y + RECEIVER_HEIGHT / 2, RECE_PH)

    # Cylinder surface points
    x_rec = RECEIVER_RADIUS * np.sin(angle)  # (PW,)
    z_rec = -RECEIVER_RADIUS * np.cos(angle)  # (PW,)
    y_rec = height  # (PH,)

    # Full grid
    Xr = x_rec[np.newaxis, :]  # (1, PW)
    Zr = z_rec[np.newaxis, :]  # (1, PW)
    Yr = y_rec[:, np.newaxis]  # (PH, 1)

    return Xr, Yr, Zr


def trace_reflection(normals, sun_dir, helio_pos=HELIO_POS):
    """Compute reflected ray directions from surface normals.

    Reflection law: R = I - 2(I·N)N  where I = incoming direction (sun -> surface)

    Args:
        normals: (GS, GS, 3) surface normal vectors
        sun_dir: (3,) sun direction (pointing FROM sun TO heliostat)
        helio_pos: (3,) heliostat position (for ray origin)

    Returns:
        ray_dirs: (GS, GS, 3) reflected ray directions
        ray_origins: (GS, GS, 3) ray origins on surface
    """
    # Normalize
    I = -sun_dir / np.linalg.norm(sun_dir)  # incoming direction (TO surface)
    N = normals / np.linalg.norm(normals, axis=-1, keepdims=True)

    # Reflection
    dot_IN = np.sum(I * N, axis=-1, keepdims=True)
    R = I - 2.0 * dot_IN * N
    R = R / np.linalg.norm(R, axis=-1, keepdims=True)

    # Ray origins: surface points in world frame
    # Simplified: heliostat is at (0,0,300), surface in local (x,y,z) = (Xg, w, Zg)
    # In world: helio_pos + local_offset
    origins = np.zeros((Xg.shape[0], Xg.shape[1], 3))
    origins[:, :, 0] = Xg + helio_pos[0]
    origins[:, :, 2] = Zg + helio_pos[2]
    origins[:, :, 1] = helio_pos[1]  # y = 0 in local frame

    return R, origins


def intersect_cylinder(ray_origins, ray_dirs, receiver_radius=RECEIVER_RADIUS):
    """Intersect rays with a vertical cylinder of given radius.

    Cylinder: x^2 + z^2 = R^2, centered on y-axis.

    For ray O + t*D:
      (Ox + t*Dx)^2 + (Oz + t*Dz)^2 = R^2

    Quadratic in t: a*t^2 + b*t + c = 0
      a = Dx^2 + Dz^2
      b = 2*(Ox*Dx + Oz*Dz)
      c = Ox^2 + Oz^2 - R^2

    Returns:
        hit_points: valid hit points (N_valid, 3)
        hit_weights: ray weights (N_valid,)
    """
    Ox = ray_origins[:, :, 0]
    Oy = ray_origins[:, :, 1]
    Oz = ray_origins[:, :, 2]
    Dx = ray_dirs[:, :, 0]
    Dy = ray_dirs[:, :, 1]
    Dz = ray_dirs[:, :, 2]

    a = Dx * Dx + Dz * Dz
    b = 2.0 * (Ox * Dx + Oz * Dz)
    c = Ox * Ox + Oz * Oz - receiver_radius * receiver_radius

    disc = b * b - 4.0 * a * c

    # Only forward hits (t > 0)
    valid = disc > 0
    disc_valid = disc[valid]

    t1 = (-b[valid] - np.sqrt(disc_valid)) / (2.0 * a[valid])
    t2 = (-b[valid] + np.sqrt(disc_valid)) / (2.0 * a[valid])

    # Take closer positive t
    t_hit = np.where((t1 > 0) & (t1 < t2), t1, t2)
    t_hit = np.where(t_hit > 0, t_hit, np.nan)

    ok = ~np.isnan(t_hit)

    hit_x = Ox[valid][ok] + t_hit[ok] * Dx[valid][ok]
    hit_y = Oy[valid][ok] + t_hit[ok] * Dy[valid][ok]
    hit_z = Oz[valid][ok] + t_hit[ok] * Dz[valid][ok]

    # Simple weight: 1/r^2 attenuation
    r = t_hit[ok]
    weights = 1.0 / (r * r + 1.0)

    return np.column_stack([hit_x, hit_y, hit_z]), weights


def accumulate_flux(hit_points, weights, Xr, Yr, Zr):
    """Accumulate ray hits into receiver flux grid.

    For each hit, find nearest receiver pixel and add weight.
    """
    flux = np.zeros((RECE_PH, RECE_PW))

    if len(hit_points) == 0:
        return flux

    # Receiver pixel centers
    angle_centers = np.arctan2(Xr[0, :], -Zr[0, :])
    angle_centers = np.where(angle_centers < 0, angle_centers + 2 * np.pi, angle_centers)

    for k in range(len(hit_points)):
        hx, hy, hz = hit_points[k]

        # Find nearest pixel
        hit_angle = np.arctan2(hx, -hz)
        if hit_angle < 0:
            hit_angle += 2 * np.pi

        # Nearest angle pixel
        angle_diffs = np.abs(angle_centers - hit_angle)
        angle_diffs = np.minimum(angle_diffs, 2 * np.pi - angle_diffs)
        pw_idx = np.argmin(angle_diffs)

        # Nearest height pixel
        ph_idx = np.argmin(np.abs(Yr[:, 0] - hy))

        flux[ph_idx, pw_idx] += weights[k]

    return flux


def compute_s95_area(flux):
    """Compute S95 area: fraction of pixels containing 95% of energy."""
    total = flux.sum()
    if total == 0:
        return 0.0

    sorted_flux = np.sort(flux.ravel())[::-1]
    cumsum = np.cumsum(sorted_flux)
    n95 = np.searchsorted(cumsum, 0.95 * total) + 1
    return n95 / len(sorted_flux)


def main():
    print("=" * 64)
    print("TPS Proxy Pipeline: Flux Spot Validation")
    print("=" * 64)

    # Load optimized surface normals
    normals_opt = np.load(os.path.join(OUT_DIR, 'normals_optimized.npy'))
    print(f"\nLoaded normals: {normals_opt.shape}")

    # Compute flat reference normals
    normals_flat = np.zeros_like(normals_opt)
    normals_flat[:, :, 1] = 1.0  # all pointing up

    # Build receiver grid
    Xr, Yr, Zr = build_receiver_grid()
    print(f"Receiver grid: {RECE_PH}x{RECE_PW}")

    # Sun direction: directly overhead (noon)
    sun_dir = np.array([0.0, 1.0, 0.0])

    # Trace flat reference
    print("\n[Trace] Flat reference...")
    R_flat, O_flat = trace_reflection(normals_flat, sun_dir)
    hits_flat, weights_flat = intersect_cylinder(R_flat, O_flat)
    flux_flat = accumulate_flux(hits_flat, weights_flat, Xr, Yr, Zr)

    # Trace optimized surface
    print("[Trace] Optimized TPS surface...")
    R_opt, O_opt = trace_reflection(normals_opt, sun_dir)
    hits_opt, weights_opt = intersect_cylinder(R_opt, O_opt)
    flux_opt = accumulate_flux(hits_opt, weights_opt, Xr, Yr, Zr)

    # Metrics
    s95_flat = compute_s95_area(flux_flat)
    s95_opt = compute_s95_area(flux_opt)

    # Peak concentration
    peak_flat = flux_flat.max()
    peak_opt = flux_opt.max()
    total_flat = flux_flat.sum()
    total_opt = flux_opt.sum()

    print(f"\nFlux Metrics:")
    print(f"  {'':>20s} {'Flat':>12s} {'TPS Optimized':>14s}")
    print(f"  {'S95 area frac:':>20s} {s95_flat:12.4f} {s95_opt:14.4f}")
    print(f"  {'Peak flux:':>20s} {peak_flat:12.4f} {peak_opt:14.4f}")
    print(f"  {'Total energy:':>20s} {total_flat:12.4f} {total_opt:14.4f}")
    print(f"  {'Hit count:':>20s} {len(hits_flat):12d} {len(hits_opt):14d}")

    # Visualization
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(18, 8))
    gs = GridSpec(1, 3, figure=fig, wspace=0.35, width_ratios=[1, 1, 0.6])

    vm = max(flux_flat.max(), flux_opt.max()) * 1.05

    # Flat flux
    ax1 = fig.add_subplot(gs[0, 0])
    im1 = ax1.pcolormesh(flux_flat, cmap='inferno', shading='auto', vmin=0, vmax=vm)
    ax1.set_title(f'Flat Reference\nS95={s95_flat:.4f}, peak={peak_flat:.4f}',
                  fontsize=10, fontweight='bold')
    ax1.set_xlabel('Receiver column (angle)'); ax1.set_ylabel('Receiver row (height)')
    plt.colorbar(im1, ax=ax1, label='Flux')

    # Optimized flux
    ax2 = fig.add_subplot(gs[0, 1])
    im2 = ax2.pcolormesh(flux_opt, cmap='inferno', shading='auto', vmin=0, vmax=vm)
    ax2.set_title(f'TPS Optimized Surface\nS95={s95_opt:.4f}, peak={peak_opt:.4f}',
                  fontsize=10, fontweight='bold')
    ax2.set_xlabel('Receiver column (angle)'); ax2.set_ylabel('Receiver row (height)')
    plt.colorbar(im2, ax=ax2, label='Flux')

    # Difference
    ax3 = fig.add_subplot(gs[0, 2])
    diff = flux_opt - flux_flat
    vm_diff = max(abs(diff).max(), 1e-10)
    im3 = ax3.pcolormesh(diff, cmap='RdBu_r', shading='auto', vmin=-vm_diff, vmax=vm_diff)
    ax3.set_title(f'Difference (TPS - Flat)\nrange=[{diff.min():.4f}, {diff.max():.4f}]',
                  fontsize=10, fontweight='bold')
    ax3.set_xlabel('Receiver column'); ax3.set_ylabel('Receiver row')
    plt.colorbar(im3, ax=ax3, label='Delta flux')

    fig.suptitle('Flux Spot Validation: TPS Proxy Surface vs Flat Reference',
                 fontsize=13, fontweight='bold', y=0.98)
    plt.savefig(os.path.join(OUT_DIR, 'flux_comparison.png'), dpi=150,
                bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"\nSaved: {os.path.join(OUT_DIR, 'flux_comparison.png')}")

    # Also visualize the normals
    fig2, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Normal x-component
    im_nx = axes[0].pcolormesh(Xg, Zg, normals_opt[:, :, 0], cmap='RdBu_r', shading='auto')
    axes[0].set_title('Normal x (surface tilt x)')
    axes[0].set_aspect('equal')
    plt.colorbar(im_nx, ax=axes[0])

    # Normal y-component
    im_ny = axes[1].pcolormesh(Xg, Zg, normals_opt[:, :, 1], cmap='viridis', shading='auto')
    axes[1].set_title('Normal y (surface normal up)')
    axes[1].set_aspect('equal')
    plt.colorbar(im_ny, ax=axes[1])

    # Normal z-component
    im_nz = axes[2].pcolormesh(Xg, Zg, normals_opt[:, :, 2], cmap='RdBu_r', shading='auto')
    axes[2].set_title('Normal z (surface tilt z)')
    axes[2].set_aspect('equal')
    plt.colorbar(im_nz, ax=axes[2])

    fig2.suptitle('TPS Surface Normals (Optimized)', fontsize=13, fontweight='bold')
    plt.savefig(os.path.join(OUT_DIR, 'normals.png'), dpi=150,
                bbox_inches='tight', facecolor='white')
    plt.close(fig2)
    print(f"Saved: {os.path.join(OUT_DIR, 'normals.png')}")

    # Save metrics
    import json
    metrics = {
        's95_flat': float(s95_flat),
        's95_optimized': float(s95_opt),
        'peak_flux_flat': float(peak_flat),
        'peak_flux_optimized': float(peak_opt),
        'total_energy_flat': float(total_flat),
        'total_energy_optimized': float(total_opt),
    }
    with open(os.path.join(OUT_DIR, 'flux_metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)

    print("\nDone.")
    return metrics


if __name__ == '__main__':
    main()
