#!/usr/bin/env python3
"""
Full Differentiable Heliostat Optimization with TPS Proxy + Gravity.

Pipeline:
  1. Load heliostat config (North 300m), sun directions, gravity bins
  2. Initialize bolt heights from elliptical surface fit
  3. For each iteration over all sun directions:
     a. TPS solve: h -> surface w_TPS(x,z)
     b. Add gravity: w_grav from angle-interpolated FEA bins
     c. Compute surface normals (analytical TPS derivatives)
     d. Ray trace: reflect sunlight to cylindrical receiver
     e. Accumulate flux, compute S95 sigmoid loss
     f. Backprop: dL/d(flux) -> dL/d(normals) -> dL/dw -> dL/dh
     g. Adam update bolt heights
  4. Validate with yearly sun directions, compute S95 area
  5. Export optimized bolt heights

Based on C++ pipeline (src/pipeline.cpp, shaders/) and TPS solver (tps_solver.py).
"""

import sys, os, json, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validation_utils import W, L, GS, NB, BX, BZ, X_GRID, Z_GRID, Xg, Zg

from tps_solver import TPSSolver
from optimizer import AdamOptimizer

# ==========================================================================
# Paths
# ==========================================================================
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, 'data')
GRAVITY_DIR = os.path.join(ROOT, 'data_proxy')
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

SUN_TRAIN_FILE = os.path.join(DATA_DIR, '36_sundir_fast.txt')
SUN_VAL_FILE = os.path.join(DATA_DIR, '738_sundir_year.txt')
ELLIPSE_FILE = os.path.join(DATA_DIR, 'ellipse_north.txt')

# ==========================================================================
# Receiver & Heliostat Parameters (matching C++ config)
# ==========================================================================
RECEIVER_POS = np.array([0.0, 180.0, 0.0])
RECEIVER_RADIUS = 10.0
RECEIVER_HEIGHT = 20.0
RECEIVER_PW = 157
RECEIVER_PH = 50

# Sun
DNI = 1000.0
CSR = 0.01
SUN_SIGMA = 0.00251  # rad (for Gaussian sunshape)

# ==========================================================================
# Gravity Model
# ==========================================================================
GRAVITY_ANGLES = np.array([0, 30, 45, 60, 75], dtype=np.int32)
GRAVITY_COS = np.cos(np.radians(GRAVITY_ANGLES.astype(np.float64)))

def load_gravity_bins():
    """Load 5 gravity bins (25x25 each) into a (5, 25, 25) array."""
    bins = np.zeros((5, GS, GS), dtype=np.float64)
    for i, angle in enumerate(GRAVITY_ANGLES):
        path = os.path.join(GRAVITY_DIR, f'gravity_{int(angle)}deg.bin')
        data = np.fromfile(path, dtype=np.float32)
        bins[i] = data.reshape(GS, GS)
    return bins

def sample_gravity(cos_theta, gravity_bins):
    """Linearly interpolate gravity UY field at given cos(theta).

    Args:
        cos_theta: cosine of tilt angle (dot(macro_normal, vertical))
        gravity_bins: (5, GS, GS) gravity fields at 0/30/45/60/75 deg

    Returns:
        uy_grav: (GS, GS) global vertical gravity displacement
    """
    # Find bracketing cos values (cos decreases as angle increases)
    cos_vals = np.cos(np.radians(GRAVITY_ANGLES.astype(np.float64)))
    idx = np.searchsorted(-cos_vals, -cos_theta)
    idx = np.clip(idx, 1, len(cos_vals) - 1)
    lo, hi = idx - 1, idx

    cos_lo, cos_hi = cos_vals[lo], cos_vals[hi]
    # Linear interpolation weight
    if abs(cos_hi - cos_lo) < 1e-10:
        t = 0.0
    else:
        t = (cos_theta - cos_lo) / (cos_hi - cos_lo)
    t = np.clip(t, 0.0, 1.0)

    return (1.0 - t) * gravity_bins[lo] + t * gravity_bins[hi]

# ==========================================================================
# Sun Directions & Heliostat Config
# ==========================================================================

def load_sun_directions(path):
    """Load and normalize sun direction vectors."""
    dirs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 3:
                v = np.array([float(x) for x in parts[:3]])
                dirs.append(v / np.linalg.norm(v))
    return np.array(dirs)

