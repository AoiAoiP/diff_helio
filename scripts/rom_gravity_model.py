# Track B: analytic reduced-order model (ROM) for the gravity deformation field.
# w_0(x,z,theta;pi) = sum_k c_k(theta) * B_k(x,z;pi)
# Basis fields are kinematically exact in the layout pi (bolt rows/cols enter
# explicitly): continuous-beam profiles (three-moment equation) along each bolt
# axis + per-bay sag bumps. Coefficients shared across layouts, fitted on
# m02/m04/m08, validated on m06 hold-out (gate G2).
import numpy as np

G = 32          # bin grid (row=z 9.45m 5 bolts, col=x 12.84m 7 bolts)
W, L = 12.84, 9.45
ANG20 = [10,14,18,22,26,30,34,38,42,46,50,54,58,62,66,70,73,76,78,80]
ANG4 = [10,30,58,80]

# ---------------------------------------------------------------- beam solver
def continuous_beam(supports, L_beam, q=1.0):
    """Continuous beam on point supports (zero settlement), UDL q, free ends
    (overhangs = distances from first/last support to the ends).
    Returns (w_fn, s_fn): evaluate deflection (down-positive) and slope at s.
    Closed-form per-span polynomials from the three-moment equation."""
    xp = np.asarray(supports, float)
    n = len(xp)
    a_l, a_r = xp[0], L_beam - xp[-1]
    M = np.zeros(n)
    M[0] = -q * a_l**2 / 2.0
    M[-1] = -q * a_r**2 / 2.0
    if n > 2:
        A = np.zeros((n - 2, n - 2)); rhs = np.zeros(n - 2)
        for k in range(1, n - 1):
            Ll = xp[k] - xp[k - 1]; Lr = xp[k + 1] - xp[k]
            r = k - 1
            A[r, r] = 2.0 * (Ll + Lr)
            if r > 0: A[r, r - 1] = Ll
            else: rhs[r] -= M[0] * Ll
            if r < n - 3: A[r, r + 1] = Lr
            else: rhs[r] -= M[-1] * Lr
            rhs[r] += -q / 4.0 * (Ll**3 + Lr**3)
        M[1:-1] = np.linalg.solve(A, rhs)

    # per-span deflection (math up-positive: w'' = M), then flip to down-positive
    spans = []
    for i in range(n - 1):
        Li = xp[i + 1] - xp[i]
        Mi, Mn = M[i], M[i + 1]
        # w(s) = Mi s^2/2 + (Mn-Mi) s^3/(6 Li) + q Li s^3/12 - q s^4/24 + C1 s
        C1 = -(Mi * Li / 2.0 + (Mn - Mi) * Li / 6.0 + q * Li**3 / 24.0)
        spans.append((xp[i], Li, Mi, Mn, C1))

    def w_span(s, i):
        x0, Li, Mi, Mn, C1 = spans[i]
        t = s - x0
        return (Mi * t**2 / 2.0 + (Mn - Mi) * t**3 / (6.0 * Li)
                + q * Li * t**3 / 12.0 - q * t**4 / 24.0 + C1 * t)

    def th_span(s, i):
        x0, Li, Mi, Mn, C1 = spans[i]
        t = s - x0
        return (Mi * t + (Mn - Mi) * t**2 / (2.0 * Li)
                + q * Li * t**2 / 4.0 - q * t**3 / 6.0 + C1)

    # overhangs: cantilever moment M(t) = -q(a+t)^2/2, root slope from span 1
    def w_over_left(s):  # s in [0, xp[0]]
        t = s - xp[0]    # t in [-a_l, 0]
        th0 = th_span(xp[0], 0)
        D1 = th0 + q * a_l**3 / 6.0
        D2 = q * a_l**4 / 24.0
        return -q * (a_l + t)**4 / 24.0 + D1 * t + D2

    def w_over_right(s):  # s in [xp[-1], L_beam]
        t = s - xp[-1]
        th0 = th_span(xp[-1], n - 2)
        D1 = th0 - q * a_r**3 / 6.0
        D2 = q * a_r**4 / 24.0
        return -q * (a_r - t)**4 / 24.0 + D1 * t + D2

    def w_fn(s):
        s = np.asarray(s, float)
        out = np.empty_like(s)
        for idx in np.ndindex(s.shape):
            v = s[idx]
            if v <= xp[0]: out[idx] = w_over_left(v)
            elif v >= xp[-1]: out[idx] = w_over_right(v)
            else:
                i = np.searchsorted(xp, v) - 1
                out[idx] = w_span(v, i)
        return -out  # down-positive

    def s_fn(s):
        s = np.asarray(s, float)
        out = np.empty_like(s)
        eps = 1e-6
        out = -(w_fn(s + eps) - w_fn(s - eps)) / (2 * eps)  # numeric, sign consistent
        return out

    return w_fn, s_fn


