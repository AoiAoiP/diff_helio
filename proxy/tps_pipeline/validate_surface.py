#!/usr/bin/env python3
"""
TPS Proxy Pipeline: Surface Validation + Differentiable Optimization.

Validates the TPS-based proxy model against FEA reference data, then
runs gradient-based optimization to fit bolt heights to the FEA surface.

Pipeline:
  1. Load FEA reference (node_dump_585deg_nograv.csv)
  2. Build TPS solver (35 bolts as source points)
  3. Validation A: zero heights → should be flat
  4. Validation B: known bolt strokes → compute proxy, compare vs FEA
  5. Validation C: gradient check (FD vs AD)
  6. Optimization: fit bolt heights to FEA surface via Adam
  7. Visualization: 2D comparison plots
"""

import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from validation_utils import (
    W, L, GS, NB, BX, BZ, X_GRID, Z_GRID, Xg, Zg,
    load_fea_data, load_bolt_strokes, compare_with_fea, tps_kernel,
)

from tps_solver import TPSSolver, gradient_check
from optimizer import AdamOptimizer

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_DIR = os.path.dirname(SCRIPT_DIR)
BOLT_PATH = os.path.join(PROXY_DIR, 'North_300m_STROKE_bolts.txt')
FEA_PATH = os.path.join(PROXY_DIR, 'node_dump_585deg_nograv.csv')
OUT_DIR = SCRIPT_DIR


