# Final package spot maps: flux maps at the 3 validation sun directions,
# bare (zero bolts) vs optimized (truth-reoptimized bolts), per mirror.
# Uses --dump-flux in bolt mode (full physics per sun direction: gravity bins
# interpolated at that sun's tilt + bolt influence), one mirror per run.
#
#   python scripts/dump_final_spots.py [mtag]     (default m04; mtag=m05 uses
#   configs/_dump_final_m05.json, data/init_final/m05/, results_final_m05/)
import os, sys, json, subprocess, shutil, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from compute_s95_from_flux import compute_s95, PIXEL_AREA, RECEIVER_RADIUS, RECEIVER_HEIGHT

EXE = os.path.join(ROOT, "build", "src", "Release", "bezier_opt.exe")
MIRRORS = ["North", "East", "South", "West"]
MTAG = sys.argv[1] if len(sys.argv) > 1 else "m04"
ELLIPSE = {
    "North": "North 0.0 0.0 -300.0 6.91e-4 7.71e-4 0.003e-4\n",
    "East": "East 300.0 0.0 0.0 6.71e-4 8.21e-4 0.63e-4\n",
    "South": "South 0.0 0.0 300.0 5.83e-4 9.18e-4 0.003e-4\n",
    "West": "West -300.0 0.0 0.0 6.57e-4 8.21e-4 -0.67e-4\n",
}
OUT = os.path.join(ROOT, f"results_final_{MTAG}")
N_SUN = 3


def run(cmd, log_path):
    with open(log_path, "w") as lf:
        return subprocess.run(cmd, cwd=ROOT, stdout=lf,
                              stderr=subprocess.STDOUT).returncode


def main():
    flux_root = os.path.join(OUT, "flux")
    work = os.path.join(OUT, "flux_dump")
    tpl = json.load(open(os.path.join(ROOT, f"configs/_dump_final_{MTAG}.json")))
    for case in ["bare", "opt"]:
        os.makedirs(os.path.join(flux_root, case), exist_ok=True)
    for m in MIRRORS:
        ell = os.path.join(work, f"ellipse_{m}_only.txt")
        os.makedirs(work, exist_ok=True)
        with open(ell, "w") as fh:
            fh.write(ELLIPSE[m])
        for case, bolt in [("bare", "data/init_final/zero35.txt"),
                           ("opt", f"data/init_final/{MTAG}/{m}_300m_bolt_init.txt")]:
            cfg = dict(tpl)
            cfg["ellipse_file"] = os.path.relpath(ell, ROOT).replace(os.sep, "/")
            cfg["output_dir"] = os.path.relpath(work, ROOT).replace(os.sep, "/")
            cfg_path = os.path.join(work, f"_cfg_{m}_{case}.json")
            json.dump(cfg, open(cfg_path, "w"), indent=2)
            t0 = time.time()
            rc = run([EXE, "--dump-flux", "--bolt-file",
                      os.path.join(ROOT, bolt).replace(os.sep, "/"), cfg_path],
                     os.path.join(ROOT, "logs", f"_spot_{m}_{case}.log"))
            moved = 0
            for s in range(N_SUN):
                src = os.path.join(work, f"{m}_300m_sun{s}_flux.npy")
                if os.path.exists(src):
                    shutil.move(src, os.path.join(flux_root, case,
                                                  f"{m}_sun{s}_flux.npy"))
                    moved += 1
            print(f"[{m} {case}] rc={rc} moved={moved} {time.time()-t0:.0f}s",
                  flush=True)

    # ---- figures: per sun, 4 mirrors x (bare | opt) ----
    s95_tbl = {m: {"bare": [], "opt": []} for m in MIRRORS}
    for s in range(N_SUN):
        fig, axes = plt.subplots(4, 2, figsize=(13, 8.5))
        vmax = 0.0
        data = {}
        for i, m in enumerate(MIRRORS):
            for j, case in enumerate(["bare", "opt"]):
                f = np.load(os.path.join(flux_root, case, f"{m}_sun{s}_flux.npy"))
                s95, _ = compute_s95(f)
                s95_tbl[m][case].append(s95)
                data[(i, j)] = (f, s95)
                vmax = max(vmax, f.max())
        for i, m in enumerate(MIRRORS):
            for j, case in enumerate(["bare", "opt"]):
                f, s95 = data[(i, j)]
                ax = axes[i, j]
                im = ax.imshow(f, origin="lower", cmap="hot", vmin=0, vmax=vmax,
                               extent=[0, 360, -RECEIVER_HEIGHT / 2, RECEIVER_HEIGHT / 2],
                               aspect="auto")
                ax.set_title(f"{m} {'bare (zero bolts)' if case == 'bare' else 'optimized ' + MTAG}"
                             f" — S95={s95:.1f} m²", fontsize=10)
                ax.set_xticks([0, 90, 180, 270, 360])
                if i == 3:
                    ax.set_xlabel("receiver azimuth (deg)")
                if j == 0:
                    ax.set_ylabel("height (m)")
        fig.suptitle(f"Spot maps at validation sun #{s} (300m, {MTAG} ANSYS-truth gravity)")
        fig.subplots_adjust(hspace=0.65)
        fig.savefig(os.path.join(OUT, f"fig_spot_sun{s}.png"), dpi=160,
                    bbox_inches="tight")
        plt.close(fig)
        print(f"wrote fig_spot_sun{s}.png", flush=True)
    with open(os.path.join(OUT, "spot_s95_table.csv"), "w") as fh:
        fh.write("mirror,case,sun0_s95_m2,sun1_s95_m2,sun2_s95_m2\n")
        for m in MIRRORS:
            for case in ["bare", "opt"]:
                v = s95_tbl[m][case]
                fh.write(f"{m},{case},{v[0]:.2f},{v[1]:.2f},{v[2]:.2f}\n")
    print("wrote spot_s95_table.csv")


if __name__ == "__main__":
    main()
