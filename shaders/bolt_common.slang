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
// Bindings 31-50: multi-angle FEA gravity bins (10/14/18/.../78/80 deg), RO
// Re-generate with: python scripts/ansys_gravity.py
[[vk::binding(31)]] public uniform StructuredBuffer<float> gravityBin10;
[[vk::binding(32)]] public uniform StructuredBuffer<float> gravityBin14;
[[vk::binding(33)]] public uniform StructuredBuffer<float> gravityBin18;
[[vk::binding(34)]] public uniform StructuredBuffer<float> gravityBin22;
[[vk::binding(35)]] public uniform StructuredBuffer<float> gravityBin26;
[[vk::binding(36)]] public uniform StructuredBuffer<float> gravityBin30;
[[vk::binding(37)]] public uniform StructuredBuffer<float> gravityBin34;
[[vk::binding(38)]] public uniform StructuredBuffer<float> gravityBin38;
[[vk::binding(39)]] public uniform StructuredBuffer<float> gravityBin42;
[[vk::binding(40)]] public uniform StructuredBuffer<float> gravityBin46;
[[vk::binding(41)]] public uniform StructuredBuffer<float> gravityBin50;
[[vk::binding(42)]] public uniform StructuredBuffer<float> gravityBin54;
[[vk::binding(43)]] public uniform StructuredBuffer<float> gravityBin58;
[[vk::binding(44)]] public uniform StructuredBuffer<float> gravityBin62;
[[vk::binding(45)]] public uniform StructuredBuffer<float> gravityBin66;
[[vk::binding(46)]] public uniform StructuredBuffer<float> gravityBin70;
[[vk::binding(47)]] public uniform StructuredBuffer<float> gravityBin73;
[[vk::binding(48)]] public uniform StructuredBuffer<float> gravityBin76;
[[vk::binding(49)]] public uniform StructuredBuffer<float> gravityBin78;
[[vk::binding(50)]] public uniform StructuredBuffer<float> gravityBin80;
// Bindings 23-24: surface derivative grids (RW, populated by computeBoltSurface)
[[vk::binding(23)]] public RWStructuredBuffer<float> yuGrid;
[[vk::binding(24)]] public RWStructuredBuffer<float> yvGrid;
// Binding 25: per-grid-point surface gradient accumulator (RW, 3 * gridSize^2)
// Phase 5: uint-typed for atomic float add via InterlockedCompareExchange (matching s95_histogram.slang)
[[vk::binding(25)]] public RWStructuredBuffer<uint> surfaceGradient;

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

// ---- Multi-angle gravity sampling (20 bins, 10-80 deg) ----
// Known gravity bin angles in degrees, sorted ascending.
// Must match THE SAME ORDER as the StructuredBuffer bindings 31-50.
static const uint kNumGravityBins = 20;
static const float kGravityAngles[20] = {10.0, 14.0, 18.0, 22.0, 26.0, 30.0, 34.0, 38.0, 42.0, 46.0,
                                         50.0, 54.0, 58.0, 62.0, 66.0, 70.0, 73.0, 76.0, 78.0, 80.0};

// Select the gravity bin buffer for a given index 0..19.
float _readGravity(uint binIdx, uint gridIdx) {
    switch (binIdx) {
        case 0u:  return gravityBin10[gridIdx];
        case 1u:  return gravityBin14[gridIdx];
        case 2u:  return gravityBin18[gridIdx];
        case 3u:  return gravityBin22[gridIdx];
        case 4u:  return gravityBin26[gridIdx];
        case 5u:  return gravityBin30[gridIdx];
        case 6u:  return gravityBin34[gridIdx];
        case 7u:  return gravityBin38[gridIdx];
        case 8u:  return gravityBin42[gridIdx];
        case 9u:  return gravityBin46[gridIdx];
        case 10u: return gravityBin50[gridIdx];
        case 11u: return gravityBin54[gridIdx];
        case 12u: return gravityBin58[gridIdx];
        case 13u: return gravityBin62[gridIdx];
        case 14u: return gravityBin66[gridIdx];
        case 15u: return gravityBin70[gridIdx];
        case 16u: return gravityBin73[gridIdx];
        case 17u: return gravityBin76[gridIdx];
        case 18u: return gravityBin78[gridIdx];
        default:  return gravityBin80[gridIdx];
    }
}

// Samples the precomputed FEA gravity UY field by linear interpolation
// between the two nearest gravity angle bins.
// lo/hi are indices into kGravityAngles (range 0..19).
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
