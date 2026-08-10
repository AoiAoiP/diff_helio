// loss.slang - S95 loss computation (flux gradient + pixel counting on GPU)
module loss;
import common;

[[vk::binding(8)]] [format("r32f")]
RWTexture2D<float> renderedFlux;
[[vk::binding(12)]] [format("r32f")]
RWTexture2D<float> fluxGradient;

struct LossPC { float s95Level; };
[[vk::push_constant]] LossPC pushConst;

// Per-thread-group reduction buffer for pixel count (uint32)
[[vk::binding(15)]] RWStructuredBuffer<uint> s95CountBuf;

static const uint kGroupSize = 256u;
groupshared uint gs_count;

[shader("compute")]
[numthreads(16,16,1)]
void computeS95Loss(uint3 tid:SV_DispatchThreadID){
    uint2 dims=getReceiverDims();
    if(tid.x>=dims.x||tid.y>=dims.y) return;
    float flux=renderedFlux[tid.xy];
    float lv=max(pushConst.s95Level,kEpsilon);
    float nf=flux/lv;
    float s=1.0f/(1.0f+exp(-6.0f*(nf-1.0f)));
    fluxGradient[tid.xy]=6.0f*s*(1.0f-s)/lv;
}

// Zero-out fluxGradient (called before each sun direction's S95 loss)
[shader("compute")]
[numthreads(16, 16, 1)]
void clearFluxGradient(uint3 tid : SV_DispatchThreadID) {
    uint2 dims = getReceiverDims();
    if (tid.x >= dims.x || tid.y >= dims.y) return;
    fluxGradient[tid.xy] = 0.0f;
}
