# G2 gate (part a): synthetic support recovery for the sparse-layout LASSO.
# Ground truth: edge-dense/center-sparse 25-bolt support S* with random
# strokes on the 11x9 m05 layout. Recover from the full 99-bolt dictionary
# in slope space:  J(h) = 1/2 ||A h - y||^2 / ||y||^2 + lambda * ||h||_1
# where A stacks the TPS slope influence functions (phi_u, phi_v).
# Solver: cyclic coordinate descent (deterministic; exact for LASSO).
# Gate: exists lambda on the path with precision AND recall >= 0.9.
#
#   python scripts/g2_lasso_recovery.py
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_proxy_model as gpm
import layout_utils as lu

LAYOUT = "configs/bolt_layouts/density/11x9_margin05.json"
TPS_DIR = "build/_g2/tps_11x9_m05"
GS = 32
TAU = 1e-4          # support threshold (0.1 mm)
N_TRUE = 25


def ground_truth_support():
    """Edge-dense / center-sparse 25-bolt subset of the 11x9 grid.
    Row-major index = j*11 + i (j: z row 0..8, i: x col 0..10)."""
    s = []
    for j in range(9):
        for i in range(11):
            on_peri = (j in (0, 8)) or (i in (0, 10))
            if on_peri and (i + j) % 2 == 0:          # subsampled perimeter
                s.append(j * 11 + i)
    for j in (2, 6):
        for i in (2, 5, 8):                            # inner ring anchors
            s.append(j * 11 + i)
    s.append(4 * 11 + 5)                               # exact center
    return np.array(sorted(set(s))[:N_TRUE])


def main():
    layout = lu.load_layout(LAYOUT)
    bx, bz = lu.bolt_positions(layout)
    NB = len(bx)
    if not os.path.exists(f"{TPS_DIR}/influence_phi_u.bin"):
        print("generating TPS for", LAYOUT, "->", TPS_DIR)
        gpm.generate_influence_data(TPS_DIR, bolt_xz=(bx, bz))
    n_grid = GS * GS
    phi_u = np.fromfile(f"{TPS_DIR}/influence_phi_u.bin",
                        dtype=np.float32).reshape(NB, n_grid).astype(np.float64)
    phi_v = np.fromfile(f"{TPS_DIR}/influence_phi_v.bin",
                        dtype=np.float32).reshape(NB, n_grid).astype(np.float64)
    A = np.vstack([phi_u.T, phi_v.T])                # (2*n_grid, NB)

    rng = np.random.default_rng(42)
    S_star = ground_truth_support()
    h_star = np.zeros(NB)
    h_star[S_star] = rng.uniform(5e-3, 30e-3, size=len(S_star))
    y = A @ h_star
    ynorm2 = float(y @ y)
    print(f"NB={NB}, |S*|={len(S_star)}, ||y||^2={ynorm2:.4e}")

    # column norms (for coordinate descent)
    col_sq = (A ** 2).sum(axis=0) / ynorm2
    At = A.T / ynorm2                                  # so grad_j = col_sq_j h_j - At_j r

    print(f"{'lambda':>10s} {'|S|':>5s} {'prec':>6s} {'recall':>6s} {'resid':>8s}")
    best = None
    for lam in np.logspace(-7, -2, 21):
        h = np.zeros(NB)
        for sweep in range(200):
            max_delta = 0.0
            for j in range(NB):
                if col_sq[j] <= 0:
                    continue
                r_j = At[j] @ (y - A @ h) + col_sq[j] * h[j]
                h_new = np.sign(r_j) * max(abs(r_j) - lam, 0.0) / col_sq[j]
                max_delta = max(max_delta, abs(h_new - h[j]))
                h[j] = h_new
            if max_delta < 1e-12:
                break
        resid = 0.5 * float(((A @ h - y) ** 2).sum()) / ynorm2
        S_hat = np.where(np.abs(h) > TAU)[0]
        tp = len(set(S_hat) & set(S_star))
        prec = tp / max(len(S_hat), 1)
        rec = tp / len(S_star)
        print(f"{lam:10.2e} {len(S_hat):5d} {prec:6.3f} {rec:6.3f} {resid:8.2e}")
        score = min(prec, rec)
        if best is None or score > best[0]:
            best = (score, lam, prec, rec, len(S_hat))
    score, lam, prec, rec, ns = best
    print(f"\nbest: lambda={lam:.2e} precision={prec:.3f} recall={rec:.3f} |S|={ns}")
    ok = prec >= 0.9 and rec >= 0.9
    print(f"G2a gate: {'PASS' if ok else 'FAIL'} (need precision AND recall >= 0.9)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
