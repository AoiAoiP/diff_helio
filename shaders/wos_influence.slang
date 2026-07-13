// wos_influence.slang — Grid-free WoS influence function computation
//
// Solves D·nabla^4 w = 0 on rectangular plate with free-edge BC
// using coupled double-layer Walk on Spheres.
// All bindings declared directly in this file (no separate module — Slang import
// doesn't propagate [[vk::binding]] to SPIR-V).

// ── Push constants ────────────────────────────────────────────────────
struct WoS_PC { float plateW; float plateL; float D_plate; float nu; };
[[vk::push_constant]] WoS_PC pc;

// ── Buffer bindings ───────────────────────────────────────────────────
[[vk::binding(0, 0)]] uniform StructuredBuffer<float2> boltPositions;
[[vk::binding(1, 0)]] RWStructuredBuffer<float> influencePhi;

// ── Constants ──────────────────────────────────────────────────────────
static const uint TEX_W    = 256u;
static const uint TEX_H    = 192u;
static const uint N_BOLTS  = 35u;
static const uint N_WALKS  = 5000u;
static const float kEps    = 0.005f;
static const float kPi     = 3.14159265358979f;

// ── PRNG ──────────────────────────────────────────────────────────────
uint pcgHash(uint seed) {
    uint state = seed * 747796405u + 2891336453u;
    uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
    return (word >> 22u) ^ word;
}
float rand01(inout uint seed) { seed = pcgHash(seed); return (float(seed)+0.5f)/4294967296.0f; }

// ── Geometry helpers ──────────────────────────────────────────────────
float distToBoundary(float2 pos, float hW, float hL) { return min(hW-abs(pos.x), hL-abs(pos.y)); }
float2 sampleCircle(float r, inout uint seed) { float t=rand01(seed)*2*kPi; return float2(r*cos(t),r*sin(t)); }
bool nearBolt(float2 pos, uint bi) { float2 d=pos-boltPositions[bi]; return sqrt(d.x*d.x+d.y*d.y)<kEps*3; }

// ── Layer 1: Neumann walk for moment M ────────────────────────────────
float walkMoment(float2 pos, uint boltIdx, float hW, float hL, inout uint seed) {
    float M = 0;
    for(uint s=0; s<200; s++) {
        float r = distToBoundary(pos, hW, hL);
        if(r < kEps) {
            float dL=abs(pos.x+hW),dR=abs(hW-pos.x),dB=abs(pos.y+hL),dT=abs(hL-pos.y);
            float dM=min(min(dL,dR),min(dB,dT));
            if(dM==dL) pos.x=-hW+kEps*2; else if(dM==dR) pos.x=hW-kEps*2;
            if(dM==dB) pos.y=-hL+kEps*2; else if(dM==dT) pos.y=hL-kEps*2;
            continue;
        }
        pos += sampleCircle(r, seed);
        if(nearBolt(pos, boltIdx)) { M += 1; return M; }
    }
    return M;
}

// ── Layer 2: Dirichlet walk for deflection w ──────────────────────────
float walkDeflection(float2 pos, uint boltIdx, float hW, float hL, float Dp, inout uint seed) {
    float w = 0;
    for(uint s=0; s<200; s++) {
        float r = distToBoundary(pos, hW, hL);
        if(r < kEps) return w;
        w += walkMoment(pos, boltIdx, hW, hL, seed) / Dp * r * r * 0.25;
        pos += sampleCircle(r, seed);
        for(uint bi=0; bi<N_BOLTS; bi++) {
            if(nearBolt(pos, bi)) { w += (bi==boltIdx)?1:0; return w; }
        }
    }
    return w;
}

// ── Main compute kernel ───────────────────────────────────────────────
[shader("compute")]
[numthreads(256, 1, 1)]
void computeWoSInfluence(uint tid : SV_DispatchThreadID) {
    uint ppb = TEX_W * TEX_H;
    uint boltIdx = tid / ppb;
    uint pixIdx  = tid % ppb;
    if(boltIdx >= N_BOLTS) return;

    uint px = pixIdx % TEX_W;
    uint py = pixIdx / TEX_W;
    float2 eval;
    eval.x = ((float(px)+0.5)/float(TEX_W)-0.5)*pc.plateW;
    eval.y = ((float(py)+0.5)/float(TEX_H)-0.5)*pc.plateL;
    float hW=pc.plateW*0.5, hL=pc.plateL*0.5, Dp=pc.D_plate;

    uint seed = boltIdx*2654435761u + px*73856093u + py*19349663u;
    float wSum = 0;
    for(uint walk=0; walk<N_WALKS; walk++) {
        wSum += walkDeflection(eval, boltIdx, hW, hL, Dp, seed);
        seed = pcgHash(seed);
    }
    influencePhi[boltIdx * ppb + py * TEX_W + px] = wSum / float(N_WALKS);
}
