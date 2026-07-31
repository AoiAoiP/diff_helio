# Track B v3: grillage ROM with correct topology — global saddle-point solve.
# x-strips at z in {bolt rows + bay centers}, z-strips at x in {bolt cols + bay
# centers}. Only strips ON bolt lines get direct supports (w=0 at bolts);
# bay-center strips float and are carried by crossing strips via Lagrange
# multipliers enforcing w_x(crossing) == w_z(crossing) at all non-bolt crossings.
# Torsion neglected. UDL split q/2 per family (tributary widths).
import numpy as np
from scipy import sparse
from scipy.sparse import linalg as spla

G = 32
W, L = 12.84, 9.45
THK, E_MOD, NU, RHO = 0.004, 7.0e10, 0.22, 2500.0
D_PLATE = E_MOD * THK**3 / (12.0 * (1.0 - NU**2))
Q_AREA = RHO * 9.81 * THK
ANG20 = [10,14,18,22,26,30,34,38,42,46,50,54,58,62,66,70,73,76,78,80]


def beam_K(nodes):
    """Euler-Bernoulli stiffness on given node positions. Returns (K csr, ndof)."""
    n = len(nodes); ndof = 2 * n
    K = sparse.lil_matrix((ndof, ndof))
    for e in range(n - 1):
        le = nodes[e + 1] - nodes[e]
        k = D_PLATE / le**3 * np.array([
            [12, 6*le, -12, 6*le],
            [6*le, 4*le*le, -6*le, 2*le*le],
            [-12, -6*le, 12, -6*le],
            [6*le, 2*le*le, -6*le, 4*le*le]])
        d = [2*e, 2*e+1, 2*e+2, 2*e+3]
        for a in range(4):
            for b in range(4):
                K[d[a], d[b]] += k[a, b]
    return K.tocsr(), ndof


def beam_f_udl(nodes, q):
    """Consistent nodal load for UDL q (down-positive)."""
    n = len(nodes); f = np.zeros(2 * n)
    for e in range(n - 1):
        le = nodes[e + 1] - nodes[e]
        fe = q * le / 12.0 * np.array([6, le, 6, -le])
        f[2*e] += fe[0]; f[2*e+1] += fe[1]; f[2*e+2] += fe[2]; f[2*e+3] += fe[3]
    return f


def beam_eval(nodes, d, q, D, s):
    """Deflection at s: Hermite + exact clamped-element UDL particular."""
    s = float(np.clip(s, nodes[0], nodes[-1]))
    e = int(np.clip(np.searchsorted(nodes, s) - 1, 0, len(nodes) - 2))
    x0, x1 = nodes[e], nodes[e + 1]
    le = x1 - x0; t = (s - x0) / le
    w0, th0, w1, th1 = d[2*e], d[2*e+1], d[2*e+2], d[2*e+3]
    w_h = ((1 - 3*t*t + 2*t**3) * w0 + le * (t - 2*t*t + t**3) * th0
           + (3*t*t - 2*t**3) * w1 + le * (-t*t + t**3) * th1)
    sl = s - x0
    return w_h + q * sl * sl * (le - sl) ** 2 / (24.0 * D)


