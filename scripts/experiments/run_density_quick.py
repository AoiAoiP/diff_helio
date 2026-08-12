#!/usr/bin/env python3
"""Quick density scan: North-only, 50 iter, all 4 layouts.

NOTE (2026-08-10 cleanup): 一次性实验脚本，仅供溯源。ROOT 硬编码指向已删除的
worktree 路径，直接运行会报错；如需复跑请修正 ROOT 并确认数据目录存在。"""
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path("L:/Code/bezier_opt_desktop/.claude/worktrees/add_prior_art_citations")
os.chdir(ROOT)

LAYOUTS = [
    ("5x3", 5, 3, 15, "data_proxy_density/5x3_margin05_fine", "data/init_comp_5x3/"),
    ("7x5", 7, 5, 35, "data_proxy_density/7x5_margin05_fine", "data/init_comp_7x5/"),
    ("9x7", 9, 7, 63, "data_proxy_density/9x7_margin05_fine", "data/init_comp_9x7/"),
    ("11x9", 11, 9, 99, "data_proxy_density/11x9_margin05_fine", "data/init_comp_11x9/"),
]

for name, nx, nz, nb, data_path, init_dir in LAYOUTS:
    cfg = {
        "sun_train_file": "data/110_sundir_paper.txt",
        "sun_validation_file": "data/110_sundir_paper.txt",
        "ellipse_file": "data/ellipse_north_300m.txt",
        "receiver_radius": 10.0, "receiver_height": 20.0,
        "pixel_width": 157, "pixel_height": 50,
        "heliostat_width": 12.84, "heliostat_length": 9.45,
        "grid_size": 32, "glass_depth": 0.004,
        "refractive_index": 1.523, "slope_error": 0.001,
        "reflectivity": 0.88, "sun_type": "buie",
        "dni": 1000.0, "csr": 0.01,
        "sun_sigma": 0.00251, "sun_theta_max": 0.00465,
        "iterations": 50, "learning_rate": 0.0004,
        "min_learning_rate": 0.0004,
        "beta1": 0.9, "beta2": 0.999, "adam_epsilon": 1e-08,
        "patience": 10, "energy_target": 1.0,
        "use_bolt": 1, "use_bspline": 0,
        "num_bolts": nb, "num_bolts_x": nx, "num_bolts_z": nz,
        "bolt_margin": 0.05,
        "bolt_init_file": "auto", "bolt_init_dir": init_dir,
        "influence_data_path": data_path,
        "output_dir": f"results_density/{name}_quick",
        "samplePoolPow": 26,
        "gravity_normal_coupling": 1,
        "max_bolt_stroke": 0.06,
        "lambda_energy": 0.5,
        "stroke_regularization": 0.001,
    }
    cfg_path = f"configs/density_scan/{name}_quick.json"
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"\n=== {name} (nb={nb}) ===")
    result = subprocess.run(
        ["./build/src/Release/bezier_opt.exe", cfg_path],
        capture_output=True, text=True, timeout=900
    )
    # Print last few lines
    lines = result.stdout.strip().split('\n')
    for line in lines[-15:]:
        print(line)
    if result.stderr:
        print("STDERR:", result.stderr[:500])

    # Read summary
    summary_path = f"results_density/{name}_quick/optimization_summary.csv"
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            print(f.read())

print("\n=== ALL DONE ===")
