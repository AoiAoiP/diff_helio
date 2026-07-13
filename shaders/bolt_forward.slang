// bolt_forward.slang — Bolt surface computation for forward rendering
// Replaces computeBezierSurface from forward.slang.
// Supplies yGrid, yuGrid, yvGrid, nGrid for renderForward (which is unchanged).
module bolt_forward;
import common;
import bolt_common;

// Push constant: number of active bolts + gravity interpolation params
// lo/hi: bin indices for lerp (0=0°,1=30°,2=45°,3=60°,4=75°), t: lerp weight
struct BoltSurfacePC { uint numBolts; uint gravityLo; uint gravityHi; float gravityT; uint disableGravity; };
[[vk::push_constant]] BoltSurfacePC pushConst;

// ---- Bolt Surface Kernel ----
// w_total = lerp(gravityBin[lo], gravityBin[hi], t) + sum_i boltHeight[i] * phi_i
// Dispatch: (1, 1, 1) with kGridSize x kGridSize threads.
[shader("compute")]
[numthreads(kGridSize, kGridSize, 1)]
void computeBoltSurface(uint3 tid : SV_DispatchThreadID) {
    if (tid.x >= kGridSize || tid.y >= kGridSize) return;

    float y, yu, yv;
    float3 nrm;
    boltSurfaceAtGrid(tid.x, tid.y, pushConst.numBolts, pushConst.gravityLo, pushConst.gravityHi, pushConst.gravityT, pushConst.disableGravity, y, yu, yv, nrm);

    uint idx = tid.y * kGridSize + tid.x;
    yGrid[idx] = y;
    yuGrid[idx] = yu;
    yvGrid[idx] = yv;
    nGrid[idx] = float4(nrm, 0.0f);
}
