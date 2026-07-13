#!/usr/bin/env python3
"""
Generate TPS-based bolt influence functions for the C++ GPU optimization pipeline.

Replaces the deprecated VSM (Virtual Source Method) influence data. TPS influence
functions are mathematically exact: phi_b(x,z) = surface displacement at (x,z)
when bolt b has unit stroke and all other bolts are at zero.

Key property: Partition of unity — Σ_b phi_b(x,z) = 1 everywhere (exact to ~1e-7).
This guarantees physically correct linear superposition for any bolt configuration.

Output: 6 binary files in C++ pipeline format (float32, bolt-major, row-major):
  influence_phi.bin, influence_phi_u.bin, influence_phi_v.bin,
  influence_kxx.bin, influence_kzz.bin, influence_kxz.bin

Usage:
  python scripts/generate_tps_influence.py [--output data_vsm_mnvn_tik32]
"""

import sys, os, argparse
import numpy as np

# Add project paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proxy'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proxy', 'tps_pipeline'))

from validation_utils import W, L, GS, NB, BX, BZ, X_GRID, Z_GRID, Xg, Zg
from tps_solver import TPSSolver


def generate_influence_data(output_dir='data_vsm_mnvn_tik32', reg=1e-6):
    """Generate TPS influence function .bin files.

    Args:
        output_dir: Directory to write .bin files
        reg: TPS Tikhonov regularization parameter
    """
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating TPS influence functions...")
    print(f"  Plate: {W:.2f} x {L:.2f} m, Grid: {GS}x{GS}, Bolts: {NB}")
    print(f"  TPS regularization: {reg}")

    # Build TPS solver (precomputes A_inv)
    solver = TPSSolver(reg=reg)

    # Flatten grid in row-major (z-first) order
    n_grid = GS * GS
    X_flat = Xg.ravel()
    Z_flat = Zg.ravel()

    # Identify nearest grid point for each bolt (used for regularization fix below)
    bolt_grid_idx = np.zeros(NB, dtype=int)
    for j in range(NB):
        dist2 = (X_flat - BX[j])**2 + (Z_flat - BZ[j])**2
        bolt_grid_idx[j] = np.argmin(dist2)

    # Precompute TPS kernel and derivatives for each bolt at all grid points
    print("  Precomputing TPS kernel matrices...")
    phi_kernel = np.zeros((NB, n_grid), dtype=np.float64)    # φ(r)
    phi_u_kernel = np.zeros((NB, n_grid), dtype=np.float64)  # ∂φ/∂u = ∂φ/∂x · W
    phi_v_kernel = np.zeros((NB, n_grid), dtype=np.float64)  # ∂φ/∂v = ∂φ/∂z · L
    kxx_kernel = np.zeros((NB, n_grid), dtype=np.float64)    # ∂²φ/∂x² · W²
    kzz_kernel = np.zeros((NB, n_grid), dtype=np.float64)    # ∂²φ/∂z² · L²
    kxz_kernel = np.zeros((NB, n_grid), dtype=np.float64)    # ∂²φ/∂x∂z · W·L

    for j in range(NB):
        dx = X_flat - BX[j]
        dz = Z_flat - BZ[j]
        r2 = dx*dx + dz*dz + 1e-30
        r = np.sqrt(r2)

        # TPS kernel: φ(r) = r²·log(r²) = 2·r²·log(r)
        # Must match tps_kernel(r2) in validation_utils.py (uses r²·log(r²)).
        log_r2 = np.log(r2)                     # = 2·log(r)
        phi_kernel[j] = r2 * log_r2             # r²·log(r²)

        # dφ/dr = d/dr[r²·log(r²)] = 2r·log(r²) + 2r
        dphi_dr = 2.0 * r * log_r2 + 2.0 * r

        # First derivatives: ∂φ/∂u = ∂φ/∂x · W
        phi_u_kernel[j] = dphi_dr * (dx / r) * W
        phi_v_kernel[j] = dphi_dr * (dz / r) * L

        # Second derivatives: ∂²φ/∂x² = 2·log(r²) + 2 + 4·(dx/r²)²·r²...
        # Derived: ∂²φ/∂x² = 2·log(r²) + 2 + 4·dx²/r²
        kxx_kernel[j] = (2.0*log_r2 + 2.0 + 4.0*dx*dx/r2) * W*W
        kzz_kernel[j] = (2.0*log_r2 + 2.0 + 4.0*dz*dz/r2) * L*L
        kxz_kernel[j] = (4.0*dx*dz/r2) * W*L  # no log term

        if (j + 1) % 7 == 0:
            print(f"    Bolt {j+1}/{NB} kernels done")

    # FIX: Add regularization to phi_kernel at bolt self-positions.
    # The TPS system matrix uses K[i,i] = φ(0) + λ, but phi_kernel evaluates
    # φ(0) ≈ r²log(r)|_{r=1e-15} ≈ 0. Without this correction, c_i·φ(0) ≈ 0
    # instead of c_i·λ, causing self-influence ≈ 0.53 instead of 1.0.
    for j in range(NB):
        phi_kernel[j, bolt_grid_idx[j]] += reg

    # For each bolt b, compute influence = surface when h[b] = 1, others = 0
    print("  Computing per-bolt influence (one-hot unit displacement)...")
    inf_phi = np.zeros((NB, n_grid), dtype=np.float32)
    inf_phi_u = np.zeros((NB, n_grid), dtype=np.float32)
    inf_phi_v = np.zeros((NB, n_grid), dtype=np.float32)
    inf_kxx = np.zeros((NB, n_grid), dtype=np.float32)
    inf_kzz = np.zeros((NB, n_grid), dtype=np.float32)
    inf_kxz = np.zeros((NB, n_grid), dtype=np.float32)

    for b in range(NB):
        h = np.zeros(NB)
        h[b] = 1.0  # unit displacement at bolt b
        c, d = solver.solve(h)

        # w(x,z) = Σ c_j·φ_j(r) + d₀ + d₁·x + d₂·z
        inf_phi[b] = (c @ phi_kernel + d[0] + d[1]*X_flat + d[2]*Z_flat).astype(np.float32)

        # ∂w/∂u = Σ c_j·∂φ_j/∂u + d₁·W (chain rule: d(d₁·x)/du = d₁·dx/du = d₁·W)
        inf_phi_u[b] = (c @ phi_u_kernel + d[1]*W).astype(np.float32)
        inf_phi_v[b] = (c @ phi_v_kernel + d[2]*L).astype(np.float32)

        # Curvatures: polynomial terms have zero second derivative
        inf_kxx[b] = (c @ kxx_kernel).astype(np.float32)
        inf_kzz[b] = (c @ kzz_kernel).astype(np.float32)
        inf_kxz[b] = (c @ kxz_kernel).astype(np.float32)

    # Save as flat binary files
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

    # Self-influence at bolt positions (nearest grid point)
    si_vals = []
    for b in range(NB):
        idx = bolt_grid_idx[b]
        si_vals.append(inf_phi[b, idx])
    si_vals = np.array(si_vals)
    n_good = np.sum(si_vals > 0.95)
    print(f"    Self-influence: mean={si_vals.mean():.4f}, "
          f"range=[{si_vals.min():.4f}, {si_vals.max():.4f}], "
          f"good(>0.95)={n_good}/{NB}"
          + ("  PASS" if n_good == NB else "  FAIL"))

    # Constraint check: at each bolt's grid point, verify phi_b ≈ 1.0
    constraint_ok = np.all(np.abs(si_vals - 1.0) < 0.05)
    print(f"    Bolt constraint (|phi_b(bolt_b)-1| < 0.05): {'PASS' if constraint_ok else 'FAIL'}")

    # Partition of unity: Σ_b φ_b(x,z) should = 1 everywhere
    unity = inf_phi.sum(axis=0).reshape(GS, GS)
    pu_pv = unity.max() - unity.min()
    print(f"    Partition of unity PV: {pu_pv:.6f} (ideal: 0)")

    return pu_pv


def main():
    parser = argparse.ArgumentParser(
        description='Generate TPS-based bolt influence functions for GPU pipeline')
    parser.add_argument('--output', default='data_vsm_mnvn_tik32',
                        help='Output directory for .bin files')
    parser.add_argument('--reg', type=float, default=1e-6,
                        help='TPS Tikhonov regularization')
    args = parser.parse_args()

    pu = generate_influence_data(args.output, args.reg)

    if pu < 1e-4:
        print(f"\nSUCCESS: Partition of unity PV = {pu:.2e} (< 1e-4)")
        print(f"Influence data ready for C++ pipeline at: {args.output}/")
    else:
        print(f"\nWARNING: Partition of unity PV = {pu:.4f} (should be < 1e-4)")


if __name__ == '__main__':
    main()
