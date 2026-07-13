#!/usr/bin/env python3
"""
TPS Solver: 35 bolt heights → TPS coefficients → surface + analytical normals.

Core math:
  w(x,z) = Σ_j c_j · r_j²log(r_j²) + d₀ + d₁x + d₂z

System: A · [c; d] = [h; 0₃]
  A = [K_{35×35}  P_{35×3}]
      [P^T_{3×35}   0_{3×3} ]

  K_ij = r_ij²·log(r_ij²)  (TPS kernel between bolt i and bolt j)
  P = [1, BX_i, BZ_i]       (polynomial terms)

Gradient backprop (from 薄板样条插值/TPS_taichi.py):
  ∂L/∂h = A_inv · [∂L/∂c; ∂L/∂d]   (first 35 components)
"""

import sys, os
import numpy as np

# Import validation_utils for geometry constants and TPS kernel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validation_utils import W, L, NB, BX, BZ, X_GRID, Z_GRID, Xg, Zg, tps_kernel


def build_system(bolt_x=None, bolt_z=None, reg=1e-8):
    """Build TPS augmented system matrix and precompute its inverse.

    Args:
        bolt_x, bolt_z: bolt positions (plate-local, meters). Defaults to BX, BZ.
        reg: Tikhonov regularization added to K's diagonal.

    Returns:
        A: (N+3, N+3) system matrix
        A_inv: (N+3, N+3) inverse
        bolt_x, bolt_z: bolt positions used
        N: number of bolts
    """
    if bolt_x is None:
        bolt_x = BX
    if bolt_z is None:
        bolt_z = BZ

    N = len(bolt_x)
    dx = bolt_x[:, np.newaxis] - bolt_x[np.newaxis, :]
    dz = bolt_z[:, np.newaxis] - bolt_z[np.newaxis, :]
    r2 = dx * dx + dz * dz

    # TPS kernel matrix K_ij = r_ij² · log(r_ij²)
    K = tps_kernel(r2)
    # Regularize diagonal
    K += reg * np.eye(N)

    # Polynomial matrix P = [1, x_i, z_i]
    P = np.column_stack([np.ones(N), bolt_x, bolt_z])

    # Assemble augmented system
    A = np.zeros((N + 3, N + 3))
    A[:N, :N] = K
    A[:N, N:] = P
    A[N:, :N] = P.T

    A_inv = np.linalg.inv(A)

    return A, A_inv, bolt_x, bolt_z, N


def forward(h, A_inv, N=None):
    """Forward pass: bolt heights → TPS coefficients.

    Solves: A · [c; d] = [h; 0, 0, 0]

    Args:
        h: (N,) bolt heights (m)
        A_inv: (N+3, N+3) precomputed inverse
        N: number of bolts (inferred if None)

    Returns:
        c: (N,) TPS source coefficients
        d: (3,) polynomial coefficients [d0, d1, d2]
    """
    if N is None:
        N = len(h)
    b = np.zeros(N + 3)
    b[:N] = h
    coeffs = A_inv @ b
    return coeffs[:N], coeffs[N:]


def backward(dL_dc, dL_dd, A_inv, N=None):
    """Backward pass: dL/d(c,d) → dL/dh via A_inv.

    Since coeffs = A_inv @ b where b = [h; 0₃]:
      ∂L/∂b = A_inv @ ∂L/∂coeffs
      ∂L/∂h = first N components of ∂L/∂b

    Args:
        dL_dc: (N,) gradient of loss w.r.t. TPS source coefficients
        dL_dd: (3,) gradient of loss w.r.t. polynomial coefficients
        A_inv: (N+3, N+3) precomputed inverse
        N: number of bolts

    Returns:
        dL_dh: (N,) gradient of loss w.r.t. bolt heights
    """
    if N is None:
        N = len(dL_dc)
    dL_dcoeff = np.concatenate([np.asarray(dL_dc), np.asarray(dL_dd)])
    dL_db = A_inv @ dL_dcoeff
    return dL_db[:N]


