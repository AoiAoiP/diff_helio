#!/usr/bin/env python3
"""
Unified proxy model data generation for the bezier_opt GPU pipeline.

Generates TPS bolt influence functions and/or gravity deformation bins.
Replaces generate_tps_influence.py + prepare_data.py + ansys_gravity.py +
precompute_gravity_bins.py with a single subcommand-based interface.

Subcommands:
  tps            TPS influence functions only
  gravity        Gravity bins from existing ANSYS CSVs
  gravity-ansys  Gravity bins via ANSYS MAPDL batch simulation
  all            tps + gravity (from existing CSVs)
  all-ansys      tps + gravity (via ANSYS MAPDL)

Output (default: data_proxy/):
  influence_phi.bin / _phi_u.bin / _phi_v.bin   (NB × GS² float32)
  influence_kxx.bin / _kzz.bin / _kxz.bin
  gravity_{angle}deg.bin                        (GS² float32, 20 files)
  gravity_y.bin, gravity_angles.json
  ansys_csv/                                     (intermediate CSVs, ANSYS only)

Usage:
  python scripts/generate_proxy_model.py tps --output-dir data_proxy
  python scripts/generate_proxy_model.py all-ansys --output-dir data_proxy
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

# ── Plate geometry (fixed physical dimensions) ──
W, L = 12.84, 9.45  # plate width, length (m)

# ── Default 20-bin gravity angles (matching shaders/bolt_common.slang kGravityAngles) ──
DEFAULT_ANGLES_20BIN = [10, 14, 18, 22, 26, 30, 34, 38, 42, 46,
                         50, 54, 58, 62, 66, 70, 73, 76, 78, 80]

# ── ANSYS executable ──
ANSYS_EXE = "L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe"


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: TPS influence function generation
# (inlined from scripts/generate_tps_influence.py)
# ══════════════════════════════════════════════════════════════════════════════

def _import_tps_solver():
    """Lazy-import TPSSolver with correct sys.path setup."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'proxy'))
    sys.path.insert(0, str(ROOT / 'proxy' / 'tps_pipeline'))
    from tps_solver import TPSSolver
    return TPSSolver


def compute_bolt_positions(bolts_x=7, bolts_z=5, margin=0.08):
    """Compute bolt (x,z) positions in plate-local coordinates (row-major: z outer, x inner)."""
    bu = np.linspace(margin, 1.0 - margin, bolts_x)
    bv = np.linspace(margin, 1.0 - margin, bolts_z)
    bx = np.array([(u - 0.5) * W for v in bv for u in bu])
    bz = np.array([(v - 0.5) * L for v in bv for u in bu])
    return bx, bz


def compute_grid(grid_size=32):
    """Compute evaluation grid in plate-local coordinates. Returns (x_grid, z_grid, Xg, Zg).

    Uses pixel-centered coordinates matching shader's gridToPlate():
      u = (gridU + 0.5) / kGridSize
      x = (u - 0.5) * W
    This ensures influence/gravity values map to the same physical positions
    as the shader's sampling points (bolt_common.slang:58)."""
    u = (np.arange(grid_size) + 0.5) / grid_size
    x_grid = (u - 0.5) * W
    z_grid = (u - 0.5) * L
    Xg, Zg = np.meshgrid(x_grid, z_grid)  # default 'xy' = X-fast
    return x_grid, z_grid, Xg, Zg