def ss_sag(supports, L_beam, q=1.0):
    """Per-span simply-supported sag bumps (zero at each support), down-positive."""
    xp = np.concatenate([[0.0], supports, [L_beam]])
    def fn(s):
        s = np.asarray(s, float); out = np.zeros_like(s)
        for i in range(len(xp) - 1):
            m = (s >= xp[i]) & (s <= xp[i + 1])
            Li = xp[i + 1] - xp[i]; t = s[m] - xp[i]
            out[m] = q * t * (Li - t) * (Li**2 + t * (Li - t)) / 24.0
        return out
    return fn


# ---------------------------------------------------------------- basis
def bolt_positions(margin, nbolts):
    return margin + (1 - 2 * margin) * np.arange(nbolts) / (nbolts - 1)

def basis_fields(margin):
    """Return list of 32x32 basis fields (row=z, col=x) for layout margin."""
    xs = bolt_positions(margin, 7) * W
    zs = bolt_positions(margin, 5) * L
    bx, _ = continuous_beam(xs, W)
    bz, _ = continuous_beam(zs, L)
    sx = ss_sag(xs, W); sz = ss_sag(zs, L)
    gx = (np.arange(G) + 0.5) / G * W   # col -> x
    gz = (np.arange(G) + 0.5) / G * L   # row -> z
    BX = bx(gx)[None, :].repeat(G, 0)   # (z,x)
    BZ = bz(gz)[:, None].repeat(G, 1)
    SX = sx(gx)[None, :].repeat(G, 0)
    SZ = sz(gz)[:, None].repeat(G, 1)
    ONE = np.ones((G, G))
    return [ONE, BX, BZ, BX * BZ, SX * SZ]

# ---------------------------------------------------------------- data
def load_w(d, a):
    return np.fromfile(f"{d}/gravity_{a}deg.bin", dtype=np.float32).reshape(3, G, G)[0]

D02 = "0730_margin_2/data_proxy_margin/7x5_margin02"
D04 = "0730_margin_2/data_proxy_margin/7x5_margin04"
D06 = "margin06_data_2026-07-30/data_proxy_margin/7x5_margin06"
D08 = "data_proxy"

if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True, linewidth=200)
    # ---- sanity checks ----
    w2, _ = continuous_beam([0.0, 1.0], 1.0)          # SS beam
    got = w2(np.array([0.5]))[0]
    exp = 5.0 / 384.0
    print(f"[sanity] SS beam center: got {got:.6f}, expect {exp:.6f}  {'OK' if abs(got-exp)<1e-9 else 'FAIL'}")
    w3, _ = continuous_beam([0.0, 1.0, 2.0], 2.0)     # 2-span continuous
    # textbook: M_mid = -qL^2/8 -> span max deflection = qL^4/185EI ~ 0.00541 (down)
    print(f"[sanity] 2-span mid-span defl: {w3(np.array([0.5]))[0]:.6f} (textbook ~0.00541)")
    wc, _ = continuous_beam([1.0, 2.0], 3.0)          # overhangs 1m each
    print(f"[sanity] overhang tips: {wc(np.array([0.0]))[0]:.6f} {wc(np.array([3.0]))[0]:.6f} (should be >0, symmetric)")

    # ---- fit per angle (stacked LS over m02[4ang]+m04+m08), validate m06 ----
    print("\nangle | cos_fit(cal) | cos_m06 relL2_m06 | coefs")
    stats = []
    for a in ANG20:
        rows_y, rows_B = [], []
        for d, m in ([(D02, 0.02)] if a in ANG4 else []) + [(D04, 0.04), (D08, 0.08)]:
            B = basis_fields(m)
            rows_B.append(np.stack([b.ravel() for b in B], 1))
            rows_y.append(load_w(d, a).ravel())
        Bm = np.concatenate(rows_B, 0); y = np.concatenate(rows_y)
        c, *_ = np.linalg.lstsq(Bm, y, rcond=None)
        fit = Bm @ c
        cos_fit = float(fit @ y / np.linalg.norm(fit) / np.linalg.norm(y))
        # hold-out
        B6 = np.stack([b.ravel() for b in basis_fields(0.06)], 1)
        y6 = load_w(D06, a).ravel()
        p6 = B6 @ c
        cos6 = float(p6 @ y6 / np.linalg.norm(p6) / np.linalg.norm(y6))
        rl6 = float(np.linalg.norm(p6 - y6) / np.linalg.norm(y6))
        stats.append((a, cos_fit, cos6, rl6))
        print(f"  {a:>3} | {cos_fit:.4f} | {cos6:.4f}  {rl6:.4f} | {c}")
    arr = np.array([s[1:] for s in stats])
    low = arr[[ANG20.index(a) for a in [10, 14, 18, 22, 26, 30]]]
    print(f"\nG2 gate: 10-30deg mean cos={low[:,1].mean():.4f} (target>=0.99) | all-angle mean cos={arr[:,1].mean():.4f} (target>=0.98)")
