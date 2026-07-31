# Track B v4: coarse-mesh Kirchhoff plate FEM as the gravity ROM.
# Exact plate physics (incl. torsion), reduced only in mesh resolution.
# ACM rectangular non-conforming element (12 DOF: w, dw/dx, dw/dy per corner).
# Mesh nodes are smooth functions of the layout (bolt rows/cols + bay subdivisions)
# -> differentiable w.r.t. layout via implicit differentiation of K d = f.
# Validations: (a) SS square plate vs Navier series 0.00406235 qL^4/D;
#              (b) vs ANSYS gravity bins (m08/m04 calib, m06 hold-out).
import numpy as np
from scipy import sparse
from scipy.sparse import linalg as spla

G = 32
W, L = 12.84, 9.45
THK, E_MOD, NU, RHO = 0.004, 7.0e10, 0.22, 2500.0
D_PLATE = E_MOD * THK**3 / (12.0 * (1.0 - NU**2))
Q_AREA = RHO * 9.81 * THK
ANG20 = [10,14,18,22,26,30,34,38,42,46,50,54,58,62,66,70,73,76,78,80]

# ------------------------------------------------------------- ACM element
# shape functions on reference square xi,eta in [-1,1], phys size 2a x 2b
# DOFs per node: (w, th_x=dw/dx, th_y=dw/dy)
def _acf(xi, eta, xii, etai):
    A = 1 + xi * xii; B = 1 + eta * etai
    C = 2 + xi * xii + eta * etai - xi**2 - eta**2
    return A, B, C

def acm_N(xi, eta, a, b):
    """12 shape function values."""
    N = np.zeros(12)
    for i, (xii, etai) in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
        A, B, C = _acf(xi, eta, xii, etai)
        N[3*i]   = A * B * C / 8.0
        N[3*i+1] = a / 8.0 * xii * (xi**2 - 1) * A * B
        N[3*i+2] = b / 8.0 * etai * (eta**2 - 1) * A * B
    return N

def acm_B(xi, eta, a, b):
    """curvature matrix: kappa = [w,xx; w,yy; 2w,xy] = B d  (3x12)."""
    B = np.zeros((3, 12))
    for i, (xii, etai) in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
        A, Bb, C = _acf(xi, eta, xii, etai)
        # N_w 2nd derivatives (derived analytically)
        n_xixi = -0.75 * xi * xii * (1 + eta * etai)
        n_etaeta = -0.75 * eta * etai * (1 + xi * xii)
        # d2(ABC)/dxi deta = xii*(etai-2*eta)*B + etai*(xii*C + A*(xii-2*xi))
        n_xieta = 0.125 * (xii * (etai - 2 * eta) * Bb
                           + etai * (xii * C + A * (xii - 2 * xi)))
        # N_thx = (a/8) xii (xi^2-1) A B
        tx_xixi = (a / 8.0) * xii * (1 + eta * etai) * (2 + 6 * xi * xii)
        tx_etaeta = 0.0
        tx_xieta = (a / 8.0) * xii * etai * (2 * xi + 3 * xi**2 * xii - xii)
        # N_thy = (b/8) etai (eta^2-1) A B  (symmetric)
        ty_etaeta = (b / 8.0) * etai * (1 + xi * xii) * (2 + 6 * eta * etai)
        ty_xixi = 0.0
        ty_xieta = (b / 8.0) * xii * etai * (2 * eta + 3 * eta**2 * etai - etai)
        for col, (xx, yy, xy) in enumerate([
                (n_xixi, n_etaeta, n_xieta),
                (tx_xixi, tx_etaeta, tx_xieta),
                (ty_xixi, ty_etaeta, ty_xieta)]):
            B[0, 3*i+col] = xx / a**2
            B[1, 3*i+col] = yy / b**2
            B[2, 3*i+col] = 2.0 * xy / (a * b)
    return B

_GPT = [-np.sqrt(3/5), 0.0, np.sqrt(3/5)]
_GWT = [5/9, 8/9, 5/9]

