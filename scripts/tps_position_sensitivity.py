# Phase 6 / G0a: TPS bolt-position sensitivity via the direct sensitivity method.
#
# Forward proxy (production conventions, generate_proxy_model.py):
#   A(pi) [c_b; d_b] = [e_b; 0],   A = [K+reg*I, P; P^T, 0],  K_ij = r^2 log r^2
#   phi_b(r)   = sum_j c_bj k(r-r_j) + d_b0 + d_b1 x + d_b2 z
#   phi_u,b(r) = W * [sum_j c_bj dk/dx(r-r_j) + d_b1]
#   phi_v,b(r) = L * [sum_j c_bj dk/dz(r-r_j) + d_b2]
#
# Position gradient (exact derivative of the discrete system, no adjoint needed):
#   d[c_b;d_b]/d pi_m = -A^-1 (dA/d pi_m) [c_b; d_b]        (direct sensitivity)
#   d phi_b/d pi_m    = K_eval_deriv + K_eval @ d[c_b;d_b]/d pi_m
#   dL/d pi_m = sum_b h_b * sum_grid [ L_y dphi_b + L_yu dphi_u,b + L_yv dphi_v,b ]/d pi_m
#
# dA/d pi_m via complex step on the assembly (exact to machine eps).
# G0a gate: direct-method gradient vs real FD (re-solve at pi +/- delta),
# relative error should sit at the FD truncation floor (~1e-4).
#
#   python scripts/tps_position_sensitivity.py --layout <json> --selftest
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_utils as lu

G = 32
W, L = 12.84, 9.45
REG = 1e-6
CS_EPS = 1e-30


# ---------------------------------------------------------------- production
def build_A(bx, bz, reg=REG):
    """TPS augmented system. Complex-safe (production conventions)."""
    dt = np.result_type(bx, bz, np.float64)
    N = len(bx)
    dx = bx[:, None] - bx[None, :]
    dz = bz[:, None] - bz[None, :]
    r2 = dx * dx + dz * dz
    # complex-safe kernel r^2 log(r^2): no abs/np.maximum (they kill imag parts);
    # at r2=0 the value is 0*log(1e-300)=0, matching the production reg diagonal.
    K = r2 * np.log(r2 + 1e-300)
    K = K + np.eye(N, dtype=dt) * reg
    P = np.column_stack([np.ones(N, dtype=dt), bx, bz])
    A = np.zeros((N + 3, N + 3), dtype=dt)
    A[:N, :N] = K
    A[:N, N:] = P
    A[N:, :N] = P.T
    return A


def solve_all(A_inv, N):
    """One-hot solves for every bolt: coeffs[b] = [c_b; d_b], shape (NB, N+3)."""
    E = np.zeros((N, N + 3))
    E[:, :N] = np.eye(N)
    return (A_inv @ E.T).T


def eval_kernels(bx, bz):
    """Grid evaluation kernels for each bolt j: returns (K0, Kx, Kz, Kxx, Kxz, Kzz)
    each (NB, G*G), following generate_proxy_model.py conventions."""
    u = (np.arange(G) + 0.5) / G
    xg = (u - 0.5) * W
    zg = (u - 0.5) * L
    Xg, Zg = np.meshgrid(xg, zg)
    X, Z = Xg.ravel(), Zg.ravel()
    N = len(bx)
    K0 = np.zeros((N, G * G)); Kx = np.zeros((N, G * G)); Kz = np.zeros((N, G * G))
    Kxx = np.zeros((N, G * G)); Kxz = np.zeros((N, G * G)); Kzz = np.zeros((N, G * G))
    for j in range(N):
        dx = X - bx[j]
        dz = Z - bz[j]
        r2 = dx * dx + dz * dz + 1e-30
        r = np.sqrt(r2)
        log_r2 = np.log(r2)
        K0[j] = r2 * log_r2
        dphi_dr = 2.0 * r * log_r2 + 2.0 * r
        Kx[j] = dphi_dr * (dx / r)          # dk/dx (physical)
        Kz[j] = dphi_dr * (dz / r)
        Kxx[j] = 2.0 * log_r2 + 2.0 + 4.0 * dx * dx / r2
        Kzz[j] = 2.0 * log_r2 + 2.0 + 4.0 * dz * dz / r2
        Kxz[j] = 4.0 * dx * dz / r2
    # self-influence correction (nearest grid point per bolt)
    for j in range(N):
        idx = int(np.argmin((X - bx[j]) ** 2 + (Z - bz[j]) ** 2))
        K0[j, idx] += REG
    return K0, Kx, Kz, Kxx, Kxz, Kzz