class TPSSolver:
    """Differentiable TPS solver for heliostat bolt proxy model.

    Precomputes A_inv once for given bolt positions. Supports forward
    (heights → coefficients → surface) and backward (loss gradient →
    height gradient) passes.

    Usage:
        solver = TPSSolver()
        c, d = solver.solve(h)              # forward: h → (c, d)
        w = solver.surface(c, d)            # surface on 25×25 grid
        w, nx, nz = solver.surface_with_normals(c, d)  # + analytical normals
        dL_dh = solver.backward(dL_dc, dL_dd)  # backward: grad → dL/dh
    """

    def __init__(self, bolt_x=None, bolt_z=None, reg=1e-8):
        self.bolt_x = np.asarray(bolt_x if bolt_x is not None else BX, dtype=np.float64)
        self.bolt_z = np.asarray(bolt_z if bolt_z is not None else BZ, dtype=np.float64)
        self.N = len(self.bolt_x)
        self.reg = reg

        # Build and cache system
        self.A, self.A_inv, _, _, _ = build_system(self.bolt_x, self.bolt_z, reg)

        # Precompute condition number for diagnostics
        self.condition = np.linalg.cond(self.A)
        print(f"[TPSSolver] {self.N} bolts, system {self.A.shape}, "
              f"cond={self.condition:.1f}, reg={reg}")

    def solve(self, h):
        """Forward: bolt heights → TPS coefficients."""
        return forward(np.asarray(h, dtype=np.float64), self.A_inv, self.N)

    def surface(self, c, d, grid_x=None, grid_z=None):
        """Evaluate TPS surface w(x,z) on grid.

        Args:
            c: (N,) TPS source coefficients
            d: (3,) polynomial coefficients
            grid_x: (Gx,) x coordinates (default: X_GRID)
            grid_z: (Gz,) z coordinates (default: Z_GRID)

        Returns:
            w: (Gz, Gx) surface heights (m)
        """
        if grid_x is None:
            grid_x = X_GRID
        if grid_z is None:
            grid_z = Z_GRID

        Xg_loc, Zg_loc = np.meshgrid(grid_x, grid_z)
        w = np.full_like(Xg_loc, d[0]) + d[1] * Xg_loc + d[2] * Zg_loc

        for j in range(self.N):
            dx = Xg_loc - self.bolt_x[j]
            dz = Zg_loc - self.bolt_z[j]
            r2 = dx * dx + dz * dz + 1e-30
            r = np.sqrt(r2)
            w += c[j] * r * r * np.log(r)

        return w

    def surface_with_normals(self, c, d, grid_x=None, grid_z=None):
        """Evaluate TPS surface and analytical normals.

        Analytical derivative of TPS kernel:
          ∂φ/∂r = 2r·log(r) + r = r·(2·log(r) + 1)
          ∂φ/∂x = ∂φ/∂r · (x - x_j)/r = (2·log(r) + 1) · 2(x - x_j)
                 Wait: φ = r²·log(r)
                 ∂φ/∂x = 2r·(∂r/∂x)·log(r) + r²·(1/r)·(∂r/∂x)
                        = 2(x-x_j)·log(r) + (x-x_j)
                        = (x-x_j)·(2·log(r) + 1)

          But the standard form from Taichi is:
          drbf_dr = 2·r·log(r) + r
          ∂φ/∂x = drbf_dr · (x-x_j)/r = (2·log(r) + 1) · (x-x_j)

          Let's use the consistent form:
          d(r²log(r))/dx = 2x·log(r) + x = x·(2·log(r) + 1)

        Returns:
            w: (Gz, Gx) surface heights (m)
            dwdx: (Gz, Gx) ∂w/∂x
            dwdz: (Gz, Gx) ∂w/∂z
            nx, ny, nz: (Gz, Gx) normal vector components
        """
        if grid_x is None:
            grid_x = X_GRID
        if grid_z is None:
            grid_z = Z_GRID

        Xg_loc, Zg_loc = np.meshgrid(grid_x, grid_z)

        # Polynomial part
        w = np.full_like(Xg_loc, d[0]) + d[1] * Xg_loc + d[2] * Zg_loc
        dwdx = np.full_like(Xg_loc, d[1])
        dwdz = np.full_like(Zg_loc, d[2])

        # TPS source contributions
        for j in range(self.N):
            dx = Xg_loc - self.bolt_x[j]
            dz = Zg_loc - self.bolt_z[j]
            r2 = dx * dx + dz * dz + 1e-30
            r = np.sqrt(r2)

            # φ = r²·log(r)
            phi = r2 * np.log(r)
            # dφ/dr = 2r·log(r) + r
            dphi_dr = 2.0 * r * np.log(r) + r

            w += c[j] * phi
            dwdx += c[j] * dphi_dr * (dx / r)
            dwdz += c[j] * dphi_dr * (dz / r)

        # Normal vector: n = (-dw/dx, 1, -dw/dz) normalized
        norm = np.sqrt(dwdx * dwdx + 1.0 + dwdz * dwdz)
        nx = -dwdx / norm
        ny = 1.0 / norm
        nz = -dwdz / norm

        return w, dwdx, dwdz, nx, ny, nz

    def surface_deriv_coeff_grad(self, dL_dw, c=None, d=None, grid_x=None, grid_z=None):
        """Project dL/dw back to dL/dc and dL/dd.

        Since w(x,z) = Σ_j c_j·φ(r_j) + d₀ + d₁x + d₂z:
          ∂w/∂c_j = φ(r_j)  →  ∂L/∂c_j = Σ_i ∂L/∂w_i · φ(r_ij)
          ∂w/∂d₀ = 1        →  ∂L/∂d₀ = Σ_i ∂L/∂w_i
          ∂w/∂d₁ = x        →  ∂L/∂d₁ = Σ_i ∂L/∂w_i · x_i
          ∂w/∂d₂ = z        →  ∂L/∂d₂ = Σ_i ∂L/∂w_i · z_i

        Args:
            dL_dw: (Gz, Gx) gradient of loss w.r.t. surface heights
            c, d: (optional, unused) TPS coefficients
            grid_x, grid_z: grid coordinates

        Returns:
            dL_dc: (N,) gradient w.r.t. TPS source coefficients
            dL_dd: (3,) gradient w.r.t. polynomial coefficients
        """
        if grid_x is None:
            grid_x = X_GRID
        if grid_z is None:
            grid_z = Z_GRID

        Xg_loc, Zg_loc = np.meshgrid(grid_x, grid_z)
        dL_dw_flat = np.asarray(dL_dw, dtype=np.float64).ravel()

        # Polynomial gradients
        dL_dd = np.array([
            np.sum(dL_dw_flat),                  # d₀
            np.sum(dL_dw_flat * Xg_loc.ravel()), # d₁
            np.sum(dL_dw_flat * Zg_loc.ravel()), # d₂
        ])

        # TPS source gradients
        dL_dc = np.zeros(self.N)
        for j in range(self.N):
            dx = Xg_loc - self.bolt_x[j]
            dz = Zg_loc - self.bolt_z[j]
            r2 = dx * dx + dz * dz + 1e-30
            r = np.sqrt(r2)
            phi_j = r2 * np.log(r)  # φ(r_j) at all grid points
            dL_dc[j] = np.sum(dL_dw_flat * phi_j.ravel())

        return dL_dc, dL_dd

    def backward(self, dL_dc, dL_dd):
        """Full backward: dL/d(c,d) → dL/dh through A_inv.

        Args:
            dL_dc: (N,) gradient w.r.t. source coefficients
            dL_dd: (3,) gradient w.r.t. polynomial coefficients

        Returns:
            dL_dh: (N,) gradient w.r.t. bolt heights
        """
        return backward(dL_dc, dL_dd, self.A_inv, self.N)

    def full_backward(self, dL_dw, c=None, d=None, grid_x=None, grid_z=None):
        """End-to-end backward: dL/dw → dL/dh.

        Combines surface_deriv_coeff_grad + backward.

        Args:
            dL_dw: (Gz, Gx) gradient of loss w.r.t. surface
            c, d: (optional) TPS coefficients
            grid_x, grid_z: grid coordinates

        Returns:
            dL_dh: (N,) gradient w.r.t. bolt heights
            dL_dc: (N,) intermediate gradient
            dL_dd: (3,) intermediate gradient
        """
        dL_dc, dL_dd = self.surface_deriv_coeff_grad(dL_dw, c, d, grid_x, grid_z)
        dL_dh = self.backward(dL_dc, dL_dd)
        return dL_dh, dL_dc, dL_dd


