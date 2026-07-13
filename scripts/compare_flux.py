#!/usr/bin/env python3
"""
Compare flux maps: ellipse-derived bolts vs. TPS-optimized bolts.

Reads .npy flux files and computes S95, correlation, total energy, etc.
"""
import numpy as np
import json
import os
import argparse

# Receiver geometry (matches pipeline.cpp)
R = 10.0    # cylinder radius (m)
H = 20.0    # cylinder height (m)
PW = 157    # pixel width
PH = 50     # pixel height
PIXEL_AREA = 2 * np.pi * R * H / (PW * PH)  # m²/pixel


def compute_s95(flux, target_frac=0.95):
    """Compute S95 area (m²) from flux map via binary search."""
    total = flux.sum()
    target = target_frac * total
    lo, hi = 0.0, flux.max()
    for _ in range(50):
        mid = (lo + hi) / 2
        if flux[flux >= mid].sum() >= target:
            lo = mid
        else:
            hi = mid
    level = lo
    s95_pixels = (flux >= level).sum()
    return s95_pixels * PIXEL_AREA, level


def center_flux(flux):
    """Roll flux azimuthally so the spot centroid is centered."""
    sum_sin, sum_cos = 0.0, 0.0
    for x in range(PW):
        col_sum = flux[:, x].sum()
        theta = 2 * np.pi * x / PW
        sum_sin += col_sum * np.sin(theta)
        sum_cos += col_sum * np.cos(theta)
    mean_theta = np.arctan2(sum_sin, sum_cos)
    if mean_theta < 0:
        mean_theta += 2 * np.pi
    center_pixel = int(mean_theta / (2 * np.pi) * PW) % PW
    shift = PW // 2 - center_pixel
    rolled = np.roll(flux, shift, axis=1)
    return rolled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ellipse-dir", default="validation_ellipse_vs_opt/flux_ellipse")
    parser.add_argument("--opt-dir", default="validation_ellipse_vs_opt/flux_optimized")
    parser.add_argument("--output-dir", default="validation_ellipse_vs_opt")
    args = parser.parse_args()

    # Read flux files
    ellipse_files = sorted([f for f in os.listdir(args.ellipse_dir) if f.endswith('.npy')])
    opt_files = sorted([f for f in os.listdir(args.opt_dir) if f.endswith('.npy')])

    print(f"Ellipse flux files: {ellipse_files}")
    print(f"Optimized flux files: {opt_files}")

    all_comparisons = []

    for ef, of in zip(ellipse_files, opt_files):
        print(f"\n{'='*70}")
        print(f"Comparing: {ef}")
        print(f"{'='*70}")

        epath = os.path.join(args.ellipse_dir, ef)
        opath = os.path.join(args.opt_dir, of)

        # Load NPY files (custom format from C++ pipeline)
        def read_flux_npy(path):
            with open(path, 'rb') as f:
                magic = f.read(6)
                assert magic == b'\x93NUMPY', f"Bad NPY magic: {magic}"
                ver_major = ord(f.read(1))
                ver_minor = ord(f.read(1))
                header_len_raw = f.read(2)
                header_len = int.from_bytes(header_len_raw, 'little')
                header = f.read(header_len).decode('utf-8')
                # Parse shape from header dict string
                # e.g. "{'descr': '<f4', 'fortran_order': False, 'shape': (50, 157)}"
                import re
                shape_match = re.search(r"'shape':\s*\(([^)]+)\)", header)
                if shape_match:
                    shape = tuple(int(s.strip()) for s in shape_match.group(1).split(','))
                else:
                    shape = (PH, PW)
                data = np.frombuffer(f.read(), dtype='<f4').reshape(shape)
            return data

        flux_e = read_flux_npy(epath)
        flux_o = read_flux_npy(opath)

        print(f"  Shape: {flux_e.shape}")

        # Un-center (our saved files are already centered from main.cpp)
        # Compute raw metrics
        total_e = flux_e.sum()
        total_o = flux_o.sum()
        max_e = flux_e.max()
        max_o = flux_o.max()

        s95_e, lvl_e = compute_s95(flux_e)
        s95_o, lvl_o = compute_s95(flux_o)

        flux_corr = np.corrcoef(flux_e.flatten(), flux_o.flatten())[0, 1]

        print(f"\n  {'Metric':<25s} {'Ellipse':>12s} {'Optimized':>12s} {'Diff':>12s} {'Ratio':>10s}")
        print(f"  {'-'*72}")
        print(f"  {'Total Energy':<25s} {total_e:12.1f} {total_o:12.1f} "
              f"{total_o-total_e:12.1f} {total_o/total_e:10.4f}")
        print(f"  {'Max Flux (W/m2)':<25s} {max_e:12.3f} {max_o:12.3f} "
              f"{max_o-max_e:12.3f} {max_o/max_e:10.4f}")
        print(f"  {'S95 Area (m2)':<25s} {s95_e:12.4f} {s95_o:12.4f} "
              f"{s95_o-s95_e:12.4f} {s95_o/s95_e:10.4f}")
        print(f"  {'S95 Level':<25s} {lvl_e:12.3f} {lvl_o:12.3f} "
              f"{lvl_o-lvl_e:12.3f} {lvl_o/lvl_e:10.4f}")
        print(f"  {'Flux Correlation':<25s} {flux_corr:>12.6f}")

        # Non-zero pixel count
        nz_e = (flux_e > 0).sum()
        nz_o = (flux_o > 0).sum()
        print(f"  {'Non-zero pixels':<25s} {nz_e:12d} {nz_o:12d} {nz_o-nz_e:12d}")

        # S95 pixel count (before area conversion)
        s95px_e = int((flux_e >= lvl_e).sum())
        s95px_o = int((flux_o >= lvl_o).sum())
        print(f"  {'S95 Pixels':<25s} {s95px_e:12d} {s95px_o:12d} {s95px_o-s95px_e:12d}")

        comp = {
            "file": ef,
            "total_energy_ellipse": float(total_e),
            "total_energy_optimized": float(total_o),
            "max_flux_ellipse": float(max_e),
            "max_flux_optimized": float(max_o),
            "s95_ellipse_m2": float(s95_e),
            "s95_optimized_m2": float(s95_o),
            "s95_level_ellipse": float(lvl_e),
            "s95_level_optimized": float(lvl_o),
            "flux_correlation": float(flux_corr),
            "nz_pixels_ellipse": int(nz_e),
            "nz_pixels_optimized": int(nz_o),
        }
        all_comparisons.append(comp)

    # ── Summary ──
    print(f"\n\n{'='*70}")
    print(f"SUMMARY: Average over {len(all_comparisons)} sun directions")
    print(f"{'='*70}")
    for key in ["total_energy_ellipse", "total_energy_optimized",
                "max_flux_ellipse", "max_flux_optimized",
                "s95_ellipse_m2", "s95_optimized_m2",
                "flux_correlation"]:
        vals = [c[key] for c in all_comparisons]
        print(f"  {key}: mean={np.mean(vals):.4f}, std={np.std(vals):.4f}")

    s95_e_avg = np.mean([c["s95_ellipse_m2"] for c in all_comparisons])
    s95_o_avg = np.mean([c["s95_optimized_m2"] for c in all_comparisons])
    print(f"\n  Average S95 ellipse:   {s95_e_avg:.4f} m2")
    print(f"  Average S95 optimized: {s95_o_avg:.4f} m2")
    print(f"  S95 ratio opt/ellipse: {s95_o_avg/s95_e_avg:.4f}")

    # Save
    out_path = os.path.join(args.output_dir, "flux_comparison.json")
    with open(out_path, 'w') as f:
        json.dump({"comparisons": all_comparisons,
                   "summary": {"s95_ellipse_avg": s95_e_avg,
                               "s95_optimized_avg": s95_o_avg,
                               "ratio": s95_o_avg / s95_e_avg}},
                  f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