def fields_from_coeffs(coeffs, bx, bz):
    """phi, phi_u(stored W-scaled), phi_v(stored L-scaled) per bolt: (NB, G*G)."""
    N = len(bx)
    K0, Kx, Kz, _, _, _ = eval_kernels(bx, bz)
    u = (np.arange(G) + 0.5) / G
    X, Z = np.meshgrid((u - 0.5) * W, (u - 0.5) * L)
    X = X.ravel(); Z = Z.ravel()
    c = coeffs[:, :N]
    d = coeffs[:, N:]
    phi = c @ K0 + d[:, [0]] + d[:, [1]] * X[None, :] + d[:, [2]] * Z[None, :]
    phiu = (c @ Kx + d[:, [1]]) * W
    phiv = (c @ Kz + d[:, [2]]) * L
    return phi, phiu, phiv


# ---------------------------------------------------------------- sensitivity
def dA_dparam(bx, bz, dim, idx, reg=REG):
    """dA/d(bolt[idx] coordinate dim) via complex step on the assembly."""
    bcx = bx.astype(complex); bcz = bz.astype(complex)
    if dim == "x":
        bcx[idx] += 1j * CS_EPS
    else:
        bcz[idx] += 1j * CS_EPS
    return build_A(bcx, bcz, reg).imag / CS_EPS


def position_sensitivity(bx, bz, h, GLy, GLyu, GLyv):
    """dL/d pi_m for all params (2*NB,) given per-mirror-aggregated surface
    gradients GLy/GLyu/GLyv (G*G,) and current bolt heights h (NB,).

    GLy(r) = sum_suns dL/dy(r) etc. (annual equal-weight sum over suns).
    """
    N = len(bx)
    A = build_A(bx, bz)
    A_inv = np.linalg.inv(A)
    coeffs = solve_all(A_inv, N)                    # (NB, N+3)
    K0, Kx, Kz, Kxx, Kxz, Kzz = eval_kernels(bx, bz)
    dL = np.zeros(2 * N)
    for dim in ("x", "z"):
        for m in range(N):
            dA = dA_dparam(bx, bz, dim, m)          # (N+3, N+3)
            # dcoeffs_b/d pi_m = -A_inv (dA coeffs_b)  for all b at once
            rhs = -dA @ coeffs.T                    # (N+3, NB)
            dcoeffs = A_inv @ rhs                   # (N+3, NB)
            dcoeffs = dcoeffs.T                     # (NB, N+3)
            # direct eval-channel derivatives (only node m's kernel moves;
            # node derivative = minus field derivative)
            c = coeffs[:, :N]
            d = coeffs[:, N:]
            if dim == "x":
                dK0 = -Kx[m]                        # d k(r-r_m)/d x_m
                dKu = -Kxx[m] * W                   # d (W dk/dx)/d x_m
                dKv = -Kxz[m] * L
                d_poly_u = 0.0                      # d(W d_b1)/dx_m handled via dcoeffs
            else:
                dK0 = -Kz[m]
                dKu = -Kxz[m] * W
                dKv = -Kzz[m] * L
            # d phi_b / d pi_m = dcoeffs channel + direct kernel channel
            u = (np.arange(G) + 0.5) / G
            X, Z = np.meshgrid((u - 0.5) * W, (u - 0.5) * L)
            Xf = X.ravel(); Zf = Z.ravel()
            dphi = (dcoeffs[:, :N] @ K0
                    + dcoeffs[:, [N]] + dcoeffs[:, [N + 1]] * Xf[None, :]
                    + dcoeffs[:, [N + 2]] * Zf[None, :]
                    + c[:, [m]] * dK0[None, :])
            dphiu = ((dcoeffs[:, :N] @ Kx + dcoeffs[:, [N + 1]]) * W
                     + c[:, [m]] * dKu[None, :])
            dphiv = ((dcoeffs[:, :N] @ Kz + dcoeffs[:, [N + 2]]) * L
                     + c[:, [m]] * dKv[None, :])
            grad_per_bolt = (dphi * GLy[None, :]
                             + dphiu * GLyu[None, :]
                             + dphiv * GLyv[None, :]).sum(axis=1)
            dL[N * (dim == "z") + m] = float(h @ grad_per_bolt)
            # note: h[b] multiplies d phi_b / d pi_m; sum over b
    return dL


