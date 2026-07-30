# G0 validation: can gravity fields be linearly interpolated across bolt layouts?
# interp(m02, m08; t=1/3) -> predict m04, compare with ground-truth m04 bins.
# Baseline: nearest-anchor (m08) prediction of m04.
# Bins are 3-plane (w, dw/du, dw/dv) x 32x32 float32.
import numpy as np, json, os, sys

D_M02 = "0730_margin_2/data_proxy_margin/7x5_margin02"
D_M04 = "0730_margin_2/data_proxy_margin/7x5_margin04"
D_M08 = "data_proxy"
ANGLES = [10, 30, 58, 80]  # only angles present in all three layouts
GRID = 1024
T = (0.04 - 0.02) / (0.08 - 0.02)  # m04 is 1/3 of the way from m02 to m08

def load(d, a):
    p = f"{d}/gravity_{a}deg.bin"
    v = np.fromfile(p, dtype=np.float32)
    assert v.size == 3 * GRID, f"{p}: {v.size}"
    return v  # [3*1024]

def cos_sim(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))

def rel_l2(pred, ref):
    return float(np.linalg.norm(pred - ref) / np.linalg.norm(ref))

print(f"interpolation weight t={T:.4f}  (m04 = (1-t)*m02 + t*m08)")
print(f"{'angle':>5} | {'cos_interp':>10} {'relL2_interp':>12} | {'cos_m08base':>11} {'relL2_m08base':>13} | {'cos_m02base':>11} {'relL2_m02base':>13}")
rows = []
for a in ANGLES:
    g02, g04, g08 = load(D_M02, a), load(D_M04, a), load(D_M08, a)
    gi = (1 - T) * g02 + T * g08
    rows.append((a, cos_sim(gi, g04), rel_l2(gi, g04),
                    cos_sim(g08, g04), rel_l2(g08, g04),
                    cos_sim(g02, g04), rel_l2(g02, g04)))
    r = rows[-1]
    print(f"{a:>5} | {r[1]:>10.4f} {r[2]:>12.4f} | {r[3]:>11.4f} {r[4]:>13.4f} | {r[5]:>11.4f} {r[6]:>13.4f}")

arr = np.array([r[1:] for r in rows])
print(f"\nmean over {len(ANGLES)} angles:")
print(f"  interp : cos={arr[:,0].mean():.4f}  relL2={arr[:,1].mean():.4f}")
print(f"  m08base: cos={arr[:,2].mean():.4f}  relL2={arr[:,3].mean():.4f}")
print(f"  m02base: cos={arr[:,4].mean():.4f}  relL2={arr[:,5].mean():.4f}")

# w-plane only (the physically dominant plane) for reference
print("\nw-plane-only (first 1024 floats):")
for a in ANGLES:
    g02, g04, g08 = load(D_M02, a)[:GRID], load(D_M04, a)[:GRID], load(D_M08, a)[:GRID]
    gi = (1 - T) * g02 + T * g08
    print(f"  {a:>3}deg: cos_interp={cos_sim(gi,g04):.4f} relL2_interp={rel_l2(gi,g04):.4f} | cos_m08={cos_sim(g08,g04):.4f} relL2_m08={rel_l2(g08,g04):.4f}")