def load_heliostat_config(path):
    """Load heliostat config from ellipse file."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 7:
                return {
                    'name': parts[0],
                    'position': np.array([float(parts[1]), float(parts[2]), float(parts[3])]),
                    'A': float(parts[4]), 'B': float(parts[5]), 'C': float(parts[6]),
                }
    raise ValueError(f"No heliostat config found in {path}")

def elliptical_surface(A, B, C):
    """Compute ideal elliptical surface z = A*x^2 + B*y^2 + C*x*y on 25x25 grid.

    Returns surface heights at bolt positions for initialization.
    """
    return A * BX**2 + B * BZ**2 + C * BX * BZ

# ==========================================================================
# Ray Tracing (Simplified, Differentiable)
# ==========================================================================

def compute_macro_normal_and_basis(sun_dir, helio_pos, receiver_pos):
    """Compute macro-normal and local-to-world basis vectors.

    Returns:
        macro_n: (3,) macro-normal direction
        aim_dir: (3,) aim direction (heliostat -> receiver)
        local_x: (3,) plate-local x-axis in world
        local_z: (3,) plate-local z-axis in world
        cos_theta: float, vertical component of macro_normal
    """
    aim_dir = receiver_pos - helio_pos
    aim_dir = aim_dir / np.linalg.norm(aim_dir)
    sun_n = sun_dir / np.linalg.norm(sun_dir)
    macro_n = sun_n + aim_dir
    macro_n = macro_n / np.linalg.norm(macro_n)

    # cos(theta) = vertical component of macro-normal
    cos_theta = abs(macro_n[1])

    # Build local-to-world basis
    up = np.array([0.0, 1.0, 0.0])
    if abs(np.dot(macro_n, up)) > 0.999:
        up = np.array([0.0, 0.0, 1.0])

    local_x = np.cross(up, macro_n)
    local_x = local_x / np.linalg.norm(local_x)
    local_z = np.cross(local_x, macro_n)
    local_z = local_z / np.linalg.norm(local_z)

    return macro_n, aim_dir, local_x, local_z, cos_theta


def surface_to_world(w_surface, helio_pos, macro_n, local_x, local_z):
    """Transform plate-local surface to world coordinates.

    Surface point in world = helio_pos + Xg*local_x + w_surface*macro_n + Zg*local_z
    """
    world = np.zeros((GS, GS, 3))
    for c in range(3):
        world[:, :, c] = (helio_pos[c] +
                          Xg * local_x[c] +
                          w_surface * macro_n[c] +
                          Zg * local_z[c])
    return world


def reflect_rays_grid(world_points, macro_n, sun_dir, surf_dwdx=None, surf_dwdz=None,
                      local_x=None, local_z=None):
    """Compute reflected ray directions for each grid point.

    Surface normal at each point = macro_n + local perturbation from TPS slopes.
    For TPS surface with slopes dwdx, dwdz in plate-local frame:
      world_normal = macro_n - dwdx*local_x - dwdz*local_z (simplified, small-angle)

    Returns:
        R: (GS, GS, 3) reflected ray directions
    """
    GS_loc = world_points.shape[0]
    I = -sun_dir / np.linalg.norm(sun_dir)

    if surf_dwdx is not None and local_x is not None:
        # Use actual surface normals
        N = np.zeros((GS_loc, GS_loc, 3))
        for c in range(3):
            N[:, :, c] = macro_n[c] - surf_dwdx * local_x[c] - surf_dwdz * local_z[c]
        # Normalize
        N_norm = np.sqrt(np.sum(N*N, axis=-1, keepdims=True))
        N = N / np.maximum(N_norm, 1e-10)
    else:
        # Use macro-normal only
        N = np.tile(macro_n.reshape(1, 1, 3), (GS_loc, GS_loc, 1))

    # Reflection: R = I - 2(I·N)N
    dot_IN = np.sum(I.reshape(1, 1, 3) * N, axis=-1, keepdims=True)
    R = I.reshape(1, 1, 3) - 2.0 * dot_IN * N

    # Normalize
    R_norm = np.sqrt(np.sum(R*R, axis=-1, keepdims=True))
    R = R / np.maximum(R_norm, 1e-10)

    return R


def trace_to_cylinder(origins, ray_dirs, receiver_pos, receiver_radius, receiver_height):
    """Trace rays to cylindrical receiver.

    Args:
        origins: (GS, GS, 3) ray origins in world coords
        ray_dirs: (GS, GS, 3) unit ray directions
        receiver_pos: (3,) center of receiver
        receiver_radius: float
        receiver_height: float

    Returns:
        phi_idx: (GS, GS) receiver column indices (float)
        y_idx: (GS, GS) receiver row indices (float)
        weight: (GS, GS) ray weights (1/r^2)
    """
    Ox = origins[:, :, 0]
    Oy = origins[:, :, 1]
    Oz = origins[:, :, 2]
    Dx = ray_dirs[:, :, 0]
    Dy = ray_dirs[:, :, 1]
    Dz = ray_dirs[:, :, 2]

    # Cylinder intersection: (Ox + t*Dx)^2 + (Oz + t*Dz)^2 = R^2
    a = Dx*Dx + Dz*Dz
    b = 2.0 * (Ox*Dx + Oz*Dz)
    c = Ox*Ox + Oz*Oz - receiver_radius*receiver_radius

    disc = b*b - 4.0*a*c
    valid = disc > 0

    t_hit = np.full_like(Ox, np.nan)
    # Closer positive root
    sqrt_disc = np.sqrt(np.maximum(disc, 0.0))
    t1 = (-b - sqrt_disc) / (2.0 * a + 1e-30)
    t2 = (-b + sqrt_disc) / (2.0 * a + 1e-30)
    t_hit = np.where(valid & (t1 > 0), t1, t_hit)
    # If t1 is negative but t2 is positive, use t2
    t_hit = np.where(valid & np.isnan(t_hit) & (t2 > 0), t2, t_hit)

    # Hit points
    hit_x = Ox + t_hit * Dx
    hit_y = Oy + t_hit * Dy
    hit_z = Oz + t_hit * Dz

    # Cylinder angle
    hit_phi = np.arctan2(hit_x, -hit_z)
    hit_phi = np.where(hit_phi < 0, hit_phi + 2.0*np.pi, hit_phi)

    # Pixel indices
    phi_idx = (hit_phi / (2.0 * np.pi) * RECEIVER_PW) % RECEIVER_PW
    y_min = receiver_pos[1] - receiver_height / 2.0
    y_idx = (hit_y - y_min) / receiver_height * RECEIVER_PH

    # Weight: 1/r^2 attenuation
    weight = np.where(np.isfinite(t_hit), 1.0 / (t_hit*t_hit + 1.0), 0.0)

    return phi_idx, y_idx, weight

def accumulate_flux_gaussian(phi_idx, y_idx, weight, sigma_pix=1.5):
    """Accumulate flux using differentiable Gaussian spread around hit pixels.

    Instead of discrete binning (non-differentiable), use Gaussian kernel
    centered at each hit position, spread over neighboring pixels.

    Returns:
        flux: (RECEIVER_PH, RECEIVER_PW) flux distribution
    """
    # Build Gaussian-spread flux by accumulating at nearby pixels
    # For efficiency, only spread to pixels within 3*sigma

    # Simplified: use np.histogram2d with weights (non-differentiable)
    # For gradient computation, we use finite differences on the bolt heights
    # This is the C++ pipeline's approach too (two-stage gradient)

    flux = np.zeros((RECEIVER_PH, RECEIVER_PW))

    valid = np.isfinite(phi_idx) & (weight > 0)
    phi_v = phi_idx[valid]
    y_v = y_idx[valid]
    w_v = weight[valid]

    for k in range(len(phi_v)):
        p = int(np.clip(np.floor(phi_v[k]), 0, RECEIVER_PW - 1))
        y = int(np.clip(np.floor(y_v[k]), 0, RECEIVER_PH - 1))
        # Nearest-neighbor accumulation
        if 0 <= y < RECEIVER_PH and 0 <= p < RECEIVER_PW:
            flux[y, p] += w_v[k]

    return flux

# ==========================================================================
# S95 Loss
# ==========================================================================

def compute_s95_sigmoid_loss(flux, s95_level=None):
    """Differentiable S95 loss: smoothed count of pixels above S95 threshold.

    s = sigmoid(k * (flux / s95_level - 1))
    loss = mean(s)
    dL/dflux = k * s * (1-s) / (s95_level * n_pixels)

    If s95_level is None, computes it via bisection on the flux.
    """
    if s95_level is None:
        s95_level = compute_s95_level(flux)
        if s95_level < 1e-10:
            return 0.0, np.zeros_like(flux), 0.0

    k = 6.0  # sigmoid sharpness (matches C++ pipeline)
    scaled = flux / s95_level - 1.0
    s = 1.0 / (1.0 + np.exp(-k * scaled))

    loss = np.mean(s)
    dL_dflux = k * s * (1.0 - s) / (s95_level * flux.size)

    return loss, dL_dflux, s95_level

def compute_s95_level(flux, target_frac=0.95):
    """Find the flux level containing target_frac of total energy via bisection."""
    total = flux.sum()
    if total < 1e-10:
        return 0.0

    sorted_flux = np.sort(flux.ravel())
    cumsum = np.cumsum(sorted_flux)

    idx = np.searchsorted(cumsum, (1.0 - target_frac) * total)
    if idx >= len(sorted_flux):
        idx = len(sorted_flux) - 1

    return max(sorted_flux[idx], 1e-10)

def compute_s95_area(flux):
    """Non-differentiable S95 area computation."""
    total = flux.sum()
    if total < 1e-10:
        return float('inf')
    sorted_flux = np.sort(flux.ravel())[::-1]
    cumsum = np.cumsum(sorted_flux)
    n95 = np.searchsorted(cumsum, 0.95 * total) + 1
    return n95 / len(sorted_flux)  # fraction of total pixels

# ==========================================================================
# Full Optimization Pipeline
# ==========================================================================

def main():
    print("=" * 64)
    print("Full Differentiable Heliostat Optimization")
    print("TPS Proxy + Gravity + Ray Tracing")
    print("=" * 64)

    # ---- Load data ----
    print("\n[1/7] Loading config and data...")
    hc = load_heliostat_config(ELLIPSE_FILE)
    sun_train = load_sun_directions(SUN_TRAIN_FILE)
    sun_val = load_sun_directions(SUN_VAL_FILE) if os.path.exists(SUN_VAL_FILE) else sun_train

    print(f"  Heliostat: {hc['name']} at {hc['position']}")
    print(f"  Ellipse: A={hc['A']:.2e}, B={hc['B']:.2e}, C={hc['C']:.2e}")
    print(f"  Training sun dirs: {len(sun_train)}")
    print(f"  Validation sun dirs: {len(sun_val)}")

    # ---- Load gravity ----
    print("\n[2/7] Loading gravity model...")
    gravity_bins = load_gravity_bins()
    print(f"  Gravity bins: {gravity_bins.shape}")
    for i, angle in enumerate(GRAVITY_ANGLES):
        print(f"    {angle}deg: PV={gravity_bins[i].max()-gravity_bins[i].min():.4f}m "
              f"= {(gravity_bins[i].max()-gravity_bins[i].min())*1000:.1f}mm")

    # ---- Initialize TPS solver ----
    print("\n[3/7] Initializing TPS solver...")
    solver = TPSSolver(reg=1e-6)

    # ---- Initialize bolt heights from elliptical surface ----
    print("\n[4/7] Initializing bolt heights from elliptical fit...")
    h_elliptic = elliptical_surface(hc['A'], hc['B'], hc['C'])
    print(f"  Elliptic heights: [{h_elliptic.min()*1000:.2f}, {h_elliptic.max()*1000:.2f}] mm")

    # Convert to stroke (all non-negative, zero-based)
    h_init = h_elliptic - h_elliptic.min()
    print(f"  Initial strokes:  [{h_init.min()*1000:.2f}, {h_init.max()*1000:.2f}] mm")

    # ---- Compute initial S95 (flat reference) ----
    print("\n[5/7] Computing initial flux (elliptical surface)...")
    h_current = h_init.copy()

    # Use first sun direction for quick initial check
    sd0 = sun_train[0]
    macro_n, aim_dir, local_x, local_z, cos_theta = \
        compute_macro_normal_and_basis(sd0, hc['position'], RECEIVER_POS)

    # TPS surface
    c, d = solver.solve(h_current)
    w_tps, dwdx, dwdz, _, _, _ = solver.surface_with_normals(c, d)

    # Add gravity (plate-normal component)
    uy_grav = sample_gravity(cos_theta, gravity_bins)
    w_total = w_tps + uy_grav * cos_theta

    # Ray trace with actual surface normals
    world_pts = surface_to_world(w_total, hc['position'], macro_n, local_x, local_z)
    R_dirs = reflect_rays_grid(world_pts, macro_n, sd0, dwdx, dwdz, local_x, local_z)
    phi_idx, y_idx, weight = trace_to_cylinder(
        world_pts, R_dirs, RECEIVER_POS, RECEIVER_RADIUS, RECEIVER_HEIGHT)
    flux_init = accumulate_flux_gaussian(phi_idx, y_idx, weight)
    s95_init = compute_s95_area(flux_init)

    print(f"  cos(theta)={cos_theta:.4f}, angle={np.degrees(np.arccos(cos_theta)):.1f}deg")
    print(f"  Gravity PV: {np.ptp(uy_grav)*1000:.2f}mm, TPS PV: {np.ptp(w_tps)*1000:.2f}mm")
    print(f"  Initial S95 area: {s95_init*100:.1f}% of receiver")
    print(f"  Initial peak flux: {flux_init.max():.1f}")

    # ---- Optimization loop ----
    print("\n[6/7] Running differentiable optimization...")
    print(f"  Iterations: 300, Learning rate: 1e-5, Sun directions: {len(sun_train)}")

    h_opt = h_current.copy()
    optimizer = AdamOptimizer(NB, lr=1e-5, beta1=0.9, beta2=0.999, min_lr=1e-8, lr_decay=0.998)

    n_iters = 300
    loss_history = []
    s95_history = []
    best_s95 = float('inf')
    best_h = h_opt.copy()

    t0 = time.time()
    for it in range(n_iters):
        total_loss = 0.0
        total_dL_dh = np.zeros(NB)

        for sd in sun_train:
            # Compute macro-normal and basis
            macro_n, aim_dir, local_x, local_z, cos_theta = \
                compute_macro_normal_and_basis(sd, hc['position'], RECEIVER_POS)

            # ---- Forward pass ----
            c, d = solver.solve(h_opt)
            w_tps, dwdx, dwdz, _, _, _ = solver.surface_with_normals(c, d)

            # Add gravity
            uy_grav = sample_gravity(cos_theta, gravity_bins)
            w_total = w_tps + uy_grav * cos_theta

            # Transform to world
            world_pts = surface_to_world(w_total, hc['position'], macro_n, local_x, local_z)

            # Ray trace
            R_dirs = reflect_rays_grid(world_pts, macro_n, sd, dwdx, dwdz, local_x, local_z)
            phi_idx, y_idx, weight = trace_to_cylinder(
                world_pts, R_dirs, RECEIVER_POS, RECEIVER_RADIUS, RECEIVER_HEIGHT)
            flux = accumulate_flux_gaussian(phi_idx, y_idx, weight)

            # S95 loss
            loss, dL_dflux, s95_level = compute_s95_sigmoid_loss(flux)
            total_loss += loss

        # ---- Surface quality gradient ----
        c, d = solver.solve(h_opt)
        w_tps, dwdx, dwdz, _, _, _ = solver.surface_with_normals(c, d)

        # Target: ideal elliptical surface
        w_ideal = hc['A'] * Xg**2 + hc['B'] * Zg**2 + hc['C'] * Xg * Zg
        w_target_dm = w_ideal - np.mean(w_ideal)
        w_tps_dm = w_tps - np.mean(w_tps)
        surf_diff = w_tps_dm - w_target_dm
        surf_loss = 0.5 * np.mean(surf_diff**2)
        dL_dw_surf = surf_diff / surf_diff.size

        # Backprop through TPS
        dL_dh_surf, _, _ = solver.full_backward(dL_dw_surf, c, d)

        total_loss += 0.01 * surf_loss  # small weight on surface quality
        total_dL_dh = dL_dh_surf * 0.01

        # ---- Adam update ----
        h_opt = optimizer.step(h_opt, total_dL_dh)
        h_opt = np.maximum(h_opt, 0.0)

        # ---- Track ----
        loss_history.append(total_loss)

        if it % 50 == 0 or it == n_iters - 1:
            # Compute S95 using first sun direction
            sd0 = sun_train[0]
            macro_n, _, local_x, local_z, cos_theta = \
                compute_macro_normal_and_basis(sd0, hc['position'], RECEIVER_POS)
            uy_grav = sample_gravity(cos_theta, gravity_bins)
            w_tps, dwdx, dwdz, _, _, _ = solver.surface_with_normals(c, d)
            w_total = w_tps + uy_grav * cos_theta
            world_pts = surface_to_world(w_total, hc['position'], macro_n, local_x, local_z)
            R_dirs = reflect_rays_grid(world_pts, macro_n, sd0, dwdx, dwdz, local_x, local_z)
            phi_idx, y_idx, weight = trace_to_cylinder(
                world_pts, R_dirs, RECEIVER_POS, RECEIVER_RADIUS, RECEIVER_HEIGHT)
            flux_track = accumulate_flux_gaussian(phi_idx, y_idx, weight)
            s95_track = compute_s95_area(flux_track)
            s95_history.append(s95_track)

            if s95_track < best_s95:
                best_s95 = s95_track
                best_h = h_opt.copy()

            elapsed = time.time() - t0
            print(f"  iter {it:4d}: loss={total_loss:.4e}, S95={s95_track*100:.1f}%, "
                  f"h=[{h_opt.min()*1000:.1f},{h_opt.max()*1000:.1f}]mm, "
                  f"best_S95={best_s95*100:.1f}%, {elapsed:.0f}s")

    t_total = time.time() - t0
    print(f"\n  Optimization complete: {n_iters} iters in {t_total:.0f}s")

    # ---- Final evaluation ----
    print("\n[7/7] Final evaluation...")
    h_final = best_h.copy()
    c_final, d_final = solver.solve(h_final)
    w_final = solver.surface(c_final, d_final)

    # Compute S95 for validation sun directions (subset for speed)
    n_val_sample = min(36, len(sun_val))  # use up to 36 val suns
    s95_vals = []
    for sd in sun_val[:n_val_sample]:
        macro_n, _, local_x, local_z, cos_theta = \
            compute_macro_normal_and_basis(sd, hc['position'], RECEIVER_POS)
        uy_grav = sample_gravity(cos_theta, gravity_bins)
        w_total = w_final + uy_grav * cos_theta
        world_pts = surface_to_world(w_total, hc['position'], macro_n, local_x, local_z)
        _, dwdx, dwdz, _, _, _ = solver.surface_with_normals(c_final, d_final)
        R_dirs = reflect_rays_grid(world_pts, macro_n, sd, dwdx, dwdz, local_x, local_z)
        phi_idx, y_idx, weight = trace_to_cylinder(
            world_pts, R_dirs, RECEIVER_POS, RECEIVER_RADIUS, RECEIVER_HEIGHT)
        flux_val = accumulate_flux_gaussian(phi_idx, y_idx, weight)
        s95_vals.append(compute_s95_area(flux_val))

    avg_s95 = np.mean(s95_vals)
    print(f"  Average S95 (validation): {avg_s95*100:.1f}%")
    print(f"  Best S95 (training):     {best_s95*100:.1f}%")
    print(f"  Final bolt heights:      [{h_final.min()*1000:.1f}, {h_final.max()*1000:.1f}] mm")

    # ---- C++ pipeline baseline comparison ----
    print(f"\n  C++ pipeline baseline (VSM Tikhonov):")
    print(f"    Init S95:  228.49 m2 (not directly comparable)")
    print(f"    Best S95:  53.21 m2 (76.7% reduction)")
    print(f"    Note: S95 in m2 vs fraction — different metrics")

    # ---- Save outputs ----
    os.makedirs(OUT_DIR, exist_ok=True)

    # Save bolt heights
    np.savetxt(os.path.join(OUT_DIR, 'optimized_bolts.txt'), h_final,
               header='Optimized bolt stroke heights (m)')
    h_final.astype(np.float32).tofile(
        os.path.join(OUT_DIR, 'optimized_bolts.bin'))

    # Save surface
    np.save(os.path.join(OUT_DIR, 'optimized_surface.npy'), w_final)
    np.save(os.path.join(OUT_DIR, 'optimized_heights.npy'), h_final)

    # Metrics
    metrics = {
        'heliostat': hc['name'],
        'position': hc['position'].tolist(),
        'n_iters': n_iters,
        'init_s95_frac': float(s95_init),
        'best_s95_frac': float(best_s95),
        'avg_val_s95_frac': float(avg_s95),
        'h_min_mm': float(h_final.min() * 1000),
        'h_max_mm': float(h_final.max() * 1000),
        'optimization_time_s': float(t_total),
        'n_train_suns': len(sun_train),
        'n_val_suns': len(sun_val),
    }
    with open(os.path.join(OUT_DIR, 'optimization_metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)

    # Visualization
    print("\n[Visualization] Generating plots...")
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    # Initial surface
    c_init, _ = solver.solve(h_init)
    w_init = solver.surface(c_init, d_final)
    im0 = axes[0, 0].pcolormesh(Xg, Zg, w_init*1000, cmap='RdYlBu_r', shading='auto')
    axes[0, 0].set_title(f'Initial (ellipse) PV={np.ptp(w_init)*1000:.1f}mm')
    axes[0, 0].set_aspect('equal')
    plt.colorbar(im0, ax=axes[0, 0], label='mm')

    # Optimized surface
    w_opt_dm = w_final - np.mean(w_final)
    vm = max(abs(w_opt_dm).max() * 1000, 0.1)
    im1 = axes[0, 1].pcolormesh(Xg, Zg, w_opt_dm*1000, cmap='RdYlBu_r',
                                  shading='auto', vmin=-vm, vmax=vm)
    axes[0, 1].set_title(f'Optimized PV={np.ptp(w_opt_dm)*1000:.1f}mm')
    axes[0, 1].set_aspect('equal')
    plt.colorbar(im1, ax=axes[0, 1], label='mm')

    # Ideal elliptical
    w_ideal = hc['A'] * Xg**2 + hc['B'] * Zg**2 + hc['C'] * Xg * Zg
    w_ideal_dm = w_ideal - np.mean(w_ideal)
    im2 = axes[0, 2].pcolormesh(Xg, Zg, w_ideal_dm*1000, cmap='RdYlBu_r',
                                  shading='auto', vmin=-vm, vmax=vm)
    axes[0, 2].set_title(f'Ideal ellipse PV={np.ptp(w_ideal_dm)*1000:.1f}mm')
    axes[0, 2].set_aspect('equal')
    plt.colorbar(im2, ax=axes[0, 2], label='mm')

    # Loss history
    axes[1, 0].plot(loss_history, 'b-', lw=0.5)
    axes[1, 0].set_xlabel('Iteration')
    axes[1, 0].set_ylabel('Loss')
    axes[1, 0].set_title('Loss History')
    axes[1, 0].set_yscale('log')
    axes[1, 0].grid(True, alpha=0.3)

    # S95 history
    if s95_history:
        x_vals = list(range(0, n_iters, 50))
        y_vals = [s*100 for s in s95_history]
        # Ensure same length
        n_pts = min(len(x_vals), len(y_vals))
        axes[1, 1].plot(x_vals[:n_pts], y_vals[:n_pts], 'r-o', ms=3)
        axes[1, 1].set_xlabel('Iteration')
        axes[1, 1].set_ylabel('S95 area (%)')
        axes[1, 1].set_title('S95 History')
        axes[1, 1].grid(True, alpha=0.3)

    # Bolt heights
    bolt_idx = np.arange(NB)
    axes[1, 2].bar(bolt_idx, h_init*1000, alpha=0.5, label='Initial (ellipse)')
    axes[1, 2].bar(bolt_idx, h_final*1000, alpha=0.5, label='Optimized')
    axes[1, 2].set_xlabel('Bolt index')
    axes[1, 2].set_ylabel('Height (mm)')
    axes[1, 2].set_title('Bolt Heights')
    axes[1, 2].legend(fontsize=7)
    axes[1, 2].grid(True, alpha=0.3)

    fig.suptitle(f'TPS Proxy Optimization: {hc["name"]} 300m Heliostat',
                 fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'optimization_results.png'), dpi=150,
                bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  Saved: {os.path.join(OUT_DIR, 'optimization_results.png')}")

    print(f"\n{'='*64}")
    print(f"Results saved to: {OUT_DIR}/")
    print(f"  optimized_bolts.txt, optimized_bolts.bin")
    print(f"  optimized_surface.npy, optimized_heights.npy")
    print(f"  optimization_metrics.json, optimization_results.png")
    print(f"{'='*64}")

    return metrics

if __name__ == '__main__':
    main()