def acm_element(ax, bx, Dm):
    """K_e (12x12) and consistent UDL f_e for element half-sizes ax,bx."""
    K = np.zeros((12, 12)); f = np.zeros(12)
    Dmat = Dm * np.array([[1, NU, 0], [NU, 1, 0], [0, 0, (1 - NU) / 2]])
    for i in range(3):
        for j in range(3):
            xi, eta = _GPT[i], _GPT[j]
            wgt = _GWT[i] * _GWT[j] * ax * bx
            B = acm_B(xi, eta, ax, bx)
            K += wgt * B.T @ Dmat @ B
            f += wgt * acm_N(xi, eta, ax, bx)
    return K, f

# ------------------------------------------------------------- mesh + solve
def make_mesh(margin, n_bay=2, n_over=1, patch_hw=0.3):
    """Node lines as smooth functions of margin: bolt lines + patch-edge lines
    (bolt +/- patch_hw) + n_bay subdivisions per bay + n_over per overhang.
    Patch-interior segments get no subdivision (nodes there are fixed anyway)."""
    def lines(n_bolts, S):
        bp = margin + (1 - 2 * margin) * np.arange(n_bolts) / (n_bolts - 1)
        bp = bp * S
        hard = {0.0, float(S)} | set(bp.tolist())
        for b in bp:
            for e in (b - patch_hw, b + patch_hw):
                if 0.0 < e < S:
                    hard.add(e)
        hard = sorted(hard)
        pts = set(hard)
        for s0, s1 in zip(hard[:-1], hard[1:]):
            mid = 0.5 * (s0 + s1)
            if any(abs(mid - b) < patch_hw - 1e-12 for b in bp):
                nsub = 0                      # inside a bolt patch
            elif s1 <= bp[0] or s0 >= bp[-1]:
                nsub = n_over                 # overhang
            else:
                nsub = n_bay                  # bay
            for k in range(1, nsub + 1):
                pts.add(s0 + (s1 - s0) * k / (nsub + 1))
        return np.sort(np.array(list(pts))), bp
    xs, bpx = lines(7, W)
    zs, bpz = lines(5, L)
    return xs, zs, bpx, bpz

class PlateROM:
    def __init__(self, margin, n_bay=2, n_over=1, patch_hw=0.3):
        self.margin = margin
        xs, zs, bpx, bpz = make_mesh(margin, n_bay, n_over, patch_hw)
        self.xs, self.zs, self.bpx, self.bpz = xs, zs, bpx, bpz
        nx, nz = len(xs), len(zs)
        self.nx, self.nz = nx, nz
        ndof = 3 * nx * nz
        self.ndof = ndof
        K = sparse.lil_matrix((ndof, ndof))
        f = np.zeros(ndof)
        self.elem = []
        for j in range(nz - 1):
            for i in range(nx - 1):
                ax = (xs[i+1] - xs[i]) / 2; bx = (zs[j+1] - zs[j]) / 2
                Ke, fe = acm_element(ax, bx, D_PLATE)
                dofs = []
                for dj, di in [(0,0),(1,0),(1,1),(0,1)]:
                    n = (j + dj) * nx + (i + di)
                    dofs += [3*n, 3*n+1, 3*n+2]
                self.elem.append((i, j, ax, bx, dofs))
                for a in range(12):
                    f[dofs[a]] += fe[a]
                    for b in range(12):
                        K[dofs[a], dofs[b]] += Ke[a, b]
        self.K = K.tocsr(); self.f = f
        # supports: w=0 on a (2*patch_hw) square patch around each bolt,
        # matching the ANSYS APDL BC (HALF_WIN=0.3, translations only).
        sup = []
        tol = patch_hw + 1e-9
        for j, z in enumerate(zs):
            for i, x in enumerate(xs):
                for bz_ in bpz:
                    if abs(z - bz_) > tol:
                        continue
                    for bx_ in bpx:
                        if abs(x - bx_) <= tol:
                            sup.append(3 * (j * nx + i))
                            break
                    else:
                        continue
                    break
        self.sup = np.array(sorted(set(sup)), dtype=int)
        self.free = np.array([i for i in range(ndof) if i not in self.sup])
        self.Kff = self.K[self.free][:, self.free].tocsc()
        self.solve_lu = spla.factorized(self.Kff)

    def solve(self, q_area):
        d = np.zeros(self.ndof)
        d[self.free] = self.solve_lu(self.f[self.free] * q_area)
        self.d = d
        return d

    def w_at(self, x, z):
        i = int(np.clip(np.searchsorted(self.xs, x) - 1, 0, self.nx - 2))
        j = int(np.clip(np.searchsorted(self.zs, z) - 1, 0, self.nz - 2))
        # find element
        for (ei, ej, ax, bx, dofs) in self.elem:
            if ei == i and ej == j:
                x0 = self.xs[i]; z0 = self.zs[j]
                xi = (x - (x0 + ax)) / ax; eta = (z - (z0 + bx)) / bx
                N = acm_N(xi, eta, ax, bx)
                return float(N @ self.d[dofs])
        return 0.0

    def surface(self):
        gx = (np.arange(G) + 0.5) / G * W
        gz = (np.arange(G) + 0.5) / G * L
        out = np.zeros((G, G))
        for j, z in enumerate(gz):
            for i, x in enumerate(gx):
                out[j, i] = self.w_at(x, z)
        return out