# ═══════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("TPS Proxy Pipeline: Surface Validation + Optimization")
    print("=" * 64)

    # ── Load FEA reference ──
    print("\n[Loading] FEA reference data...")
    x_fea, z_fea, u_local, _, _, u_grid_fea = load_fea_data(FEA_PATH)
    print(f"  FEA nodes: {len(x_fea)}, grid: {GS}×{GS}")
    print(f"  FEA u_local PV: {np.ptp(u_grid_fea)*1000:.2f} mm")
    print(f"  FEA u_local mean: {np.mean(u_grid_fea)*1000:.4f} mm")

    # ── Build TPS solver ──
    print("\n[Init] Building TPS solver (35 bolts as source points)...")
    solver = TPSSolver(reg=1e-6)
    # Note: reg=1e-6 gives better conditioning than 1e-8 for 35 bolts

    # ── Validation A: Zero heights ──
    print("\n" + "=" * 64)
    print("Validation A: Zero bolt heights")
    print("=" * 64)
    h_zero = np.zeros(NB)
    c0, d0 = solver.solve(h_zero)
    w_zero, dwdx0, dwdz0, nx0, ny0, nz0 = solver.surface_with_normals(c0, d0)

    print(f"  Zero-height surface PV: {np.ptp(w_zero)*1000:.6f} mm (expect ~0)")
    print(f"  Polynomial coeffs: d=[{d0[0]:.6f}, {d0[1]:.6f}, {d0[2]:.6f}]")
    zero_rms = np.sqrt(np.mean((w_zero - u_grid_fea)**2)) * 1000
    print(f"  RMS vs FEA (not de-meaned): {zero_rms:.2f} mm")

    # ── Validation B: Known bolt strokes ──
    print("\n" + "=" * 64)
    print("Validation B: Known bolt strokes vs FEA")
    print("=" * 64)
    h_strokes = load_bolt_strokes(BOLT_PATH)
    print(f"  Bolt strokes: [{h_strokes.min()*1000:.2f}, {h_strokes.max()*1000:.2f}] mm")

    c_stroke, d_stroke = solver.solve(h_strokes)
    w_proxy_bolts, dwdx_b, dwdz_b, nx_b, ny_b, nz_b = \
        solver.surface_with_normals(c_stroke, d_stroke)

    # De-mean comparison
    w_proxy_dm = w_proxy_bolts - np.mean(w_proxy_bolts)
    u_fea_dm = u_grid_fea - np.mean(u_grid_fea)
    residual_bolts = w_proxy_dm - u_fea_dm

    rms_bolts = np.sqrt(np.mean(residual_bolts**2)) * 1000
    max_err_bolts = np.max(np.abs(residual_bolts)) * 1000
    sst = np.sum(u_fea_dm**2)
    r2_bolts = 1.0 - np.sum(residual_bolts**2) / max(sst, 1e-30)
    pv_proxy = np.ptp(w_proxy_dm) * 1000
    pv_fea = np.ptp(u_fea_dm) * 1000
    pv_ratio = pv_proxy / max(pv_fea, 1e-10)

    # Shape correlation
    shape_corr = np.corrcoef(w_proxy_dm.ravel(), u_fea_dm.ravel())[0, 1]

    print(f"  Proxy PV: {pv_proxy:.2f} mm")
    print(f"  FEA PV:   {pv_fea:.2f} mm")
    print(f"  PV ratio: {pv_ratio:.4f}")
    print(f"  RMS:      {rms_bolts:.4f} mm")
    print(f"  Max err:  {max_err_bolts:.4f} mm")
    print(f"  R2:       {r2_bolts:.4f}")
    print(f"  Shape corr: {shape_corr:.4f}")

    # Compare with baselines
    baselines = {
        'finite_difference': 4.60,
        'bezier+tps_interp': 5.78,
        'baseline_tps': 7.20,
    }
    best_baseline = min(baselines.values())
    print(f"\n  Baseline comparison (best={best_baseline:.2f}mm):")
    for name, rms in sorted(baselines.items(), key=lambda x: x[1]):
        marker = ' <- NEW BEST!' if rms_bolts < rms else ''
        status = 'BETTER' if rms_bolts < rms else '  worse'
        print(f"    {name:>25s}: {rms:.2f} mm {status}{marker}")

    # ── Gradient check ──
    print("\n" + "=" * 64)
    print("Validation C: Gradient verification (FD vs AD)")
    print("=" * 64)
    cos_sim, max_rel_err = gradient_check(solver, h_strokes, eps=1e-5, verbose=True)
    grad_ok = cos_sim > 0.99

    # ── Optimization: fit bolt heights to FEA surface ──
    print("\n" + "=" * 64)
    print("Optimization: Fitting bolt heights to FEA surface")
    print("=" * 64)

    # Initialize from zero
    h_opt = np.zeros(NB, dtype=np.float64)
    optimizer = AdamOptimizer(NB, lr=5e-4, beta1=0.9, beta2=0.999,
                              min_lr=1e-7, lr_decay=0.998)

    n_iters = 500
    loss_history = []
    rms_history = []
    pv_history = []
    h_history = []

    t_start = time.time()
    for it in range(n_iters):
        # Forward
        c, d = solver.solve(h_opt)
        w_opt, _, _, _, _, _ = solver.surface_with_normals(c, d)

        # Loss: MSE vs FEA (de-meaned to focus on shape, not rigid offset)
        w_opt_dm = w_opt - np.mean(w_opt)
        diff = w_opt_dm - u_fea_dm
        loss = 0.5 * np.mean(diff**2)
        dL_dw = diff / diff.size

        # Backward
        dL_dh, dL_dc, dL_dd = solver.full_backward(dL_dw, c, d)

        # Apply bolt non-negative constraint (physically bolts can only push, not pull)
        # Soft penalty for negative heights
        neg_mask = h_opt < 0
        if neg_mask.any():
            penalty = 1e3 * np.sum(h_opt[neg_mask]**2)
            loss += penalty
            dL_dh[neg_mask] += 2e3 * h_opt[neg_mask]

        # Adam step
        h_opt = optimizer.step(h_opt, dL_dh)

        # Track
        rms_it = np.sqrt(np.mean(diff**2)) * 1000
        loss_history.append(loss)
        rms_history.append(rms_it)
        pv_history.append(np.ptp(w_opt_dm) * 1000)
        if it % 100 == 0 or it == n_iters - 1:
            print(f"  iter {it:4d}: loss={loss:.6e}, RMS={rms_it:.3f}mm, "
                  f"PV={np.ptp(w_opt_dm)*1000:.2f}mm, "
                  f"h_range=[{h_opt.min()*1000:.2f},{h_opt.max()*1000:.2f}]mm")

    t_elapsed = time.time() - t_start
    print(f"\n  Optimization complete: {n_iters} iters in {t_elapsed:.1f}s")

    # Final evaluation
    c_final, d_final = solver.solve(h_opt)
    w_final, dwdx_f, dwdz_f, nx_f, ny_f, nz_f = \
        solver.surface_with_normals(c_final, d_final)
    w_final_dm = w_final - np.mean(w_final)
    residual_final = w_final_dm - u_fea_dm

    rms_final = np.sqrt(np.mean(residual_final**2)) * 1000
    max_err_final = np.max(np.abs(residual_final)) * 1000
    r2_final = 1.0 - np.sum(residual_final**2) / max(sst, 1e-30)
    pv_final = np.ptp(w_final_dm) * 1000
    pv_ratio_final = pv_final / max(pv_fea, 1e-10)
    shape_corr_final = np.corrcoef(w_final_dm.ravel(), u_fea_dm.ravel())[0, 1]

    print(f"\n  Final results after optimization:")
    print(f"    RMS:       {rms_final:.4f} mm (was {rms_bolts:.4f})")
    print(f"    R^2:        {r2_final:.4f} (was {r2_bolts:.4f})")
    print(f"    PV ratio:  {pv_ratio_final:.4f} (was {pv_ratio:.4f})")
    print(f"    Shape corr: {shape_corr_final:.4f} (was {shape_corr:.4f})")
    print(f"    h range:   [{h_opt.min()*1000:.2f}, {h_opt.max()*1000:.2f}] mm")

    # ── Save outputs ──
    print("\n[Saving] Outputs...")
    os.makedirs(OUT_DIR, exist_ok=True)

    metrics = {
        'method': 'TPS Direct (35 bolt sources)',
        'validation_b_rms_mm': float(rms_bolts),
        'validation_b_r2': float(r2_bolts),
        'validation_b_pv_ratio': float(pv_ratio),
        'optimized_rms_mm': float(rms_final),
        'optimized_r2': float(r2_final),
        'optimized_pv_ratio': float(pv_ratio_final),
        'optimized_shape_corr': float(shape_corr_final),
        'gradient_cosine_sim': float(cos_sim),
        'gradient_max_rel_err': float(max_rel_err),
        'gradient_ok': bool(grad_ok),
        'system_condition': float(solver.condition),
        'n_bolts': NB,
        'n_iters': n_iters,
        'optimization_time_s': float(t_elapsed),
        'baseline_best_rms_mm': float(best_baseline),
    }

    with open(os.path.join(OUT_DIR, 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)

    np.save(os.path.join(OUT_DIR, 'proxy_surface_strokes.npy'), w_proxy_bolts)
    np.save(os.path.join(OUT_DIR, 'proxy_surface_optimized.npy'), w_final)
    np.save(os.path.join(OUT_DIR, 'optimized_heights.npy'), h_opt)
    np.save(os.path.join(OUT_DIR, 'fea_surface.npy'), u_grid_fea)
    np.save(os.path.join(OUT_DIR, 'residual_strokes.npy'), residual_bolts)
    np.save(os.path.join(OUT_DIR, 'residual_optimized.npy'), residual_final)
    np.save(os.path.join(OUT_DIR, 'loss_history.npy'),
            np.array(loss_history))
    np.save(os.path.join(OUT_DIR, 'rms_history.npy'),
            np.array(rms_history))

    # ── Visualization ──
    print("[Visualization] Generating 2D comparison plots...")
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(22, 14))
    gs = GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35,
                  width_ratios=[1, 1, 1, 1], height_ratios=[1, 1, 0.5])

    # Row 1: Stroke-based proxy | FEA | Residual (strokes) | Optimization convergence
    vm1 = max(abs(w_proxy_dm).max(), abs(u_fea_dm).max()) * 1000
    vm1_err = max(abs(residual_bolts).max() * 1000, 0.01)

    titles_r1 = [
        f'TPS Proxy (known strokes)\nPV={pv_proxy:.2f}mm',
        f'FEA Reference (nograv, 58.5°)\nPV={pv_fea:.2f}mm',
        f'Residual (strokes)\nRMS={rms_bolts:.2f}mm R^2={r2_bolts:.3f}',
        'Optimization Convergence'
    ]
    data_r1 = [w_proxy_dm * 1000, u_fea_dm * 1000, residual_bolts * 1000, None]
    cmaps_r1 = ['RdYlBu_r', 'RdYlBu_r', 'RdBu_r', None]

    for col in range(3):
        ax = fig.add_subplot(gs[0, col])
        im = ax.pcolormesh(Xg, Zg, data_r1[col], cmap=cmaps_r1[col], shading='auto',
                           vmin=(-vm1 if col < 2 else -vm1_err),
                           vmax=(vm1 if col < 2 else vm1_err))
        ax.set_title(titles_r1[col], fontsize=9, fontweight='bold')
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

    # Convergence plot
    ax_conv = fig.add_subplot(gs[0, 3])
    ax_conv.plot(rms_history, 'b-', lw=1, label='RMS')
    ax_conv.axhline(y=rms_bolts, color='gray', ls='--', alpha=0.5,
                    label=f'Strokes: {rms_bolts:.1f}mm')
    ax_conv.axhline(y=best_baseline, color='orange', ls=':', alpha=0.5,
                    label=f'Best baseline: {best_baseline:.1f}mm')
    ax_conv.set_xlabel('Iteration'); ax_conv.set_ylabel('RMS (mm)')
    ax_conv.set_title('RMS Convergence', fontsize=9, fontweight='bold')
    ax_conv.legend(fontsize=7); ax_conv.grid(True, alpha=0.3)
    ax_conv.set_yscale('log')

    # Row 2: Optimized proxy | FEA | Residual (optimized) | Bolt heights comparison
    vm2 = max(abs(w_final_dm).max(), abs(u_fea_dm).max()) * 1000
    vm2_err = max(abs(residual_final).max() * 1000, 0.01)

    titles_r2 = [
        f'TPS Proxy (optimized)\nPV={pv_final:.2f}mm',
        f'FEA Reference\nPV={pv_fea:.2f}mm',
        f'Residual (optimized)\nRMS={rms_final:.2f}mm R^2={r2_final:.3f}',
        'Bolt Heights: Strokes vs Optimized'
    ]
    data_r2 = [w_final_dm * 1000, u_fea_dm * 1000, residual_final * 1000, None]

    for col in range(3):
        ax = fig.add_subplot(gs[1, col])
        im = ax.pcolormesh(Xg, Zg, data_r2[col], cmap=cmaps_r1[col], shading='auto',
                           vmin=(-vm2 if col < 2 else -vm2_err),
                           vmax=(vm2 if col < 2 else vm2_err))
        ax.set_title(titles_r2[col], fontsize=9, fontweight='bold')
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)')
        plt.colorbar(im, ax=ax, label='mm')

    # Bolt heights comparison
    ax_bolts = fig.add_subplot(gs[1, 3])
    bolt_idx = np.arange(NB)
    ax_bolts.bar(bolt_idx - 0.15, h_strokes * 1000, width=0.3,
                 color='steelblue', alpha=0.7, label='Known strokes')
    ax_bolts.bar(bolt_idx + 0.15, h_opt * 1000, width=0.3,
                 color='coral', alpha=0.7, label='Optimized')
    ax_bolts.axhline(y=0, color='black', lw=0.5)
    ax_bolts.set_xlabel('Bolt index'); ax_bolts.set_ylabel('Height (mm)')
    ax_bolts.set_title('Bolt Height Comparison', fontsize=9, fontweight='bold')
    ax_bolts.legend(fontsize=7)
    ax_bolts.grid(True, alpha=0.3)

    # Row 3: Cross-section + metrics table + per-row RMS
    # Center cross-section
    ax_xs = fig.add_subplot(gs[2, 0])
    mid_row = GS // 2
    ax_xs.plot(X_GRID, w_final_dm[mid_row, :] * 1000, 'b-', lw=2, label='Optimized')
    ax_xs.plot(X_GRID, w_proxy_dm[mid_row, :] * 1000, 'g--', lw=1, alpha=0.6,
               label='Strokes')
    ax_xs.plot(X_GRID, u_fea_dm[mid_row, :] * 1000, 'r:', lw=2, label='FEA')
    ax_xs.set_xlabel('x (m)'); ax_xs.set_ylabel('w (mm)')
    ax_xs.set_title('Center cross-section (z=0)', fontsize=9, fontweight='bold')
    ax_xs.legend(fontsize=7); ax_xs.grid(True, alpha=0.3)

    # Per-row RMS
    ax_rms_row = fig.add_subplot(gs[2, 1])
    rms_per_row_final = np.array([np.sqrt(np.mean(residual_final[i, :]**2))*1000
                                   for i in range(GS)])
    rms_per_row_strokes = np.array([np.sqrt(np.mean(residual_bolts[i, :]**2))*1000
                                     for i in range(GS)])
    ax_rms_row.plot(Z_GRID, rms_per_row_strokes, 'gray', lw=1, alpha=0.5,
                    label=f'Strokes mean={rms_per_row_strokes.mean():.1f}')
    ax_rms_row.plot(Z_GRID, rms_per_row_final, 'b-o', ms=2,
                    label=f'Optimized mean={rms_per_row_final.mean():.1f}')
    ax_rms_row.fill_between(Z_GRID, 0, rms_per_row_final, alpha=0.1, color='blue')
    ax_rms_row.set_xlabel('z (m)'); ax_rms_row.set_ylabel('RMS (mm)')
    ax_rms_row.set_title('Per-row RMS error', fontsize=9, fontweight='bold')
    ax_rms_row.legend(fontsize=7); ax_rms_row.grid(True, alpha=0.3)

    # Metrics table
    ax_tbl = fig.add_subplot(gs[2, 2:])
    ax_tbl.axis('off')
    improvement = rms_bolts - rms_final
    tbl_text = (
        f"Validation Summary\n"
        f"{'='*42}\n"
        f"  TPS (35 sources) vs FEA (nograv)\n"
        f"{'='*42}\n"
        f"  Validation B (known strokes):\n"
        f"    RMS:       {rms_bolts:.4f} mm\n"
        f"    R^2:        {r2_bolts:.4f}\n"
        f"    PV ratio:  {pv_ratio:.4f}\n"
        f"    Shape corr: {shape_corr:.4f}\n"
        f"  ──────────────────────────\n"
        f"  Validation C (optimized):\n"
        f"    RMS:       {rms_final:.4f} mm\n"
        f"    R^2:        {r2_final:.4f}\n"
        f"    PV ratio:  {pv_ratio_final:.4f}\n"
        f"    Improvement: {improvement:+.2f} mm\n"
        f"  ──────────────────────────\n"
        f"  Gradient check:\n"
        f"    Cosine sim: {cos_sim:.6f}\n"
        f"    Status:     {'PASS' if grad_ok else 'FAIL'}\n"
        f"  ──────────────────────────\n"
        f"  System: cond={solver.condition:.0f}\n"
        f"  Baseline best: {best_baseline:.2f} mm\n"
        f"  Optimization: {n_iters} iters, {t_elapsed:.1f}s"
    )
    ax_tbl.text(0.05, 0.95, tbl_text, transform=ax_tbl.transAxes,
                fontsize=8.5, fontfamily='monospace', va='top',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    fig.suptitle('TPS Proxy Model: Direct 35-Bolt Parameterization vs FEA',
                 fontsize=13, fontweight='bold', y=0.99)
    plt.savefig(os.path.join(OUT_DIR, 'comparison.png'), dpi=150,
                bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  Saved: {os.path.join(OUT_DIR, 'comparison.png')}")

    # ── Phase 5 prep: Save normal field for flux validation ──
    np.save(os.path.join(OUT_DIR, 'normals_optimized.npy'),
            np.stack([nx_f, ny_f, nz_f], axis=-1))

    # ── Final summary ──
    print(f"\n{'='*64}")
    print(f"Results saved to: {OUT_DIR}/")
    print(f"  metrics.json, comparison.png")
    print(f"  proxy_surface_strokes.npy, proxy_surface_optimized.npy")
    print(f"  optimized_heights.npy, normals_optimized.npy")
    print(f"\nKey Results:")
    print(f"  Strokes RMS:  {rms_bolts:.4f} mm (baseline best: {best_baseline:.2f} mm)")
    print(f"  Optimized RMS: {rms_final:.4f} mm (Delta = {improvement:+.2f} mm)")
    print(f"  Gradient check: {'PASS' if grad_ok else 'FAIL'}")
    if rms_final < best_baseline:
        print(f"  *** NEW BEST RESULT! ***")
    print(f"{'='*64}")

    return metrics


if __name__ == '__main__':
    main()