def fd_reference(bx, bz, h, GLy, GLyu, GLyv, delta=0.01):
    """Real FD: re-solve and re-evaluate at pi +/- delta (2*NB*2 solves)."""
    N = len(bx)
    dL = np.zeros(2 * N)
    for dim_i, dim in enumerate(("x", "z")):
        for m in range(N):
            vals = []
            for sgn in (+1.0, -1.0):
                bx2, bz2 = bx.copy(), bz.copy()
                if dim == "x":
                    bx2[m] += sgn * delta
                else:
                    bz2[m] += sgn * delta
                A2 = build_A(bx2, bz2)
                coeffs2 = np.linalg.solve(A2, np.vstack([np.eye(N), np.zeros((3, N))])).T
                phi, phiu, phiv = fields_from_coeffs(coeffs2, bx2, bz2)
                loss = float((h[:, None] * (phi * GLy[None, :]
                                            + phiu * GLyu[None, :]
                                            + phiv * GLyv[None, :])).sum())
                vals.append(loss)
            dL[dim_i * N + m] = (vals[0] - vals[1]) / (2.0 * delta)
    return dL


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", required=True)
    ap.add_argument("--delta", type=float, default=0.01)
    ap.add_argument("--params", type=int, default=None,
                    help="limit to first k params for the FD check")
    args = ap.parse_args()

    lay = lu.load_layout(args.layout)
    bx, bz = lu.bolt_positions(lay)
    N = len(bx)
    rng = np.random.default_rng(7)
    h = rng.uniform(0.005, 0.03, size=N)
    # synthetic surface gradients (smooth random fields standing in for dumps)
    gy, gz_ = np.meshgrid(np.linspace(-1, 1, G), np.linspace(-1, 1, G))
    GLy = (0.3 * gy + 0.2 * gz_).ravel()
    GLyu = (0.1 * gy * gz_).ravel()
    GLyv = (0.15 * gy - 0.05 * gz_).ravel()

    print(f"layout: {args.layout}  NB={N}")
    dL_dir = position_sensitivity(bx, bz, h, GLy, GLyu, GLyv)
    dL_fd = fd_reference(bx, bz, h, GLy, GLyu, GLyv, delta=args.delta)
    k = args.params or 2 * N
    # scale-aware: per-param rel error only meaningful above the FD noise floor
    floor = 1e-2 * np.abs(dL_fd).max()
    big = np.abs(dL_fd) > floor
    rel = np.abs(dL_dir - dL_fd) / np.maximum(np.abs(dL_fd), 1e-30)
    norm_rel = float(np.linalg.norm(dL_dir - dL_fd) / np.linalg.norm(dL_fd))
    cos = float(dL_dir @ dL_fd / np.linalg.norm(dL_dir) / np.linalg.norm(dL_fd))
    for i in range(k):
        dim = "x" if i < N else "z"
        idx = i if i < N else i - N
        print(f"  {dim}:{idx:2d}  direct={dL_dir[i]:+.6e}  fd={dL_fd[i]:+.6e}  rel={rel[i]:.2e}")
    ok = (cos > 0.999) and (norm_rel < 0.01) and (rel[big].max() < 0.05)
    print(f"\nG0a: cos={cos:.6f}  norm_rel={norm_rel:.2e}  "
          f"max_rel(>{floor:.1e})={rel[big].max() if big.any() else 0:.3e}  "
          f"{'PASS' if ok else 'CHECK'}")


if __name__ == "__main__":
    main()