def gradient_check(solver, h=None, eps=1e-5, verbose=True):
    """Verify analytical gradient via finite differences.

    Args:
        solver: TPSSolver instance
        h: bolt heights for test (random if None)
        eps: FD perturbation
        verbose: print results

    Returns:
        cosine_sim: cosine similarity between AD and FD gradients
        max_rel_err: maximum relative error
    """
    if h is None:
        np.random.seed(42)
        h = np.random.randn(solver.N) * 0.001  # 1mm scale

    # Target: a simple quadratic bowl surface
    w_target = 0.001 * (Xg**2 / (W/2)**2 + Zg**2 / (L/2)**2)

    # Forward pass
    c, d = solver.solve(h)
    w_proxy = solver.surface(c, d)
    diff = w_proxy - w_target
    loss = 0.5 * np.mean(diff**2)
    dL_dw = diff / diff.size  # MSE gradient

    # Analytical gradient
    dL_dh_ad, _, _ = solver.full_backward(dL_dw, c, d)

    # Finite difference gradient
    dL_dh_fd = np.zeros(solver.N)
    for i in range(solver.N):
        h_pert = h.copy()
        h_pert[i] += eps
        c_p, d_p = solver.solve(h_pert)
        w_p = solver.surface(c_p, d_p)
        loss_p = 0.5 * np.mean((w_p - w_target)**2)
        dL_dh_fd[i] = (loss_p - loss) / eps

    # Compare
    dot = np.dot(dL_dh_ad, dL_dh_fd)
    cosine_sim = dot / (np.linalg.norm(dL_dh_ad) * np.linalg.norm(dL_dh_fd) + 1e-30)
    rel_err = np.abs(dL_dh_ad - dL_dh_fd) / (np.abs(dL_dh_fd) + 1e-10)
    max_rel_err = np.max(rel_err)

    if verbose:
        print(f"[Gradient Check] cosine_sim={cosine_sim:.6f}, "
              f"max_rel_err={max_rel_err:.2e}, eps={eps}")

    return cosine_sim, max_rel_err