# ------------------------------------------------------------- von Karman extension
def acm_Nd(xi, eta, a, b):
    """first derivatives of ACM shape functions: (2,12) = [dN/dx; dN/dy]."""
    Gm = np.zeros((2, 12))
    for i, (xii, etai) in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
        A, Bb, C = _acf(xi, eta, xii, etai)
        nw_xi  = Bb * (xii * C + A * (xii - 2 * xi)) / 8.0
        nw_eta = A * (etai * C + Bb * (etai - 2 * eta)) / 8.0
        tx_xi  = (a / 8.0) * xii * Bb * (2 * xi * A + (xi**2 - 1) * xii)
        tx_eta = (a / 8.0) * xii * (xi**2 - 1) * A * etai
        ty_xi  = (b / 8.0) * etai * (eta**2 - 1) * xii * Bb
        ty_eta = (b / 8.0) * etai * A * (2 * eta * Bb + (eta**2 - 1) * etai)
        for col, (gx, gy) in enumerate([(nw_xi, nw_eta), (tx_xi, tx_eta), (ty_xi, ty_eta)]):
            Gm[0, 3*i+col] = gx / a
            Gm[1, 3*i+col] = gy / b
    return Gm

def q4_N(xi, eta):
    return np.array([(1 - xi) * (1 - eta), (1 + xi) * (1 - eta),
                     (1 + xi) * (1 + eta), (1 - xi) * (1 + eta)]) / 4.0

def q4_Bm(xi, eta, a, b):
    Bm = np.zeros((3, 8))
    for i, (xii, etai) in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
        dx = xii * (1 + etai * eta) / (4 * a)
        dy = etai * (1 + xii * xi) / (4 * b)
        Bm[0, 2*i] = dx
        Bm[1, 2*i+1] = dy
        Bm[2, 2*i] = dy
        Bm[2, 2*i+1] = dx
    return Bm

_CHAT = E_MOD / (1.0 - NU**2) * np.array(
    [[1, NU, 0], [NU, 1, 0], [0, 0, (1.0 - NU) / 2]])