class Grillage:
    def __init__(self, margin):
        self.margin = margin
        self.bx = (margin + (1 - 2*margin) * np.arange(7) / 6.0) * W   # bolt cols
        self.bz = (margin + (1 - 2*margin) * np.arange(5) / 4.0) * L   # bolt rows
        self.xstrip_z = np.sort(np.concatenate([self.bz, (self.bz[:-1] + self.bz[1:]) / 2]))
        self.zstrip_x = np.sort(np.concatenate([self.bx, (self.bx[:-1] + self.bx[1:]) / 2]))
        self.onbolt_z = np.isin(self.xstrip_z, self.bz)
        self.onbolt_x = np.isin(self.zstrip_x, self.bx)

        def trib(pos, S):
            p = np.concatenate([[0.0], pos, [S]]); mid = (p[:-1] + p[1:]) / 2
            return mid[1:] - mid[:-1]
        self.xtrib = trib(self.xstrip_z, L)
        self.ztrib = trib(self.zstrip_x, W)

        # crossings: all pairs except bolt-coincident ones
        self.cross = [(iz, ix) for iz in range(len(self.xstrip_z))
                      for ix in range(len(self.zstrip_x))
                      if not (self.onbolt_z[iz] and self.onbolt_x[ix])]
        self.nc = len(self.cross)
        self._assemble()

    def _assemble(self):
        # per-strip K/f, global DOF offsets
        self.offsets = []
        ndof_total = 0
        self.strip_data = []   # (nodes, is_x, line_index)
        fams = [(True, self.xstrip_z, self.zstrip_x, self.bx, self.onbolt_z),
                (False, self.zstrip_x, self.xstrip_z, self.bz, self.onbolt_x)]
        for is_x, lines, cross_pos, bolts, onbolt in fams:
            for li, line in enumerate(lines):
                pts = set(cross_pos) | set(bolts) | {0.0, (W if is_x else L)}
                nodes = np.sort(np.array(list(pts)))
                K, ndof = beam_K(nodes)
                sup_dofs = []
                if onbolt[li]:
                    sup_dofs = [2 * int(np.searchsorted(nodes, b)) for b in bolts]
                self.strip_data.append((nodes, is_x, li))
                self.offsets.append(ndof_total)
                ndof_total += ndof
        # build global K, support elimination list, constraint matrix C
        self.Kglob = sparse.block_diag([beam_K(sd[0])[0] for sd in self.strip_data]).tocsr()
        # constraints: for each crossing (iz, ix): w_xstrip_iz(xstrip x= zstrip_x[ix]) - w_zstrip_ix(z=xstrip_z[iz]) = 0
        C = sparse.lil_matrix((self.nc, ndof_total))
        x_fam = [i for i, sd in enumerate(self.strip_data) if sd[1]]
        z_fam = [i for i, sd in enumerate(self.strip_data) if not sd[1]]
        for k, (iz, ix) in enumerate(self.cross):
            si_x = x_fam[iz]; si_z = z_fam[ix]
            nx = self.strip_data[si_x][0]; nz = self.strip_data[si_z][0]
            dof_x = self.offsets[si_x] + 2 * int(np.searchsorted(nx, self.zstrip_x[ix]))
            dof_z = self.offsets[si_z] + 2 * int(np.searchsorted(nz, self.xstrip_z[iz]))
            C[k, dof_x] = 1.0; C[k, dof_z] = -1.0
        self.C = C.tocsr()
        # support DOFs (w=0 at bolts, only strips on bolt lines)
        self.sup_dofs = []
        for si, (nodes, is_x, li) in enumerate(self.strip_data):
            bolts = self.bx if is_x else self.bz
            onb = self.onbolt_z[li] if is_x else self.onbolt_x[li]
            if onb:
                for b in bolts:
                    self.sup_dofs.append(self.offsets[si] + 2 * int(np.searchsorted(nodes, b)))
        self.sup_dofs = np.array(self.sup_dofs)
        self.ndof = ndof_total

    def solve(self, q_area):
        f = np.zeros(self.ndof)
        for si, (nodes, is_x, li) in enumerate(self.strip_data):
            q = q_area / 2 * (self.xtrib[li] if is_x else self.ztrib[li])
            f[self.offsets[si]:self.offsets[si] + 2 * len(nodes)] = beam_f_udl(nodes, q)
        # saddle-point system [K C^T; C 0] with support DOFs eliminated
        free = np.array([i for i in range(self.ndof) if i not in self.sup_dofs])
        Kff = self.Kglob[free][:, free]
        Cf = self.C[:, free]
        S = sparse.bmat([[Kff, Cf.T], [Cf, None]], format="csc")
        rhs = np.concatenate([f[free], np.zeros(self.nc)])
        sol = spla.spsolve(S, rhs)
        self.d = np.zeros(self.ndof)
        self.d[free] = sol[:len(free)]
        self.lam = sol[len(free):]
        self.q = q_area
        return self.d

    def _strip_w(self, si, s):
        nodes, is_x, li = self.strip_data[si]
        q = self.q / 2 * (self.xtrib[li] if is_x else self.ztrib[li])
        d = self.d[self.offsets[si]:self.offsets[si] + 2 * len(nodes)]
        return beam_eval(nodes, d, q, D_PLATE, s)

    def surface(self):
        gx = (np.arange(G) + 0.5) / G * W
        gz = (np.arange(G) + 0.5) / G * L
        nx_, nz_ = len(self.xstrip_z), len(self.zstrip_x)
        x_fam = [i for i, sd in enumerate(self.strip_data) if sd[1]]
        z_fam = [i for i, sd in enumerate(self.strip_data) if not sd[1]]
        zpos, xpos = self.xstrip_z, self.zstrip_x
        wmat = np.zeros((nx_, nz_))
        for iz in range(nx_):
            for ix in range(nz_):
                wmat[iz, ix] = self._strip_w(x_fam[iz], xpos[ix])
        out = np.zeros((G, G))
        for j, z in enumerate(gz):
            iz = int(np.clip(np.searchsorted(zpos, z) - 1, 0, nx_ - 2))
            tz = np.clip((z - zpos[iz]) / (zpos[iz+1] - zpos[iz]), 0, 1)
            for i, x in enumerate(gx):
                ix = int(np.clip(np.searchsorted(xpos, x) - 1, 0, nz_ - 2))
                tx = np.clip((x - xpos[ix]) / (xpos[ix+1] - xpos[ix]), 0, 1)
                X = (1-tz) * self._strip_w(x_fam[iz], x) + tz * self._strip_w(x_fam[iz+1], x)
                Z = (1-tx) * self._strip_w(z_fam[ix], z) + tx * self._strip_w(z_fam[ix+1], z)
                C = ((1-tz)*((1-tx)*wmat[iz,ix] + tx*wmat[iz,ix+1])
                     + tz*((1-tx)*wmat[iz+1,ix] + tx*wmat[iz+1,ix+1]))
                out[j, i] = X + Z - C
        return out


