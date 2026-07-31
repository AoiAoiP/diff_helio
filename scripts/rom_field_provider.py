# Track B3: ROM field provider — generate renderer-consumable gravity bins
# (20 angles x 3-plane 32x32 float32) for a given bolt layout (v1: margin),
# using the von Karman plate ROM (PlateVK). Influence phi files are copied
# from a reference dir (layout-weak, Track A decision: fixed m08 set).
#
#   python scripts/rom_field_provider.py --margin 0.06 --out data_rom/m06 \
#       --alpha-table analysis/rom_b2_alpha_table.csv
#
# Angle chain is warm-started; VK non-convergence falls back to linear plate.
# Slopes dw/du, dw/dv follow scripts/generate_proxy_model.py conventions
# (gauss sigma=1.0 pre-smooth, central differences, physical dx/dz).
import os, sys, json, shutil, argparse
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rom_plate_fem as rom

ANGLES = rom.ANG20  # [10..80]


def load_alpha_table(path):
    if not path or not os.path.exists(path):
        return None
    ang, al = [], []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("angle"):
                continue
            a, v = line.split(",")[:2]
            ang.append(float(a)); al.append(float(v))
    order = np.argsort(ang)
    return np.array(ang)[order], np.array(al)[order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--phi-dir", default="data_proxy",
                    help="dir to copy influence_phi{,_u,_v}.bin from (fixed m08 set)")
    ap.add_argument("--alpha-table", default="analysis/rom_b2_alpha_table.csv",
                    help="CSV angle,alpha; missing file -> no alpha scaling")
    ap.add_argument("--no-alpha", action="store_true")
    ap.add_argument("--n-bay", type=int, default=4)
    ap.add_argument("--n-over", type=int, default=2)
    ap.add_argument("--patch-hw", type=float, default=0.3)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    alpha_tab = None if args.no_alpha else load_alpha_table(args.alpha_table)
    gj = json.load(open("data_proxy/gravity_angles.json"))
    CT = {int(k): v["cos_theta"] for k, v in gj["angles"].items()}

    r = rom.PlateVK(args.margin, n_bay=args.n_bay, n_over=args.n_over,
                    patch_hw=args.patch_hw)
    print(f"PlateVK margin={args.margin} ndof={r.ndof} ndm={r.ndm} "
          f"alpha_table={'off' if alpha_tab is None else 'on'}")
    dx = rom.W / rom.G; dz = rom.L / rom.G
    meta = {"angles": {}, "grid_size": rom.G, "plate_W_m": rom.W,
            "plate_L_m": rom.L, "format": "float32", "planes": 3,
            "plane_layout": "w, dw/du, dw/dv",
            "source": f"PlateVK(margin={args.margin},n_bay={args.n_bay},"
                      f"n_over={args.n_over},hw={args.patch_hw})"}
    d_b = None
    for a in ANGLES:
        q_n = rom.Q_AREA * CT[a]
        q_i = rom.Q_AREA * float(np.sin(np.radians(a)))
        it, ok = r.solve_vk(q_n, q_i, d_b0=d_b)
        mode = "vk"
        if not ok:
            it2, ok2 = r.solve_vk(q_n, q_i, d_b0=None, max_iter=120)
            it += it2
            if not ok2:
                mode = "linear-fallback"
                r.d = np.zeros(r.ndof)
                r.d[r.free] = r.solve_lu(r.f[r.free] * q_n)
        if mode == "vk":
            d_b = r.d.copy()
        sg = -r.surface()
        al_applied = 1.0
        if alpha_tab is not None:
            al_applied = float(np.interp(a, alpha_tab[0], alpha_tab[1]))
            sg = sg * al_applied
        # slopes: pre-smooth sigma=1.0, central FD, physical units (m/m)
        w_s = ndimage.gaussian_filter(sg, 1.0)
        dw_du, dw_dv = np.gradient(w_s, axis=(1, 0))
        dw_du /= dx; dw_dv /= dz
        packed = np.concatenate([sg.ravel(), dw_du.ravel(), dw_dv.ravel()]
                                ).astype(np.float32)
        packed.tofile(f"{args.out}/gravity_{a}deg.bin")
        srms = float(np.sqrt(np.mean(dw_du**2 + dw_dv**2)))
        meta["angles"][str(a)] = {
            "cos_theta": CT[a], "pv_mm": float(np.ptp(sg) * 1000),
            "min_mm": float(sg.min() * 1000), "max_mm": float(sg.max() * 1000),
            "slope_rms_mrad": srms * 1000, "nan_filled": 0,
            "vk_iters": it, "mode": mode, "alpha_applied": al_applied,
            "source": meta["source"]}
        print(f"  [{a:3d}deg] mode={mode:15s} it={it:3d} alpha={al_applied:.3f} "
              f"PV={np.ptp(sg)*1000:6.2f}mm slopeRMS={srms*1000:.2f}mrad", flush=True)
    with open(f"{args.out}/gravity_angles.json", "w") as fh:
        json.dump(meta, fh, indent=2)
    for f in ["influence_phi.bin", "influence_phi_u.bin", "influence_phi_v.bin",
              "gravity_y.bin"]:
        src = os.path.join(args.phi_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(args.out, f))
        else:
            print(f"  WARNING: {src} missing, not copied")
    print("done ->", args.out)


if __name__ == "__main__":
    main()
