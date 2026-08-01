# Track B2 fine-substep recalibration: VK ROM vs fine-substep ANSYS gravity bins.
# Same logic as rom_b2_validation.py but using _fine directories (--nsubst 50,500,50).
# Calibration: m02+m04 (train), m06 (hold-out).
# Alpha table = average(m02_alpha, m04_alpha) at each angle; m04-only where m02 absent.
#
# Output: analysis/rom_b2_sweep_fine.csv, analysis/rom_b2_alpha_table_fine.csv
import os, sys, json, time
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rom_plate_fem as rom

# Fine-substep directories on desktop
DIRS = {
    0.02: ("data_proxy_margin/7x5_margin02_fine", rom.ANG20),
    0.04: ("data_proxy_margin/7x5_margin04_fine", rom.ANG20),
    0.06: ("data_proxy_margin/7x5_margin06_fine", rom.ANG20),
}
OUT_SWEEP = "analysis/rom_b2_sweep_fine.csv"
OUT_ALPHA = "analysis/rom_b2_alpha_table_fine.csv"


def cosx(a, b):
    return float(a.ravel() @ b.ravel() / np.linalg.norm(a) / np.linalg.norm(b))


def main():
    gj = json.load(open("data_proxy/gravity_angles.json"))
    CT = {int(k): v["cos_theta"] for k, v in gj["angles"].items()}
    new = not os.path.exists(OUT_SWEEP)
    with open(OUT_SWEEP, "a") as fh:
        if new:
            fh.write("margin,angle,iters,converged,fallback,cos_vk,alpha_vk,"
                     "relL2_vk,cos_vk_blur,cos_lin,alpha_lin,pv_fem,pv_ref,seconds\n")
        for margin, (d, angles) in DIRS.items():
            if not os.path.isdir(d):
                print(f"SKIP margin={margin}: dir {d} not found")
                continue
            r = rom.PlateVK(margin, n_bay=4, n_over=2, patch_hw=0.3)
            d_b = None  # warm-start state
            for a in angles:
                bin_path = f"{d}/gravity_{a}deg.bin"
                if not os.path.exists(bin_path):
                    print(f"  SKIP m{int(margin*100):02d}@{a}deg: bin missing")
                    continue
                t0 = time.time()
                ref = np.fromfile(bin_path, dtype=np.float32
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
                status = "FALLBACK" if fallback else ("NO_CONV" if not ok else "OK")
                print(f"m{int(margin*100):02d}@{a:3d}deg {status} "
                      f"cos={cosx(sg,ref):.4f} alpha={al:+.4f} it={it} "
                      f"pv_fem={1e3*(sg.max()-sg.min()):.2f} pv_ref={1e3*(ref.max()-ref.min()):.2f}",
                      flush=True)
    print("sweep done ->", OUT_SWEEP)

    # --- fit alpha table from m02+m04 (train) ---
    print("\n=== Fitting alpha table (m02+m04 average) ===")
    sweep = {}
    with open(OUT_SWEEP) as fh:
        header = fh.readline().strip().split(",")
        for line in fh:
            parts = line.strip().split(",")
            margin = float(parts[0])
            angle = int(parts[1])
            if parts[4] == "1":  # skip fallback rows
                continue
            alpha = float(parts[6])
            sweep.setdefault(angle, {})[margin] = alpha

    alpha_table = {}
    for angle in sorted(sweep.keys()):
        alphas = sweep[angle]
        if 0.02 in alphas and 0.04 in alphas:
            alpha_table[angle] = (alphas[0.02] + alphas[0.04]) / 2.0
        elif 0.04 in alphas:
            alpha_table[angle] = alphas[0.04]
        elif 0.02 in alphas:
            alpha_table[angle] = alphas[0.02]
        else:
            continue

    with open(OUT_ALPHA, "w") as fh:
        fh.write("# Fine-substep recalibrated alpha table (m02+m04 average, m06 hold-out)\n")
        fh.write("# Generated by rom_b2_validation_fine.py\n")
        fh.write("angle,alpha\n")
        for angle in sorted(alpha_table.keys()):
            a = alpha_table[angle]
            fh.write(f"{angle},{a:.4f}\n")
    print("alpha table ->", OUT_ALPHA)

    # --- diagnostic: check all-positive monotonic ---
    angles_sorted = sorted(alpha_table.keys())
    alphas = [alpha_table[a] for a in angles_sorted]
    all_pos = all(a > 0 for a in alphas)
    monotonic = all(alphas[i] >= alphas[i+1] for i in range(len(alphas)-1))
    has_neg = any(a < 0 for a in alphas)
    print(f"\n=== Alpha table diagnostics ===")
    print(f"  All-positive: {all_pos}  Monotonic-decreasing: {monotonic}  Has-negative: {has_neg}")
    if has_neg:
        neg_angles = [a for a in angles_sorted if alpha_table[a] < 0]
        print(f"  NEGATIVE at angles: {neg_angles}")
    print(f"  Range: {min(alphas):.4f} @ {angles_sorted[alphas.index(min(alphas))]}deg "
          f"to {max(alphas):.4f} @ {angles_sorted[alphas.index(max(alphas))]}deg")

    # --- hold-out verification (m06) ---
    print("\n=== Hold-out (m06) transfer ratios ===")
    for angle in angles_sorted:
        if angle in sweep and 0.06 in sweep[angle]:
            alpha_m06 = sweep[angle][0.06]
            alpha_cal = alpha_table.get(angle)
            if alpha_cal and abs(alpha_cal) > 1e-9:
                ratio = alpha_m06 / alpha_cal
                print(f"  {angle:3d}deg  alpha_m06={alpha_m06:+.4f}  "
                      f"alpha_cal={alpha_cal:+.4f}  transfer={ratio:.2f}")


if __name__ == "__main__":
    main()