def load_w(d, a):
    return np.fromfile(f"{d}/gravity_{a}deg.bin", dtype=np.float32).reshape(3, G, G)[0]

D04 = "0730_margin_2/data_proxy_margin/7x5_margin04"
D06 = "margin06_data_2026-07-30/data_proxy_margin/7x5_margin06"
D08 = "data_proxy"

if __name__ == "__main__":
    # sanity: single bolt-line strip (supported) vs analytic continuous beam
    nodes = np.sort(np.array([0.0, 2.0] + [0.5, 1.0, 1.5] + [0.25, 0.75, 1.25, 1.75]))
    K, ndof = beam_K(nodes)
    sup = [2 * int(np.searchsorted(nodes, s)) for s in [0.5, 1.0, 1.5]]
    free = np.array([i for i in range(ndof) if i not in sup])
    f = beam_f_udl(nodes, 1.0)
    d = np.zeros(ndof)
    d[free] = spla.spsolve(K[free][:, free].tocsc(), f[free])
    import rom_gravity_model as rom
    wref, _ = rom.continuous_beam([0.5, 1.0, 1.5], 2.0)
    xs = np.linspace(0, 2, 9)
    got = np.array([beam_eval(nodes, d, 1.0, 1.0, x) for x in xs])   # D=1 to match analytic
    exp = wref(xs)
    # FEM uses D_PLATE; scale: redo with q scaled by 1/D_PLATE instead
    print("[sanity] strip FEM(UDL, D=1 via eval) vs analytic: ratio =",
          np.array2string(got / np.where(np.abs(exp) > 1e-12, exp, 1.0), precision=4))

    import json
    gj = json.load(open("data_proxy/gravity_angles.json"))
    cos_theta = {int(k): v["cos_theta"] for k, v in gj["angles"].items()}
    gr = Grillage(0.08)
    gr.solve(Q_AREA * cos_theta[10])
    sg = -gr.surface()   # ANSYS down = negative
    ref = load_w(D08, 10)
    c = float(sg.ravel() @ ref.ravel() / np.linalg.norm(sg) / np.linalg.norm(ref))
    alpha = float(sg.ravel() @ ref.ravel() / (sg.ravel() @ sg.ravel()))
    p2 = alpha * sg
    rl2 = float(np.linalg.norm(p2 - ref) / np.linalg.norm(ref))
    c2 = float(p2.ravel() @ ref.ravel() / np.linalg.norm(p2) / np.linalg.norm(ref))
    print(f"[grillage m08@10] raw cos={c:.4f} predPV={1000*(sg.max()-sg.min()):.2f}mm ansysPV={1000*(ref.max()-ref.min()):.2f}mm")
    print(f"[grillage m08@10] alpha={alpha:.3f} cos={c2:.4f} relL2={rl2:.4f}")