class PlateVK(PlateROM):
    """von Karman plate ROM: ACM bending + Q4 membrane on the same rect mesh,
    coupled by von Karman strains; alternating block iteration.
    Patch BCs fix w,u,v (matches ANSYS D,ALL,UX/UY/UZ at bolt patches).
    In-plane gravity component q_in acts along plate-local +z."""

    def __init__(self, margin, n_bay=4, n_over=2, patch_hw=0.3):
        super().__init__(margin, n_bay, n_over, patch_hw)
        nx = self.nx
        self.ndm = 2 * nx * self.nz
        Km = sparse.lil_matrix((self.ndm, self.ndm))
        fm = np.zeros(self.ndm)
        self.elem_m = []
        for (i, j, ax, bx, dofs_b) in self.elem:
            dofs_m = []
            for dj, di in [(0,0),(1,0),(1,1),(0,1)]:
                n = (j + dj) * nx + (i + di)
                dofs_m += [2*n, 2*n+1]
            self.elem_m.append((ax, bx, dofs_b, dofs_m))
            Ke = np.zeros((8, 8)); fe = np.zeros(8)
            for ii in range(3):
                for jj in range(3):
                    xi, eta = _GPT[ii], _GPT[jj]
                    wgt = _GWT[ii] * _GWT[jj] * ax * bx
                    Bm = q4_Bm(xi, eta, ax, bx)
                    Ke += wgt * THK * Bm.T @ _CHAT @ Bm
                    fe[1::2] += wgt * q4_N(xi, eta)
            for aa in range(8):
                fm[dofs_m[aa]] += fe[aa]
                for bb in range(8):
                    Km[dofs_m[aa], dofs_m[bb]] += Ke[aa, bb]
        self.Km = Km.tocsr(); self.fm = fm
        nodes = sorted(set((self.sup // 3).tolist()))
        sup_m = sorted(set(d for n in nodes for d in (2*n, 2*n+1)))
        self.sup_m = np.array(sup_m, dtype=int)
        sm = set(self.sup_m)
        self.free_m = np.array([d for d in range(self.ndm) if d not in sm])
        self.solve_km = spla.factorized(self.Km[self.free_m][:, self.free_m].tocsc())

    def _nl_mem_rhs(self, d_b):
        """sum_e int Bm^T t Chat eps_nl(w) dA  (assembled over membrane DOFs)."""
        rhs = np.zeros(self.ndm)
        for (ax, bx, dofs_b, dofs_m) in self.elem_m:
            d_e = d_b[dofs_b]
            re = np.zeros(8)
            for ii in range(3):
                for jj in range(3):
                    xi, eta = _GPT[ii], _GPT[jj]
                    wgt = _GWT[ii] * _GWT[jj] * ax * bx
                    Gm = acm_Nd(xi, eta, ax, bx)
                    wx, wy = Gm[0] @ d_e, Gm[1] @ d_e
                    enl = np.array([0.5*wx*wx, 0.5*wy*wy, wx*wy])
                    Nnl = THK * _CHAT @ enl
                    re += wgt * q4_Bm(xi, eta, ax, bx).T @ Nnl
            rhs[dofs_m] += re
        return rhs

    def _geometric_stiffness(self, d_b, d_m):
        Kg = sparse.lil_matrix((self.ndof, self.ndof))
        for (ax, bx, dofs_b, dofs_m) in self.elem_m:
            d_e = d_b[dofs_b]; u_e = d_m[dofs_m]
            Ke = np.zeros((12, 12))
            for ii in range(3):
                for jj in range(3):
                    xi, eta = _GPT[ii], _GPT[jj]
                    wgt = _GWT[ii] * _GWT[jj] * ax * bx
                    Gm = acm_Nd(xi, eta, ax, bx)
                    wx, wy = Gm[0] @ d_e, Gm[1] @ d_e
                    eps = q4_Bm(xi, eta, ax, bx) @ u_e \
                        + np.array([0.5*wx*wx, 0.5*wy*wy, wx*wy])
                    N = THK * _CHAT @ eps
                    Nm = np.array([[N[0], N[2]], [N[2], N[1]]])
                    Ke += wgt * Gm.T @ Nm @ Gm
            for aa in range(12):
                for bb in range(12):
                    Kg[dofs_b[aa], dofs_b[bb]] += Ke[aa, bb]
        return Kg.tocsr()

    def solve_vk(self, q_n, q_in, d_b0=None, max_iter=60, tol=1e-8, verbose=False):
        """Alternating block iteration with Aitken delta^2 acceleration.
        Returns (iters, converged)."""
        if d_b0 is None:
            d_b = np.zeros(self.ndof)
            d_b[self.free] = self.solve_lu(self.f[self.free] * q_n)
        else:
            d_b = d_b0.copy()
        d_m = np.zeros(self.ndm)
        hist = []
        for it in range(max_iter):
            rhs = self.fm * q_in - self._nl_mem_rhs(d_b)
            d_m[self.free_m] = self.solve_km(rhs[self.free_m])
            Kg = self._geometric_stiffness(d_b, d_m)
            Kff = (self.K + Kg)[self.free][:, self.free].tocsc()
            d_new = np.zeros(self.ndof)
            d_new[self.free] = spla.spsolve(Kff, self.f[self.free] * q_n)
            denom = max(np.max(np.abs(d_new)), 1e-30)
            delta = np.max(np.abs(d_new - d_b)) / denom
            hist.append(d_new)
            if len(hist) == 3:
                d0, d1, d2 = hist
                den = d2 - 2 * d1 + d0
                mask = np.abs(den) > 1e-30 * denom
                d_acc = d2.copy()
                d_acc[mask] = d0[mask] - (d1[mask] - d0[mask])**2 / den[mask]
                d_new = d_acc
                hist = []
            d_b = d_new
            if verbose:
                print(f"  vk it{it}: delta={delta:.2e}")
            if delta < tol:
                self.d = d_b; self.d_m = d_m
                return it + 1, True
        self.d = d_b; self.d_m = d_m
        return max_iter, False


# ------------------------------------------------------------- validation
def navier_ss_center(q=1.0, D=1.0, Lp=1.0, nterms=40):
    s = 0.0
    for m in range(1, 2 * nterms, 2):
        for n in range(1, 2 * nterms, 2):
            s += np.sin(m * np.pi / 2) * np.sin(n * np.pi / 2) / (m * n * (m*m + n*n)**2)
    return 16 * q / (np.pi**6 * D) * s

def test_ss_plate():
    """Simply-supported square plate, UDL: center = 0.00406235 q L^4 / D."""
    global D_PLATE
    D_save = D_PLATE; D_PLATE = 1.0
    n = 9  # 8x8 elements
    xs = np.linspace(0, 1, n); zs = xs
    nx = nz = n; ndof = 3 * nx * nz
    K = sparse.lil_matrix((ndof, ndof)); f = np.zeros(ndof)
    for j in range(nz - 1):
        for i in range(nx - 1):
            ax = (xs[i+1]-xs[i])/2; bx = (zs[j+1]-zs[j])/2
            Ke, fe = acm_element(ax, bx, 1.0)
            dofs = []
            for dj, di in [(0,0),(1,0),(1,1),(0,1)]:
                nn = (j+dj)*nx + (i+di); dofs += [3*nn, 3*nn+1, 3*nn+2]
            for a in range(12):
                f[dofs[a]] += fe[a]
                for b in range(12):
                    K[dofs[a], dofs[b]] += Ke[a, b]
    sup = []
    for j in range(nz):
        for i in range(nx):
            if i == 0 or j == 0 or i == nx-1 or j == nz-1:
                sup.append(3*(j*nx+i))
    free = np.array([i for i in range(ndof) if i not in sup])
    d = np.zeros(ndof)
    d[free] = spla.spsolve(K[free][:, free].tocsc(), f[free])
    center = d[3*((nz//2)*nx + nx//2)]
    D_PLATE = D_save
    exp = 0.00406235
    err = abs(center - exp) / exp
    print(f"[test] SS plate center: FEM={center:.6e} Navier={exp:.6e} err={err*100:.2f}% ({'OK' if err<0.02 else 'FAIL'})")

def load_w(d, a):
    return np.fromfile(f"{d}/gravity_{a}deg.bin", dtype=np.float32).reshape(3, G, G)[0]

D04 = "0730_margin_2/data_proxy_margin/7x5_margin04"
D06 = "margin06_data_2026-07-30/data_proxy_margin/7x5_margin06"
D08 = "data_proxy"

if __name__ == "__main__":
    print("navier check:", navier_ss_center(), "(expect ~0.00406235)")
    test_ss_plate()
    import json
    gj = json.load(open("data_proxy/gravity_angles.json"))
    cos_theta = {int(k): v["cos_theta"] for k, v in gj["angles"].items()}
    rom = PlateROM(0.08)
    print(f"mesh: {rom.nx}x{rom.nz} nodes, {rom.ndof} DOFs")
    rom.solve(Q_AREA * cos_theta[10])
    sg = -rom.surface()
    ref = load_w(D08, 10)
    c = float(sg.ravel() @ ref.ravel() / np.linalg.norm(sg) / np.linalg.norm(ref))
    alpha = float(sg.ravel() @ ref.ravel() / (sg.ravel() @ sg.ravel()))
    p2 = alpha * sg
    rl2 = float(np.linalg.norm(p2 - ref) / np.linalg.norm(ref))
    print(f"[plate m08@10] raw cos={c:.4f} predPV={1000*(sg.max()-sg.min()):.2f}mm ansysPV={1000*(ref.max()-ref.min()):.2f}mm")
    print(f"[plate m08@10] alpha={alpha:.3f} cos={c:.4f} relL2={rl2:.4f}")
