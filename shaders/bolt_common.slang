// bolt_common.slang — Bolt influence function surface representation
// Replaces Bezier CP parameterization with linear bolt-height superposition.
// Imports common for shared UBOs (bindings 0-4) and coordinate transforms.
module bolt_common;
import common;

// Bolt count constants
public static const uint kMaxBolts  = 50u;

// ---- Bolt-mode buffer bindings (extend set 0 beyond Bezier's 0-16) ----
// Binding 17: bolt heights (read-only during forward/backward, RW during adam)
[[vk::binding(17)]] public uniform StructuredBuffer<float> boltHeights;
// Binding 18: bolt height gradient accumulator (RW)
[[vk::binding(18)]] public RWStructuredBuffer<float> boltHeightGradient;
// Bindings 19-21: precomputed influence function textures (RO)
// Layout: [boltIdx * gridSize^2 + row * gridSize + col]
[[vk::binding(19)]] public uniform StructuredBuffer<float> influencePhi;
[[vk::binding(20)]] public uniform StructuredBuffer<float> influencePhiU;
[[vk::binding(21)]] public uniform StructuredBuffer<float> influencePhiV;
// Binding 22: gravity sag precomputation (RO, legacy - kept for compat)
[[vk::binding(22)]] public uniform StructuredBuffer<float> gravityY;
// Binding 30: FEA gravity base texture (RO) — legacy, kept for compat
[[vk::binding(30)]] public uniform StructuredBuffer<float> gravityBase;
// Bindings 31-40: multi-angle FEA gravity bins (0/12/22/30/35/45/52/60/67/75°), RO
// Re-generate with: scripts/train_residual/precompute_gravity_bins.py --angles 0 12 22 30 35 45 52 60 67 75
[[vk::binding(31)]] public uniform StructuredBuffer<float> gravityBin0;
[[vk::binding(32)]] public uniform StructuredBuffer<float> gravityBin12;
[[vk::binding(33)]] public uniform StructuredBuffer<float> gravityBin22;
[[vk::binding(34)]] public uniform StructuredBuffer<float> gravityBin30;
[[vk::binding(35)]] public uniform StructuredBuffer<float> gravityBin35;
[[vk::binding(36)]] public uniform StructuredBuffer<float> gravityBin45;
[[vk::binding(37)]] public uniform StructuredBuffer<float> gravityBin52;
[[vk::binding(38)]] public uniform StructuredBuffer<float> gravityBin60;
[[vk::binding(39)]] public uniform StructuredBuffer<float> gravityBin67;
[[vk::binding(40)]] public uniform StructuredBuffer<float> gravityBin75;
// Bindings 23-24: surface derivative grids (RW, populated by computeBoltSurface)
[[vk::binding(23)]] public RWStructuredBuffer<float> yuGrid;
[[vk::binding(24)]] public RWStructuredBuffer<float> yvGrid;
// Binding 25: per-grid-point surface gradient accumulator (RW, 3 * gridSize^2)
[[vk::binding(25)]] public RWStructuredBuffer<float> surfaceGradient;

// Bolt count from host push constant (set at dispatch time)
// Access via a global that gets set by push constant in each kernel

// ---- Influence function evaluation at a grid point ----
public float evaluateInfluence(uint boltIdx, uint gridU, uint gridV) {
    uint idx = boltIdx * kGridSize * kGridSize + gridV * kGridSize + gridU;
    return influencePhi[idx];
}

public float evaluateInfluenceU(uint boltIdx, uint gridU, uint gridV) {
    uint idx = boltIdx * kGridSize * kGridSize + gridV * kGridSize + gridU;
    return influencePhiU[idx];
}

public float evaluateInfluenceV(uint boltIdx, uint gridU, uint gridV) {
    uint idx = boltIdx * kGridSize * kGridSize + gridV * kGridSize + gridU;
    return influencePhiV[idx];
}

// ---- Multi-angle gravity sampling (10 bins, dense) ----
// Known gravity bin angles in degrees, sorted ascending.
// Must match THE SAME ORDER as the StructuredBuffer bindings 31-40.
static const float kGravityAngles[10] = {0.0, 12.0, 22.0, 30.0, 35.0, 45.0, 52.0, 60.0, 67.0, 75.0};

// Select the gravity bin buffer for a given index 0..9.
float _readGravity(uint binIdx, uint gridIdx) {
    switch (binIdx) {
        case 0u: return gravityBin0[gridIdx];
        case 1u: return gravityBin12[gridIdx];
        case 2u: return gravityBin22[gridIdx];
        case 3u: return gravityBin30[gridIdx];
        case 4u: return gravityBin35[gridIdx];
        case 5u: return gravityBin45[gridIdx];
        case 6u: return gravityBin52[gridIdx];
        case 7u: return gravityBin60[gridIdx];
        case 8u: return gravityBin67[gridIdx];
        default: return gravityBin75[gridIdx];
    }
}

// Samples the precomputed FEA gravity UY field by linear interpolation
// between the two nearest gravity angle bins.
// lo/hi are indices into kGravityAngles (range 0..9).
public float sampleGravityUY(uint gridIdx, uint lo, uint hi, float t) {
    float gLo = _readGravity(lo, gridIdx);
    // When lo==hi (exact match or single-bin case) avoid the second read.
    if (lo == hi) return gLo;
    float gHi = _readGravity(hi, gridIdx);
    return lerp(gLo, gHi, t);
}

// ---- Bolt surface evaluation (replaces bezierSurface + bezierSurfaceNormal) ----
// Computes y, yu, yv, and normal at a single (u,v) grid point.
// w_total(u,v) = UY_grav^FEA(u,v,theta) + sum_b boltHeights[b] * phi_b(u,v)
// to vertical UY displacement. Gravity is sampled from multi-angle FEA bins.
public void boltSurfaceAtGrid(
    uint gridU, uint gridV, uint numBolts, uint gravityLo, uint gravityHi, float gravityT, uint disableGravity,
    out float y, out float yu, out float yv, out float3 nrm)
{
    uint gridIdx = gridV * kGridSize + gridU;
    y  = (disableGravity != 0u) ? 0.0f : sampleGravityUY(gridIdx, gravityLo, gravityHi, gravityT);
    yu = 0.0f;
    yv = 0.0f;

    for (uint b = 0u; b < numBolts; b++) {
        float phi   = evaluateInfluence(b, gridU, gridV);
        float phi_u = evaluateInfluenceU(b, gridU, gridV);
        float phi_v = evaluateInfluenceV(b, gridU, gridV);
        float h = boltHeights[b];
        y  += h * phi;
        yu += h * phi_u;
        yv += h * phi_v;
    }

    // Normal from surface derivatives (matches bezierSurfaceNormal convention)
    float2 hs = getHeliostatSize();
    float3 tu = float3(hs.x, yu, 0.0f);
    float3 tv = float3(0.0f, yv, hs.y);
    nrm = -normalize(cross(tu, tv));
}
