# Track B4 / G5: end-to-end margin optimization with the ROM field provider.
# Derivative-free 1D search over bolt_margin: for each candidate margin,
# (1) generate ROM gravity bins (PlateVK, warm-started angle chain),
# (2) write a renderer config (bolt_margin + influence_data_path),
# (3) run bezier_opt bolt-height optimization (300m NEWS @110dir template),
# (4) parse per-mirror S95 from optimization_summary.csv.
# Warm start: bolt heights chained from the previous margin's North BEST file.
#
#   smoke: python scripts/rom_margin_optimize.py --margins 0.08 --iters 20
#   full : python scripts/rom_margin_optimize.py --margins 0.08,0.06,0.05,0.04,0.03
import os, sys, json, csv, argparse, subprocess, time, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "build", "src", "Release", "bezier_opt.exe")
PROVIDER = os.path.join(ROOT, "scripts", "rom_field_provider.py")
SUMMARY = "optimization_summary.csv"


def run(cmd, log_path):
    with open(log_path, "w") as lf:
        p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="configs/_fw_tanh_a0_110.json")
    ap.add_argument("--margins", required=True,
                    help="comma list, evaluated in the given order")
    ap.add_argument("--iters", type=int, default=None,
                    help="override template iterations")
    ap.add_argument("--bins-root", default="data_rom")
    ap.add_argument("--out-root", default="results_rom")
    ap.add_argument("--alpha-table", default="analysis/rom_b2_alpha_table.csv")
    ap.add_argument("--reuse-bins", action="store_true",
                    help="skip provider if gravity_10deg.bin already exists")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    margins = [float(x) for x in args.margins.split(",")]
    tpl = json.load(open(os.path.join(ROOT, args.template)))
    os.makedirs(os.path.join(ROOT, args.bins_root), exist_ok=True)
    os.makedirs(os.path.join(ROOT, args.out_root), exist_ok=True)
    rows = []
    warm_file = None

    for m in margins:
        mtag = f"m{int(round(m*100)):02d}"
        bins_dir = os.path.join(args.bins_root, mtag)
        out_dir = os.path.join(args.out_root, (args.tag + "_" if args.tag else "") + mtag)
        t0 = time.time()
        # (1) bins
        if not (args.reuse_bins and os.path.exists(os.path.join(ROOT, bins_dir, "gravity_10deg.bin"))):
            rc = run([sys.executable, PROVIDER, "--margin", str(m),
                      "--out", bins_dir, "--alpha-table", args.alpha_table],
                     os.path.join(ROOT, bins_dir + "_provider.log"))
            if rc != 0:
                print(f"[{mtag}] provider FAILED rc={rc}, skipping"); continue
        # (2) config
        cfg = dict(tpl)
        cfg["bolt_margin"] = m
        cfg["influence_data_path"] = bins_dir.replace(os.sep, "/")
        cfg["output_dir"] = out_dir.replace(os.sep, "/")
        if args.iters is not None:
            cfg["iterations"] = args.iters
        os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
        cfg_path = os.path.join(ROOT, out_dir, "config.json")
        json.dump(cfg, open(cfg_path, "w"), indent=2)
        # (3) renderer run (warm start via --bolt-file)
        cmd = [EXE, "--config", cfg_path]
        if warm_file:
            cmd += ["--bolt-file", warm_file]
        rc = run(cmd, os.path.join(ROOT, out_dir, "run.log"))
        if rc != 0:
            print(f"[{mtag}] renderer FAILED rc={rc}, skipping"); continue
        # (4) parse
        with open(os.path.join(ROOT, out_dir, SUMMARY)) as fh:
            for row in csv.DictReader(fh):
                rows.append({"margin": m, "mirror": row["Position"],
                             "init_s95": float(row["Init_S95(m2)"]),
                             "best_s95": float(row["Best_S95(m2)"]),
                             "reduction_pct": float(row["Reduction(%)"])})
        cand = os.path.join(ROOT, out_dir, "North_300m_BEST_bolts.bin")
        if os.path.exists(cand):
            warm_file = cand
        print(f"[{mtag}] done in {time.time()-t0:.0f}s -> {out_dir}", flush=True)

    out_csv = os.path.join(ROOT, "analysis",
                           "rom_g5_margin_curve" + ("_" + args.tag if args.tag else "") + ".csv")
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["margin", "mirror", "init_s95", "best_s95", "reduction_pct"])
        w.writeheader(); w.writerows(rows)
    print(f"\n=== G5 margin curve -> {out_csv}")
    mirrors = sorted(set(r["mirror"] for r in rows))
    hdr = "margin | " + " | ".join(f"{m:>8s}" for m in mirrors) + " | mean"
    print(hdr); print("-" * len(hdr))
    for m in margins:
        vals = [r["best_s95"] for r in rows if r["margin"] == m]
        if not vals:
            continue
        per = {r["mirror"]: r["best_s95"] for r in rows if r["margin"] == m}
        print(f"{m:.2f}   | " + " | ".join(f"{per.get(mi, float('nan')):8.3f}" for mi in mirrors)
              + f" | {sum(vals)/len(vals):.3f}")


if __name__ == "__main__":
    main()