def generate_influence_data(output_dir='data_proxy', reg=1e-6, grid_size=32,
                            bolts_x=7, bolts_z=5, margin=0.08):
    """Generate TPS influence function .bin files. Returns partition-of-unity PV."""
    TPSSolver = _import_tps_solver()
    os.makedirs(output_dir, exist_ok=True)

    GS = grid_size
    NB = bolts_x * bolts_z
    _, _, Xg, Zg = compute_grid(GS)
    BX, BZ = compute_bolt_positions(bolts_x, bolts_z, margin)

    print(f"Generating TPS influence functions...")
    print(f"  Plate: {W:.2f} x {L:.2f} m, Grid: {GS}x{GS}, Bolts: {NB} ({bolts_x}x{bolts_z})")
    print(f"  Bolt margin: {margin}, TPS regularization: {reg}")

    solver = TPSSolver(bolt_x=BX, bolt_z=BZ, reg=reg)

    n_grid = GS * GS
    X_flat = Xg.ravel()
    Z_flat = Zg.ravel()

    # Nearest grid point for each bolt (self-influence correction)
    bolt_grid_idx = np.zeros(NB, dtype=int)
    for j in range(NB):
        dist2 = (X_flat - BX[j])**2 + (Z_flat - BZ[j])**2
        bolt_grid_idx[j] = np.argmin(dist2)

    # Precompute TPS kernel matrices
    print("  Precomputing TPS kernel matrices...")
    phi_kernel = np.zeros((NB, n_grid), dtype=np.float64)
    phi_u_kernel = np.zeros((NB, n_grid), dtype=np.float64)
    phi_v_kernel = np.zeros((NB, n_grid), dtype=np.float64)
    kxx_kernel = np.zeros((NB, n_grid), dtype=np.float64)
    kzz_kernel = np.zeros((NB, n_grid), dtype=np.float64)
    kxz_kernel = np.zeros((NB, n_grid), dtype=np.float64)

    for j in range(NB):
        dx = X_flat - BX[j]
        dz = Z_flat - BZ[j]
        r2 = dx*dx + dz*dz + 1e-30
        r = np.sqrt(r2)
        log_r2 = np.log(r2)

        # TPS kernel: φ(r) = r²·log(r²)
        phi_kernel[j] = r2 * log_r2

        # dφ/dr = 2r·log(r²) + 2r
        dphi_dr = 2.0 * r * log_r2 + 2.0 * r

        phi_u_kernel[j] = dphi_dr * (dx / r) * W
        phi_v_kernel[j] = dphi_dr * (dz / r) * L

        kxx_kernel[j] = (2.0*log_r2 + 2.0 + 4.0*dx*dx/r2) * W*W
        kzz_kernel[j] = (2.0*log_r2 + 2.0 + 4.0*dz*dz/r2) * L*L
        kxz_kernel[j] = (4.0*dx*dz/r2) * W*L

        if (j + 1) % 7 == 0:
            print(f"    Bolt {j+1}/{NB} kernels done")

    # Self-influence regularization fix
    for j in range(NB):
        phi_kernel[j, bolt_grid_idx[j]] += reg

    # Per-bolt influence computation
    print("  Computing per-bolt influence (one-hot unit displacement)...")
    inf_phi = np.zeros((NB, n_grid), dtype=np.float32)
    inf_phi_u = np.zeros((NB, n_grid), dtype=np.float32)
    inf_phi_v = np.zeros((NB, n_grid), dtype=np.float32)
    inf_kxx = np.zeros((NB, n_grid), dtype=np.float32)
    inf_kzz = np.zeros((NB, n_grid), dtype=np.float32)
    inf_kxz = np.zeros((NB, n_grid), dtype=np.float32)

    for b in range(NB):
        h = np.zeros(NB)
        h[b] = 1.0
        c, d = solver.solve(h)

        inf_phi[b] = (c @ phi_kernel + d[0] + d[1]*X_flat + d[2]*Z_flat).astype(np.float32)
        inf_phi_u[b] = (c @ phi_u_kernel + d[1]*W).astype(np.float32)
        inf_phi_v[b] = (c @ phi_v_kernel + d[2]*L).astype(np.float32)
        inf_kxx[b] = (c @ kxx_kernel).astype(np.float32)
        inf_kzz[b] = (c @ kzz_kernel).astype(np.float32)
        inf_kxz[b] = (c @ kxz_kernel).astype(np.float32)

    # Save binary files
    files = [
        ('influence_phi.bin', inf_phi),
        ('influence_phi_u.bin', inf_phi_u),
        ('influence_phi_v.bin', inf_phi_v),
        ('influence_kxx.bin', inf_kxx),
        ('influence_kzz.bin', inf_kzz),
        ('influence_kxz.bin', inf_kxz),
    ]
    for name, data in files:
        path = os.path.join(output_dir, name)
        data.ravel().tofile(path)
        size_kb = os.path.getsize(path) / 1024
        print(f"  Saved: {name} ({size_kb:.1f} KB)")

    # Quality checks
    print(f"\n  Quality checks:")
    print(f"    phi range: [{inf_phi.min():.4f}, {inf_phi.max():.4f}]")

    si_vals = np.array([inf_phi[b, bolt_grid_idx[b]] for b in range(NB)])
    n_good = np.sum(si_vals > 0.95)
    print(f"    Self-influence: mean={si_vals.mean():.4f}, "
          f"range=[{si_vals.min():.4f}, {si_vals.max():.4f}], "
          f"good(>0.95)={n_good}/{NB}"
          + ("  PASS" if n_good == NB else "  FAIL"))

    unity = inf_phi.sum(axis=0).reshape(GS, GS)
    pu_pv = unity.max() - unity.min()
    print(f"    Partition of unity PV: {pu_pv:.6f} (ideal: 0)")

    return pu_pv


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Gravity bins from CSV
# (inlined from scripts/train_residual/precompute_gravity_bins.py)
# ══════════════════════════════════════════════════════════════════════════════

