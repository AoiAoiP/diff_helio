#!/usr/bin/env python3
"""
Rigorous verification: does h_b = w_ellipse(x_b, z_b) accurately reproduce
the ellipse surface through the TPS model?

Tests:
1. Direct evaluation: h_b = ellipse(x_b, z_b) → compute TPS surface → compare with ellipse
2. Least-squares fit: min ||sum h_b·phi_b - ellipse||^2 → compare accuracy
"""
import numpy as np
import os
import sys

W, L = 12.84, 9.45
NB = 35
GS = 32
MARGIN = 0.08

# -- Bolt positions --------------------------------------------------─
def bolt_positions():
    pos = np.zeros((NB, 2))
    idx = 0
    for j in range(5):
        v = MARGIN + (1.0 - 2.0*MARGIN) * j / 4.0
        for i in range(7):
            u = MARGIN + (1.0 - 2.0*MARGIN) * i / 6.0
            pos[idx, 0] = (u - 0.5) * W
            pos[idx, 1] = (v - 0.5) * L
            idx += 1
    return pos

# -- Load influence functions ----------------------------------------─
DATA_DIR = "data_proxy"

def load_bin(path, dtype=np.float32):
    return np.fromfile(path, dtype=dtype)

print("Loading TPS influence data...")
phi   = load_bin(f"{DATA_DIR}/influence_phi.bin").reshape(NB, GS*GS)    # [35, 1024]
phi_u = load_bin(f"{DATA_DIR}/influence_phi_u.bin").reshape(NB, GS*GS)
phi_v = load_bin(f"{DATA_DIR}/influence_phi_v.bin").reshape(NB, GS*GS)

print(f"  phi shape: {phi.shape}, range: [{phi.min():.6f}, {phi.max():.6f}]")
print(f"  Unit decomposition check: sumphi_b at each grid point:")
unit_sum = phi.sum(axis=0)
print(f"    min={unit_sum.min():.8f}, max={unit_sum.max():.8f}, PV={unit_sum.max()-unit_sum.min():.8f}")

# Self-influence: phi_b at bolt b's own grid position
bolt_grid_idx = np.zeros(NB, dtype=int)
pos = bolt_positions()
for b in range(NB):
    x, z = pos[b, 0], pos[b, 1]
    # Find closest grid point (32x32 → u=x/W+0.5, v=z/L+0.5)
    u_grid = x / W + 0.5
    v_grid = z / L + 0.5
    gi = int(np.clip(u_grid * (GS-1), 0, GS-1))
    gj = int(np.clip(v_grid * (GS-1), 0, GS-1))
    bolt_grid_idx[b] = gj * GS + gi

self_influence = phi[np.arange(NB), bolt_grid_idx]
print(f"\n  Self-influence at bolt grid points:")
print(f"    min={self_influence.min():.4f}, max={self_influence.max():.4f}, "
      f"mean={self_influence.mean():.4f}")
print(f"    bolts outside [0.95,1.05]: {(np.abs(self_influence-1.0)>0.05).sum()}/35")

# -- Grid coordinates ------------------------------------------------─
u_vals = np.linspace(0, 1, GS)
v_vals = np.linspace(0, 1, GS)
x_grid = (u_vals - 0.5) * W
z_grid = (v_vals - 0.5) * L
X, Z = np.meshgrid(x_grid, z_grid, indexing='ij')  # [GS, GS]

# -- Ellipse surface --------------------------------------------------
A, B, C = 6.91e-4, 7.71e-4, 3.0e-7
ellipse_grid = (A * X**2 + B * Z**2 + C * X * Z).flatten()  # [GS*GS]

print(f"\nEllipse surface on {GS}x{GS} grid:")
print(f"  PV={ellipse_grid.max()-ellipse_grid.min():.4f} m = "
      f"{(ellipse_grid.max()-ellipse_grid.min())*1000:.2f} mm")

# -- Method 1: Direct evaluation --------------------------------------
h_direct = np.array([A*x**2 + B*z**2 + C*x*z for x, z in pos])

# Compute TPS surface with these bolts
tps_direct = (h_direct @ phi)  # [1024]