# ── Quick self-test ──
if __name__ == '__main__':
    print("=" * 60)
    print("TPS Solver Self-Test")
    print("=" * 60)

    solver = TPSSolver()

    # Test 1: round-trip consistency
    print("\n[Test 1] Round-trip: h → surface → bolt positions")
    h_test = np.zeros(solver.N)
    h_test[17] = 0.001  # 1mm at center bolt
    c, d = solver.solve(h_test)
    w = solver.surface(c, d)

    # Check that w ≈ h at bolt positions
    bolt_w = np.array([w[np.argmin(np.abs(Z_GRID - solver.bolt_z[b])),
                          np.argmin(np.abs(X_GRID - solver.bolt_x[b]))]
                       for b in range(solver.N)])
    max_err = np.max(np.abs(bolt_w - h_test))
    print(f"  Max error at bolt positions: {max_err:.2e} m")

    # Test 2: all-zero → zero surface
    print("\n[Test 2] Zero heights → zero surface")
    h_zero = np.zeros(solver.N)
    c0, d0 = solver.solve(h_zero)
    w0 = solver.surface(c0, d0)
    print(f"  Surface PV: {np.ptp(w0)*1000:.6f} mm (should be ~0)")

    # Test 3: gradient check
    print("\n[Test 3] Gradient check (FD vs AD)")
    cos_sim, max_err = gradient_check(solver, verbose=True)
    if cos_sim > 0.99:
        print("  PASS: cosine similarity > 0.99")
    else:
        print(f"  WARNING: cosine similarity = {cos_sim:.4f}")

    # Test 4: surface with normals
    print("\n[Test 4] Surface + analytical normals")
    h_bowl = np.zeros(solver.N)
    h_bowl[17] = -0.005  # -5mm at center → slight bowl
    c_b, d_b = solver.solve(h_bowl)
    w_b, dwdx, dwdz, nx, ny, nz = solver.surface_with_normals(c_b, d_b)
    print(f"  Surface PV: {np.ptp(w_b)*1000:.2f} mm")
    print(f"  dwdx PV: {np.ptp(dwdx):.6f}, dwdz PV: {np.ptp(dwdz):.6f}")
    print(f"  Normal ranges: nx∈[{nx.min():.4f},{nx.max():.4f}], "
          f"nz∈[{nz.min():.4f},{nz.max():.4f}]")

    print("\n" + "=" * 60)
    print("All self-tests complete.")
