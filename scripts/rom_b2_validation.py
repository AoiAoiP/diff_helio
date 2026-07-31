# Track B2: full validation sweep of the von Karman plate ROM against the
# script-model ANSYS gravity bins (m02/m04 train, m06 hold-out).
# For each (margin, angle): VK solve (warm-started across angles), linear-ROM
# fallback on non-convergence; reports cos/alpha/relL2 vs the bins.
# Output: analysis/rom_b2_sweep.csv (incremental).
import os, sys, json, time
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rom_plate_fem as rom

DIRS = {
    0.02: ("0730_margin_2/data_proxy_margin/7x5_margin02", [10, 30, 58, 80]),
    0.04: ("0730_margin_2/data_proxy_margin/7x5_margin04", rom.ANG20),
    0.06: ("margin06_data_2026-07-30/data_proxy_margin/7x5_margin06", rom.ANG20),
}
OUT = "analysis/rom_b2_sweep.csv"


def cosx(a, b):
    return float(a.ravel() @ b.ravel() / np.linalg.norm(a) / np.linalg.norm(b))


def main():
    gj = json.load(open("data_proxy/gravity_angles.json"))
    CT = {int(k): v["cos_theta"] for k, v in gj["angles"].items()}
    new = not os.path.exists(OUT)
    with open(OUT, "a") as fh:
        if new:
            fh.write("margin,angle,iters,converged,fallback,cos_vk,alpha_vk,"
                     "relL2_vk,cos_vk_blur,cos_lin,alpha_lin,pv_fem,pv_ref,seconds\n")
        for margin, (d, angles) in DIRS.items():
            r = rom.PlateVK(margin, n_bay=4, n_over=2, patch_hw=0.3)
            d_b = None  # warm-start state
            for a in angles:
                t0 = time.time()
                ref = np.fromfile(f"{d}/gravity_{a}deg.bin", dtype=np.float32
                                  ).reshape(3, rom.G, rom.G)[0]
                q_n = rom.Q_AREA * CT[a]
                q_i = rom.Q_AREA * float(np.sin(np.radians(a)))
                # linear reference
                r.solve(q_n)
                sg_lin = -r.surface()
                cos_lin = cosx(sg_lin, ref)
                al_lin = float(sg_lin.ravel() @ ref.ravel() / (sg_lin.ravel() @ sg_lin.ravel()))
                # VK solve with warm start; retry from linear on failure
                it, ok = r.solve_vk(q_n, q_i, d_b0=d_b)
                fallback = 0
                if not ok:
                    it2, ok2 = r.solve_vk(q_n, q_i, d_b0=None, max_iter=120)
                    it += it2
                    if not ok2:
                        fallback = 1
                        r.d = np.zeros(r.ndof)
                        r.d[r.free] = r.solve_lu(r.f[r.free] * q_n)
                sg = -r.surface()
                al = float(sg.ravel() @ ref.ravel() / (sg.ravel() @ sg.ravel()))
                p = al * sg
                rl2 = float(np.linalg.norm(p - ref) / np.linalg.norm(ref))
                cos_b = cosx(ndimage.gaussian_filter(sg, 0.75),
                             ndimage.gaussian_filter(ref, 0.75))
                if not fallback:
                    d_b = r.d.copy()
                row = (f"{margin},{a},{it},{int(ok and not fallback)},{fallback},"
                       f"{cosx(sg, ref):.4f},{al:.4f},{rl2:.4f},{cos_b:.4f},"
                       f"{cos_lin:.4f},{al_lin:.4f},"
                       f"{1e3*(sg.max()-sg.min()):.3f},{1e3*(ref.max()-ref.min()):.3f},"
                       f"{time.time()-t0:.1f}")
                fh.write(row + "\n"); fh.flush()
                print(f"m{int(margin*100):02d}@{a}: {row.split(',', 2)[2]}", flush=True)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