def precompute_gravity_bins(source_dir, output_dir, grid_size=32, angles=None,
                            deriv_output=True, deriv_smooth=True):
    """Convert ANSYS CSV node dumps to gravity_{angle}deg.bin + gravity_angles.json.

    When deriv_output=True (default), each .bin file contains 3 planes:
      [w (GS*GS)] [dw/du (GS*GS)] [dw/dv (GS*GS)]
    for a total of 3 * GS * GS float32 values. dw/du and dw/dv are computed
    via central differences (with optional sigma=1px Gaussian pre-smoothing)
    to give the physical slope in m/m at each grid point.

    When deriv_output=False, legacy single-plane [w] format is written.
    """
    from scipy.interpolate import griddata as gd
    try:
        from scipy.ndimage import gaussian_filter as gauss_filt
        _has_ndimage = True
    except ImportError:
        _has_ndimage = False

    if angles is None:
        angles = DEFAULT_ANGLES_20BIN

    GS = grid_size
    os.makedirs(output_dir, exist_ok=True)

    # Pixel-centered flat-plate evaluation grid, matching shader's gridToPlate()
    u = (np.arange(GS) + 0.5) / GS
    Ug, Vg = np.meshgrid(u, u)
    X_flat = (Ug - 0.5) * W
    Z_flat = (Vg - 0.5) * L

    # Cell spacing for physical derivative computation (m)
    dx = W / GS
    dz = L / GS

    print(f"Gravity bins: {GS}x{GS}  source: {source_dir}  output: {output_dir}")
    if deriv_output:
        print(f"  Derivative output: 3-plane [w, dw/du, dw/dv] (smooth={deriv_smooth})")
    metadata = {"angles": {}, "grid_size": GS, "plate_W_m": W, "plate_L_m": L,
                "format": "w_du_dv_v2" if deriv_output else "w_legacy",
                "planes": 3 if deriv_output else 1,
                "plane_layout": "w, dw/du, dw/dv" if deriv_output else "w"}

    for ang in angles:
        cos_th = np.cos(np.deg2rad(ang))
        ang_key = int(ang) if ang == int(ang) else ang
        csv_path = os.path.join(source_dir, f'node_dump_{ang_key}deg.csv')
        if not os.path.exists(csv_path):
            print(f"  WARN theta={ang}deg: {csv_path} not found -- skipped")
            continue

        fea_raw = np.loadtxt(csv_path, delimiter=',', skiprows=1)
        # 7-col: x,y,z,ux,uy,uz,usum  |  3-col: x,z,uy
        if fea_raw.shape[1] >= 7:
            x_fea = fea_raw[:, 0]
            z_fea_tilt = fea_raw[:, 2]
            uy_fea = fea_raw[:, 4]
            uz_fea = fea_raw[:, 5]
            # Plate-normal displacement: w = uy·cosθ + uz·sinθ
            # (matches GUI convention: plate normal = (0, cosθ, +sinθ))
            sin_th = np.sin(np.deg2rad(ang))
            w_fea = uy_fea * cos_th + uz_fea * sin_th
        else:
            x_fea, z_fea_tilt, uy_fea = fea_raw[:, 0], fea_raw[:, 1], fea_raw[:, 2]
            # 3-col CSV (legacy): no uz available.
            # For pure gravity bending on a thin plate, displacement ≈ w·n̂,
            # so uy ≈ w·cosθ → w ≈ uy / cosθ.
            # This is approximate; prefer 7-col CSVs for accuracy.
            if ang != 0:
                w_fea = uy_fea / max(cos_th, 1e-6)
            else:
                w_fea = uy_fea  # cos(0)=1, no correction needed

        # Un-compress tilted Z back to flat-plate length
        z_fea_flat = z_fea_tilt if ang == 0 else z_fea_tilt / cos_th

        in_plate = (np.abs(x_fea) <= W / 2 + 0.02) & (np.abs(z_fea_flat) <= L / 2 + 0.02)
        grid = gd((x_fea[in_plate], z_fea_flat[in_plate]), w_fea[in_plate],
                  (X_flat.ravel(), Z_flat.ravel()), method='linear').reshape(GS, GS)

        nan_mask = np.isnan(grid)
        n_nan = int(nan_mask.sum())
        if n_nan:
            near = gd((x_fea[in_plate], z_fea_flat[in_plate]), uy_fea[in_plate],
                      (X_flat.ravel(), Z_flat.ravel()), method='nearest').reshape(GS, GS)
            grid[nan_mask] = near[nan_mask]

        ang_key = int(ang) if ang == int(ang) else ang
        out_path = os.path.join(output_dir, f'gravity_{ang_key}deg.bin')

        if deriv_output:
            # Compute physical slope derivatives (m/m) via central differences
            grid_w = grid  # (GS, GS), axis0=v(z), axis1=u(x)

            if deriv_smooth and _has_ndimage:
                grid_w = gauss_filt(grid_w, sigma=1.0)

            # dw/du = dw/dx (physical), dw/dv = dw/dz (physical)
            dw_du, dw_dv_native = np.gradient(grid_w, axis=(1, 0))
            dw_du /= dx   # m/m in x-direction
            dw_dv = dw_dv_native / dz  # m/m in z-direction

            # Write 3-plane binary: [w | dw/du | dw/dv]
            packed = np.concatenate([
                grid.ravel(),
                dw_du.ravel(),
                dw_dv.ravel(),
            ]).astype(np.float32)
            packed.tofile(out_path)

            slope_rms = float(np.sqrt(np.mean(dw_du**2 + dw_dv**2)))
            metadata["angles"][str(ang_key)] = {
                "cos_theta": float(cos_th),
                "pv_mm": float(np.ptp(grid) * 1000),
                "min_mm": float(grid.min() * 1000),
                "max_mm": float(grid.max() * 1000),
                "slope_rms_mrad": slope_rms * 1000,
                "nan_filled": n_nan,
                "source": f"{source_dir}/node_dump_{ang_key}deg.csv",
            }
            print(f"  theta={ang}deg: PV={np.ptp(grid)*1000:.1f}mm  "
                  f"slopeRMS={slope_rms*1000:.2f}mrad  "
                  f"NaN={n_nan}  ->  gravity_{ang_key}deg.bin (3-plane)")
        else:
            # Legacy single-plane output
            grid.astype(np.float32).ravel().tofile(out_path)

            metadata["angles"][str(ang_key)] = {
                "cos_theta": float(cos_th),
                "pv_mm": float(np.ptp(grid) * 1000),
                "min_mm": float(grid.min() * 1000),
                "max_mm": float(grid.max() * 1000),
                "nan_filled": n_nan,
                "source": f"{source_dir}/node_dump_{ang_key}deg.csv",
            }
            print(f"  theta={ang}deg: PV={np.ptp(grid)*1000:.1f}mm  "
                  f"range=[{grid.min()*1000:.1f},{grid.max()*1000:.1f}]mm  "
                  f"NaN={n_nan}  ->  gravity_{ang_key}deg.bin")

    # Save metadata
    meta_path = os.path.join(output_dir, 'gravity_angles.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"\nMetadata: {meta_path}")

    # Backward-compat: gravity_y.bin = copy of first gravity bin
    first_angle = angles[0]
    first_key = int(first_angle) if first_angle == int(first_angle) else first_angle
    first_bin = os.path.join(output_dir, f'gravity_{first_key}deg.bin')
    grav_y_bin = os.path.join(output_dir, 'gravity_y.bin')
    if os.path.exists(first_bin):
        shutil.copy(first_bin, grav_y_bin)
        print(f"  Copied gravity_y.bin from gravity_{first_key}deg.bin")

    print("Done.")


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: ANSYS MAPDL batch gravity simulation
# (inlined from scripts/ansys_gravity.py)
# ══════════════════════════════════════════════════════════════════════════════

def load_bolt_layout(path):
    """Load bolt layout configuration from JSON."""
    with open(path) as f:
        cfg = json.load(f)
    required = ["bolts_x", "bolts_z", "margin", "plate_width_m", "plate_length_m",
                "plate_thickness_m"]
    for k in required:
        if k not in cfg:
            raise ValueError(f"Bolt layout config missing key: {k}")
    return cfg


def bolt_positions_from_layout(layout):
    """Compute bolt (x,z) positions from layout config (row-major: z outer, x inner)."""
    nx, nz = layout["bolts_x"], layout["bolts_z"]
    m = layout["margin"]
    pW, pL = layout["plate_width_m"], layout["plate_length_m"]
    positions = []
    for j in range(nz):
        v = m + (1.0 - 2.0 * m) * j / (nz - 1)
        for i in range(nx):
            u = m + (1.0 - 2.0 * m) * i / (nx - 1)
            x = (u - 0.5) * pW
            z = (v - 0.5) * pL
            positions.append((x, z))
    return positions


def generate_gravity_apdl(layout, angle_deg, bolt_xy, work_dir):
    """Generate ANSYS APDL input for zero-bolt gravity simulation at angle_deg.

    Returns (dat_path, node_csv_path).
    """
    pW = layout["plate_width_m"]
    pL = layout["plate_length_m"]
    t = layout["plate_thickness_m"]
    E = layout.get("youngs_modulus_pa", 7.0e10)
    nu = layout.get("poisson_ratio", 0.22)
    rho = layout.get("density_kg_m3", 2500)

    theta = np.radians(angle_deg)
    sin_t = np.sin(theta)
    cos_t = np.cos(theta)

    hw, hl = pW / 2.0, pL / 2.0
    corners_global = [
        (-hw,  hl * sin_t,  hl * cos_t),
        ( hw,  hl * sin_t,  hl * cos_t),
        ( hw, -hl * sin_t, -hl * cos_t),
        (-hw, -hl * sin_t, -hl * cos_t),
    ]

    dat_path = os.path.join(work_dir, f"gravity_{angle_deg}deg.dat")
    node_csv = os.path.join(work_dir, f"node_dump_{angle_deg}deg.csv")

    ndiv_x = layout.get("mesh_ndiv_x", 64)
    ndiv_z = layout.get("mesh_ndiv_z", 48)

    lines = []
    lines.append(f"! Zero-bolt gravity: tilt={angle_deg}deg")
    lines.append(f"! Auto-generated by scripts/generate_proxy_model.py")
    lines.append("")
    lines.append("/NOPR")
    lines.append("")
    lines.append(f"! ── Parameters ──")
    lines.append(f"W = {pW}")
    lines.append(f"L = {pL}")
    lines.append(f"thick = {t}")
    lines.append(f"E_mod = {E}")
    lines.append(f"nu = {nu}")
    lines.append(f"rho = {rho}")
    lines.append(f"ang = {angle_deg}")
    lines.append(f"nbolts = {len(bolt_xy)}")
    lines.append("")
    lines.append("/PREP7")
    lines.append("")
    lines.append("! ── Material & Element ──")
    lines.append("MP,EX,1,E_mod")
    lines.append("MP,NUXY,1,nu")
    lines.append("MP,DENS,1,rho")
    lines.append("ET,1,SHELL181          ! 4-node structural shell")
    lines.append("KEYOPT,1,3,2           ! incompatible modes (match Workbench GUI)")
    lines.append("R,1,thick")
    lines.append("")
    lines.append("! ── Geometry: clean 4-sided area (no hardpoints) ──")
    lines.append(f"K,1,{corners_global[0][0]:.6f},{corners_global[0][1]:.6f},{corners_global[0][2]:.6f}")
    lines.append(f"K,2,{corners_global[1][0]:.6f},{corners_global[1][1]:.6f},{corners_global[1][2]:.6f}")
    lines.append(f"K,3,{corners_global[2][0]:.6f},{corners_global[2][1]:.6f},{corners_global[2][2]:.6f}")
    lines.append(f"K,4,{corners_global[3][0]:.6f},{corners_global[3][1]:.6f},{corners_global[3][2]:.6f}")
    lines.append("A,1,2,3,4")
    lines.append("")
    lines.append(f"! ── Mesh: mapped quad mesh {ndiv_x}x{ndiv_z} ──")
    lines.append("MSHAPE,0,2D             ! quad elements")
    lines.append("MSHKEY,1                ! mapped mesh")
    lines.append(f"LESIZE,1,,,{ndiv_x}           ! L1 (K1-K2): X-parallel, {ndiv_x} divs")
    lines.append(f"LESIZE,2,,,{ndiv_z}           ! L2 (K2-K3): Z-parallel, {ndiv_z} divs")
    lines.append(f"LESIZE,3,,,{ndiv_x}           ! L3 (K3-K4): X-parallel, {ndiv_x} divs")
    lines.append(f"LESIZE,4,,,{ndiv_z}           ! L4 (K4-K1): Z-parallel, {ndiv_z} divs")
    lines.append("AMESH,ALL")
    lines.append("")
    lines.append("! ── BC: NSEL near each bolt, then D (translation only, match GUI) ──")
    lines.append("HALF_WIN=0.3")
    for i, (bx, bz_local) in enumerate(bolt_xy):
        gx = bx
        gz = bz_local * cos_t
        lines.append(f"NSEL,S,LOC,X,{gx:.6f}-HALF_WIN,{gx:.6f}+HALF_WIN")
        lines.append(f"NSEL,R,LOC,Z,{gz:.6f}-HALF_WIN,{gz:.6f}+HALF_WIN")
        lines.append("D,ALL,UX,0.0              ! fix translation only (match GUI)")
        lines.append("D,ALL,UY,0.0")
        lines.append("D,ALL,UZ,0.0")
        lines.append("ALLSEL,ALL")
    lines.append("")
    lines.append("! ── Solution ──")
    lines.append("/SOLU")
    lines.append("ANTYPE,STATIC")
    lines.append("NLGEOM,ON")
    lines.append("AUTOTS,ON              ! auto time stepping (match GUI)")
    lines.append("NSUBST,1,10,1           ! match GUI")
    lines.append("PRED,ON                ! predictor (match GUI)")
    lines.append("OUTRES,ALL,ALL")
    lines.append("PIVCHECK,0             ! disable pivot checking")
    lines.append("")
    lines.append("! Gravity: always vertical (global +Y direction)")
    lines.append("ACEL,0,9.81,0")
    lines.append("SOLVE")
    lines.append("FINISH")
    lines.append("")
    lines.append("! ── Post: 7-col CSV ──")
    lines.append("/POST1")
    lines.append("SET,LAST")
    lines.append("ALLSEL,ALL")
    lines.append("")
    lines.append("*GET,N_NODES,NODE,0,COUNT")
    lines.append("*GET,N_MIN,NODE,0,NUM,MIN")
    lines.append("")
    lines.append("*CFOPEN,'" + node_csv.replace('\\', '/') + "',,,")
    lines.append("*VWRITE,'x','y','z','ux','uy','uz','usum'")
    lines.append("%C,%C,%C,%C,%C,%C,%C")
    lines.append("")
    lines.append("nd = N_MIN")
    lines.append("*DO,idx,1,N_NODES,1")
    lines.append("  *GET,ux_val,NODE,nd,U,X")
    lines.append("  *GET,uy_val,NODE,nd,U,Y")
    lines.append("  *GET,uz_val,NODE,nd,U,Z")
    lines.append("  *GET,usum_val,NODE,nd,U,SUM")
    lines.append("  *VWRITE,NX(nd),NY(nd),NZ(nd),ux_val,uy_val,uz_val,usum_val")
    lines.append("  %12.6F,%12.6F,%12.6F,%14.9F,%14.9F,%14.9F,%14.9F")
    lines.append("  nd = NDNEXT(nd)")
    lines.append("*ENDDO")
    lines.append("*CFCLOSE")
    lines.append("")
    lines.append("FINISH")
    lines.append("/EXIT,NOSAVE")

    with open(dat_path, 'w') as f:
        f.write('\n'.join(lines))

    return dat_path, node_csv


def run_ansys(dat_path, work_dir, ansys_exe=ANSYS_EXE, timeout_s=600):
    """Run ANSYS MAPDL in batch mode. Returns True on success."""
    jobname = os.path.splitext(os.path.basename(dat_path))[0]
    cmd = [
        ansys_exe,
        "-b", "-np", "4",
        "-dir", work_dir,
        "-j", jobname,
        "-i", dat_path,
        "-o", os.path.join(work_dir, f"{jobname}.out"),
    ]
    print(f"  ANSYS: {' '.join(cmd[:2])} -j {jobname} ...")
    try:
        subprocess.run(cmd, cwd=work_dir, timeout=timeout_s,
                       capture_output=True, text=True)
        return True
    except subprocess.TimeoutExpired:
        print(f"  ERROR: ANSYS timed out after {timeout_s}s", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"  ERROR: ANSYS not found at {ansys_exe}", file=sys.stderr)
        return False


def run_ansys_gravity_bins(layout_path, output_dir, grid_size=32, angles=None,
                           ansys_exe=ANSYS_EXE, keep_temp=False, dry_run=False):
    """Generate gravity bins via ANSYS MAPDL batch simulation.

    1. For each angle: generate APDL, run ANSYS, extract CSV
    2. Convert all CSVs to .bin files via precompute_gravity_bins()
    """
    if angles is None:
        angles = DEFAULT_ANGLES_20BIN

    layout_path = str(ROOT / layout_path) if not os.path.isabs(layout_path) else layout_path
    if not os.path.exists(layout_path):
        print(f"ERROR: Bolt layout not found: {layout_path}", file=sys.stderr)
        sys.exit(1)

    layout = load_bolt_layout(layout_path)
    pW = layout["plate_width_m"]
    pL = layout["plate_length_m"]
    GS = grid_size
    positions = bolt_positions_from_layout(layout)
    n_bolts = len(positions)

    print(f"=== ANSYS Gravity Bin Generator ===")
    print(f"  Layout:   {layout.get('description', layout_path)}")
    print(f"  Bolts:    {layout['bolts_x']}x{layout['bolts_z']} = {n_bolts}, margin={layout['margin']}")
    print(f"  Plate:    {pW}x{pL}m, t={layout['plate_thickness_m']*1000}mm")
    print(f"  Grid:     {GS}x{GS}")
    print(f"  Angles:   {len(angles)} bins, {angles[0]}°–{angles[-1]}°")
    print(f"  ANSYS:    {ansys_exe}")
    print(f"  Output:   {output_dir}/")

    out_dir = str(ROOT / output_dir) if not os.path.isabs(output_dir) else output_dir
    os.makedirs(out_dir, exist_ok=True)

    csv_dir = os.path.join(out_dir, "ansys_csv")
    os.makedirs(csv_dir, exist_ok=True)

    failed = []
    for ang in angles:
        print(f"\n  [{ang:.0f}deg] ", end="", flush=True)

        work_dir = tempfile.mkdtemp(prefix=f"ansys_grav_{int(ang)}deg_",
                                    dir=str(ROOT / "build"))
        try:
            dat_path, expected_csv = generate_gravity_apdl(layout, ang, positions, work_dir)

            if dry_run:
                print(f"APDL: {dat_path} (dry-run, skip ANSYS)")
                continue

            t0 = time.time()
            ok = run_ansys(dat_path, work_dir, ansys_exe)
            if not ok:
                failed.append(ang)
                continue

            if not os.path.exists(expected_csv):
                print(f"MISSING CSV: {expected_csv}", flush=True)
                failed.append(ang)
                continue

            dest_csv = os.path.join(csv_dir, f"node_dump_{int(ang)}deg.csv")
            shutil.copy(expected_csv, dest_csv)

            elapsed = time.time() - t0
            data = np.loadtxt(dest_csv, delimiter=',', skiprows=1)
            n_nodes = data.shape[0]
            uy_pv = (data[:, 4].max() - data[:, 4].min()) * 1000
            print(f"UY_PV={uy_pv:.1f}mm, nodes={n_nodes}, {elapsed:.0f}s", flush=True)

        finally:
            if not keep_temp:
                shutil.rmtree(work_dir, ignore_errors=True)

    print(f"\n=== ANSYS done: {len(angles)-len(failed)}/{len(angles)} angles ===")
    if failed:
        print(f"  Failed: {failed}")

    # Convert CSV → gravity bins
    if not dry_run:
        precompute_gravity_bins(csv_dir, out_dir, GS, angles,
                                deriv_output=True, deriv_smooth=True)

    print(f"\n  Output: {out_dir}/")
    print(f"  CSVs:   {csv_dir}/")


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: Validation
# ══════════════════════════════════════════════════════════════════════════════

def validate_output(output_dir, grid_size, bolts_x, bolts_z, gravity_angles):
    """Quick sanity check on generated files."""
    n_bolts = bolts_x * bolts_z
    n_grid = grid_size * grid_size
    errors = []

    for name in ["influence_phi", "influence_phi_u", "influence_phi_v",
                 "influence_kxx", "influence_kzz", "influence_kxz"]:
        path = os.path.join(output_dir, f"{name}.bin")
        if not os.path.exists(path):
            errors.append(f"MISSING: {path}")
            continue
        data = np.fromfile(path, dtype=np.float32)
        expected = n_bolts * n_grid
        if len(data) != expected:
            errors.append(f"SIZE: {path} has {len(data)}, expected {expected}")

    if errors:
        print("\nVALIDATION ERRORS:")
        for e in errors:
            print(f"  {e}")
        return False

    phi = np.fromfile(os.path.join(output_dir, "influence_phi.bin"),
                      dtype=np.float32).reshape(n_bolts, n_grid)
    unit_sum = phi.sum(axis=0)
    pv = unit_sum.max() - unit_sum.min()
    print(f"\n  Validation OK: {n_bolts} influence functions, unit decomp PV={pv:.2e}")

    for ang in gravity_angles:
        path = os.path.join(output_dir, f"gravity_{ang}deg.bin")
        if not os.path.exists(path):
            errors.append(f"MISSING: {path}")

    if errors:
        print("GRAVITY ERRORS:")
        for e in errors:
            print(f"  {e}")
        return False

    meta_path = os.path.join(output_dir, "gravity_angles.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print(f"  Gravity bins: {len(meta.get('angles',{}))} angles, grid={meta.get('grid_size')}")

    print(f"  All checks passed.")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: Main — subcommand dispatch
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_bolt_params(args):
    """Resolve bolts_x, bolts_z, margin from either --bolt-layout JSON or explicit args."""
    if args.bolt_layout:
        layout_path = ROOT / args.bolt_layout if not os.path.isabs(args.bolt_layout) else args.bolt_layout
        if not os.path.exists(layout_path):
            print(f"ERROR: Bolt layout not found: {layout_path}", file=sys.stderr)
            sys.exit(1)
        with open(layout_path) as f:
            lc = json.load(f)
        return lc.get("bolts_x", 7), lc.get("bolts_z", 5), lc.get("margin", 0.08)
    return args.bolts_x, args.bolts_z, args.margin


def cmd_tps(args):
    """Handle 'tps' subcommand."""
    bx, bz, margin = _resolve_bolt_params(args)
    pu = generate_influence_data(args.output_dir, args.reg, args.grid_size, bx, bz, margin)
    if pu < 1e-4:
        print(f"\nSUCCESS: Partition of unity PV = {pu:.2e} (< 1e-4)")
    else:
        print(f"\nWARNING: Partition of unity PV = {pu:.4f} (should be < 1e-4)")


def cmd_gravity(args):
    """Handle 'gravity' subcommand."""
    precompute_gravity_bins(args.source_dir, args.output_dir, args.grid_size, args.angles,
                            deriv_output=getattr(args, 'deriv_output', True),
                            deriv_smooth=getattr(args, 'deriv_smooth', True))


def cmd_gravity_ansys(args):
    """Handle 'gravity-ansys' subcommand."""
    run_ansys_gravity_bins(
        args.bolt_layout, args.output_dir, args.grid_size, args.angles,
        args.ansys_exe, args.keep_temp, args.dry_run)


def cmd_all(args):
    """Handle 'all' subcommand."""
    bx, bz, margin = _resolve_bolt_params(args)
    out = args.output_dir

    # Step 1: TPS influence
    print(f"\n{'='*60}")
    print(f"Step 1/2: TPS Influence Functions")
    print(f"{'='*60}")
    generate_influence_data(out, args.reg, args.grid_size, bx, bz, margin)

    # Step 2: Gravity
    print(f"\n{'='*60}")
    print(f"Step 2/2: Gravity Bins")
    print(f"{'='*60}")

    if args.use_ansys:
        run_ansys_gravity_bins(
            args.bolt_layout, out, args.grid_size, args.gravity_angles,
            args.ansys_exe, args.keep_temp, args.dry_run)
    else:
        precompute_gravity_bins(args.gravity_source, out, args.grid_size, args.gravity_angles,
                                deriv_output=getattr(args, 'deriv_output', True),
                                deriv_smooth=getattr(args, 'deriv_smooth', True))

    # Validate
    print(f"\n{'='*60}")
    print(f"Validation")
    print(f"{'='*60}")
    validate_output(out, args.grid_size, bx, bz, args.gravity_angles)

    print(f"\n=== Data ready in {out} ===")


def main():
    parser = argparse.ArgumentParser(
        description="Unified proxy model data generation for bezier_opt GPU pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', help='Subcommands')

    # ── Shared parent parser ──
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument('--output-dir', default='data_proxy',
                        help='Output directory (default: data_proxy)')
    shared.add_argument('--grid-size', type=int, default=32,
                        help='Render grid resolution (default: 32)')
    shared.add_argument('--bolt-layout', default='configs/bolt_layouts/7x5_default.json',
                        help='Bolt layout JSON config file')
    shared.add_argument('--bolts-x', type=int, default=7,
                        help='Number of bolts in x/width direction (default: 7)')
    shared.add_argument('--bolts-z', type=int, default=5,
                        help='Number of bolts in z/length direction (default: 5)')
    shared.add_argument('--margin', type=float, default=0.08,
                        help='Bolt edge margin fraction (default: 0.08)')

    # ── tps ──
    sp_tps = sub.add_parser('tps', parents=[shared],
                            help='Generate TPS influence functions only')
    sp_tps.add_argument('--reg', type=float, default=1e-6,
                        help='TPS Tikhonov regularization (default: 1e-6)')

    # ── gravity ──
    sp_grav = sub.add_parser('gravity', parents=[shared],
                             help='Generate gravity bins from existing ANSYS CSVs')
    sp_grav.add_argument('--source-dir', default=None,
                         help='Dir with node_dump_{ang}deg.csv (default: <output-dir>/ansys_csv)')
    sp_grav.add_argument('--angles', type=float, nargs='+', default=DEFAULT_ANGLES_20BIN,
                         help='Tilt angles in degrees (default: 20-bin 10-80)')
    sp_grav.add_argument('--deriv-output', type=lambda x: x.lower() in ('1','true','yes'), default=True,
                         help='Output 3-plane [w, dw/du, dw/dv] gravity bins (default: true)')
    sp_grav.add_argument('--deriv-smooth', type=lambda x: x.lower() in ('1','true','yes'), default=True,
                         help='Gaussian sigma=1px pre-smooth before derivative (default: true)')

    # ── gravity-ansys ──
    sp_ga = sub.add_parser('gravity-ansys', parents=[shared],
                           help='Generate gravity bins via ANSYS MAPDL')
    sp_ga.add_argument('--angles', type=float, nargs='+', default=DEFAULT_ANGLES_20BIN,
                       help='Tilt angles in degrees (default: 20-bin 10-80)')
    sp_ga.add_argument('--ansys-exe', default=ANSYS_EXE,
                       help='Path to ANSYS MAPDL executable')
    sp_ga.add_argument('--keep-temp', action='store_true',
                       help='Keep temporary ANSYS working files')
    sp_ga.add_argument('--dry-run', action='store_true',
                       help='Generate APDL files but do not run ANSYS')

    # ── all ──
    sp_all = sub.add_parser('all', parents=[shared],
                            help='Generate TPS influence + gravity bins')
    sp_all.add_argument('--reg', type=float, default=1e-6,
                        help='TPS Tikhonov regularization (default: 1e-6)')
    sp_all.add_argument('--use-ansys', action='store_true',
                        help='Generate gravity bins via ANSYS MAPDL (requires license)')
    sp_all.add_argument('--gravity-source', default=None,
                        help='Dir with node_dump CSVs (non-ANSYS path)')
    sp_all.add_argument('--gravity-angles', type=float, nargs='+', default=DEFAULT_ANGLES_20BIN,
                        help='Gravity tilt angles in degrees (default: 20-bin)')
    sp_all.add_argument('--ansys-exe', default=ANSYS_EXE,
                        help='Path to ANSYS MAPDL executable')
    sp_all.add_argument('--keep-temp', action='store_true',
                        help='Keep temporary ANSYS working files')
    sp_all.add_argument('--dry-run', action='store_true',
                        help='Generate APDL files but do not run ANSYS')
    sp_all.add_argument('--deriv-output', type=lambda x: x.lower() in ('1','true','yes'), default=True,
                        help='Output 3-plane [w, dw/du, dw/dv] gravity bins (default: true)')
    sp_all.add_argument('--deriv-smooth', type=lambda x: x.lower() in ('1','true','yes'), default=True,
                        help='Gaussian sigma=1px pre-smooth before derivative (default: true)')

    # ── all-ansys (convenience alias) ──
    sp_aa = sub.add_parser('all-ansys', parents=[shared],
                           help='Generate TPS influence + gravity (ANSYS path, convenience alias)')
    sp_aa.add_argument('--reg', type=float, default=1e-6)
    sp_aa.add_argument('--gravity-angles', type=float, nargs='+', default=DEFAULT_ANGLES_20BIN)
    sp_aa.add_argument('--ansys-exe', default=ANSYS_EXE)
    sp_aa.add_argument('--keep-temp', action='store_true')
    sp_aa.add_argument('--dry-run', action='store_true')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Ensure output dir is absolute
    if not os.path.isabs(args.output_dir):
        args.output_dir = str(ROOT / args.output_dir)

    # Default gravity source to output_dir/ansys_csv
    if args.command == 'gravity' and args.source_dir is None:
        args.source_dir = os.path.join(args.output_dir, 'ansys_csv')
    if args.command == 'all' and args.gravity_source is None:
        if args.use_ansys:
            args.gravity_source = os.path.join(args.output_dir, 'ansys_csv')
        else:
            args.gravity_source = 'train_data/zero_heights_ON'

    # Dispatch
    if args.command == 'tps':
        cmd_tps(args)
    elif args.command == 'gravity':
        cmd_gravity(args)
    elif args.command == 'gravity-ansys':
        cmd_gravity_ansys(args)
    elif args.command == 'all':
        cmd_all(args)
    elif args.command == 'all-ansys':
        args.use_ansys = True
        args.gravity_source = os.path.join(args.output_dir, 'ansys_csv')
        cmd_all(args)


if __name__ == '__main__':
    main()