# Compare
diff_direct = tps_direct - ellipse_grid
rms_direct = np.sqrt(np.mean(diff_direct**2))
print(f"\n-- Method 1: Direct evaluation (h_b = ellipse(x_b, z_b)) --")
print(f"  Bolt heights PV: {(h_direct.max()-h_direct.min())*1000:.2f} mm")
print(f"  TPS surface vs ellipse RMS: {rms_direct*1000:.4f} mm")
print(f"  Max error: {np.abs(diff_direct).max()*1000:.4f} mm")
print(f"  PV error: {(diff_direct.max()-diff_direct.min())*1000:.4f} mm")

# -- Method 2: Least-squares fit --------------------------------------
# Solve: min_h ||Phi^T h - w_ellipse||^2
# Phi is [NB, 1024], we want h^T Phi ≈ ellipse^T
# Normal equations: (PhiPhi^T) h = Phi ellipse
PhiPhiT = phi @ phi.T  # [35, 35]
Phi_ellipse = phi @ ellipse_grid  # [35]
h_lsq = np.linalg.solve(PhiPhiT, Phi_ellipse)

tps_lsq = h_lsq @ phi
diff_lsq = tps_lsq - ellipse_grid
rms_lsq = np.sqrt(np.mean(diff_lsq**2))
print(f"\n-- Method 2: Least-squares fit (min ||sum h_b·phi_b - ellipse||^2) --")
print(f"  Bolt heights PV: {(h_lsq.max()-h_lsq.min())*1000:.2f} mm")
print(f"  TPS surface vs ellipse RMS: {rms_lsq*1000:.4f} mm")
print(f"  Max error: {np.abs(diff_lsq).max()*1000:.4f} mm")

# -- Compare the two methods ------------------------------------------
h_diff = h_direct - h_lsq
h_diff_dm = h_diff - h_diff.mean()
print(f"\n-- Method comparison --")
print(f"  h_direct vs h_lsq correlation: {np.corrcoef(h_direct, h_lsq)[0,1]:.6f}")
print(f"  h_direct vs h_lsq RMS diff (de-meaned): {np.sqrt(np.mean(h_diff_dm**2))*1000:.4f} mm")
print(f"  h_direct vs h_lsq max diff: {np.abs(h_diff).max()*1000:.4f} mm")
print(f"  RMS improvement of LSQ over direct: {rms_direct-rms_lsq:.6f} m = {(rms_direct-rms_lsq)*1000:.3f} mm")

# -- Also check: what bolt heights would make TPS exact at bolt positions?
# This is the "interpolation" condition: sum h_b · phi_b(x_j, z_j) = ellipse(x_j, z_j) for each bolt j
print(f"\n-- Method 3: Exact interpolation at bolt positions --")
# Build the [35×35] interpolation matrix: M_{ij} = phi_j at bolt position i
M = np.zeros((NB, NB))
for i in range(NB):
    M[i, :] = phi[:, bolt_grid_idx[i]]
cond = np.linalg.cond(M)
print(f"  Interpolation matrix condition number: {cond:.1f}")
print(f"  (Unit decomposition implies M ≈ I; cond ≈ 1)")

h_interp = np.linalg.solve(M, np.array([A*x**2 + B*z**2 + C*x*z for x, z in pos]))
tps_interp = h_interp @ phi
diff_interp = tps_interp - ellipse_grid
rms_interp = np.sqrt(np.mean(diff_interp**2))
print(f"  Bolt heights PV: {(h_interp.max()-h_interp.min())*1000:.2f} mm")
print(f"  TPS surface vs ellipse RMS: {rms_interp*1000:.4f} mm")
print(f"  h_direct vs h_interp correlation: {np.corrcoef(h_direct, h_interp)[0,1]:.6f}")

# -- Summary ----------------------------------------------------------
print(f"\n{'='*60}")
print(f"SUMMARY: Accuracy of reconstructing ellipse surface via TPS")
print(f"{'='*60}")
print(f"  Method 1 (direct eval):  RMS = {rms_direct*1000:.4f} mm")
print(f"  Method 2 (least squares): RMS = {rms_lsq*1000:.4f} mm")
print(f"  Method 3 (interpolation): RMS = {rms_interp*1000:.4f} mm")
print(f"\n  Direct evaluation is {'adequate' if rms_direct*1000 < 1.0 else 'INADEQUATE'} "
      f"(RMS error {rms_direct*1000:.3f} mm)")
print(f"  The ellipse surface PV is {ellipse_grid.ptp()*1000:.2f} mm, so relative error is "
      f"{rms_direct/ellipse_grid.ptp()*100:.2f}%")
