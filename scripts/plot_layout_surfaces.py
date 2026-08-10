# Phase 5.4/5.3 visualization: 2D surface maps + density curve.
# Row 1: bolt layout scatter;  Row 2: gravity w field @10deg (mm);
# Row 3: slope magnitude @10deg (mrad). Truth bins where available.
#
#   python scripts/plot_layout_surfaces.py
import os, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_utils as lu

W, L = 12.84, 9.45
G = 32
OUT = "analysis/figures"
ANG = 10

# (label, layout_json, bins_dir, provenance, s95_text)
PANELS = [
    ("Uniform 7x5 (N=35)\nbaseline", "configs/bolt_layouts/density/7x5_margin05.json",
     "data_proxy_margin/7x5_margin05_fine", "ANSYS truth", "S95=281.2 (truth)"),
    ("Uniform 9x7 (N=63)", "configs/bolt_layouts/density/9x7_margin05.json",
     "data_proxy_truth/9x7_margin05", "ANSYS truth", "S95=247.9 (truth, 100it)"),
    ("Uniform 9x8 (N=72)", "configs/bolt_layouts/free/uniform_9x8_m05.json",
     "data_rom_sparse/g4_uniform72", "ROM", "S95=268.6 (ROM)"),
    ("Dense 11x9 (N=99)", "configs/bolt_layouts/density/11x9_margin05.json",
     "data_proxy_truth/11x9_margin05", "ANSYS truth", "S95=271.5 (truth)"),
    ("Sparse v4 (N=91)\nedge-protected", "configs/bolt_layouts/free/v4_best_91.json",
     "data_proxy_truth/v4_best_91", "ANSYS truth", "S95=259.6 (truth)"),
    ("Sparse v3 (N=74)\ngreedy (edge gap!)", "configs/bolt_layouts/free/archive_v3/sparse_v3_round05.json",
     "data_proxy_truth/sparse74", "ANSYS truth", "S95=462.8 (truth)"),
]


def load_w(d, a=ANG):
    return np.fromfile(f"{d}/gravity_{a}deg.bin", dtype=np.float32).reshape(3, G, G)


def main():
    os.makedirs(OUT, exist_ok=True)
    panels = []
    for label, lay_path, bins_dir, prov, s95 in PANELS:
        if not os.path.exists(os.path.join(bins_dir, f"gravity_{ANG}deg.bin")):
            print(f"[skip] {label}: bins not ready ({bins_dir})")
            continue
        lay = lu.load_layout(lay_path)
        bx, bz = lu.bolt_positions(lay)
        b3 = load_w(bins_dir)
        w = b3[0].astype(np.float64) * 1000.0                      # mm
        slp = np.sqrt(b3[1] ** 2 + b3[2] ** 2).astype(np.float64) * 1000.0  # mrad
        panels.append((label, bx, bz, w, slp, prov, s95))
    if not panels:
        print("no panels ready"); return

    n = len(panels)
    fig, axes = plt.subplots(3, n, figsize=(3.2 * n, 9.2),
                             gridspec_kw={"height_ratios": [1, 1, 1]})
    if n == 1:
        axes = axes.reshape(3, 1)
    xg = (np.arange(G) + 0.5) / G * W - W / 2
    zg = (np.arange(G) + 0.5) / G * L - L / 2
    for k, (label, bx, bz, w, slp, prov, s95) in enumerate(panels):
        # row 0: layout
        ax = axes[0, k]
        ax.set_title(label + f"\n[{prov}]", fontsize=9)
        ax.scatter(bx, bz, s=14, c="tab:blue", zorder=3)
        ax.set_xlim(-W / 2, W / 2); ax.set_ylim(-L / 2, L / 2)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_linewidth(1.5)
        # row 1: w field
        ax = axes[1, k]
        im = ax.imshow(w, origin="lower", extent=[-W/2, W/2, -L/2, L/2],
                       cmap="RdBu_r", vmin=-np.abs(w).max(), vmax=np.abs(w).max())
        ax.scatter(bx, bz, s=4, c="k", zorder=3)
        pv = np.ptp(w)
        ax.set_title(f"w @{ANG}deg  PV={pv:.1f} mm", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, label="mm")
        # row 2: slope magnitude
        ax = axes[2, k]
        im = ax.imshow(slp, origin="lower", extent=[-W/2, W/2, -L/2, L/2],
                       cmap="viridis", vmin=0, vmax=slp.max())
        ax.scatter(bx, bz, s=4, c="w", zorder=3)
        srms = float(np.sqrt(np.mean(slp ** 2)))
        ax.set_title(f"|slope| @{ANG}deg  RMS={srms:.2f} mrad", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, label="mrad")
        if s95:
            axes[1, k].set_xlabel(s95, fontsize=9)
    fig.suptitle(f"Gravity deformation fields @{ANG}deg (zero-bolt) + bolt layouts — 300m NEWS @110dir S95",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(OUT, "fig54_layout_surfaces.png")
    fig.savefig(out, dpi=150)
    print("saved", out)

    # ---- density curve ----
    pts_truth = [  # (N, S95, label)
        (35, 281.2, "7x5 m05"),
        (99, 271.53, "11x9 m05"),
        (91, 259.55, "sparse v4"),
        (74, 462.76, "sparse v3 (edge gap)"),
    ]
    p63 = "results_truth/9x7_m05/optimization_summary.csv"
    if os.path.exists(p63):
        import csv
        with open(p63) as f:
            tot = sum(float(r["Best_S95(m2)"]) for r in csv.DictReader(f))
        pts_truth.insert(1, (63, tot, "9x7 m05"))
    pts_rom = [
        (35, 291.3, "7x5 m05"),
        (72, 268.55, "9x8 m05"),
        (99, 271.02, "11x9 m05"),
        (91, 266.41, "sparse v4"),
        (74, 284.53, "sparse v3"),
    ]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ut = [(n, s) for n, s, l in pts_truth if "sparse" not in l]
    ax.plot([n for n, _ in ut], [s for _, s in ut], "o-", c="tab:blue",
            label="uniform grid (ANSYS truth)", zorder=3)
    ur = [(n, s) for n, s, l in pts_rom if "sparse" not in l]
    ax.plot([n for n, _ in ur], [s for _, s in ur], "s--", c="tab:cyan",
            label="uniform grid (ROM)", zorder=3)
    sp = [(n, s, l) for n, s, l in pts_truth if "sparse" in l]
    for n, s, l in sp:
        ax.plot([n], [s], "D", ms=9, zorder=4,
                c="tab:green" if "v4" in l else "tab:red", label=f"{l} (truth)")
    spr = [(n, s, l) for n, s, l in pts_rom if "sparse" in l]
    for n, s, l in spr:
        ax.plot([n], [s], "D", ms=7, mfc="none", zorder=4,
                c="tab:green" if "v4" in l else "tab:red", label=f"{l} (ROM)")
    ax.set_xlabel("bolt count N"); ax.set_ylabel("S95 total, 4 mirrors (m$^2$)")
    ax.set_title("Bolt density / sparsity at margin=0.05 (300m NEWS @110dir)")
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout()
    out2 = os.path.join(OUT, "fig54_density_curve.png")
    fig.savefig(out2, dpi=150)
    print("saved", out2)


if __name__ == "__main__":
    main()
