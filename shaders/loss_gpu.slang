// loss_gpu.slang — GPU-side loss reduction (avoids GPU→CPU texture download)
// Computes loss directly from renderedFlux, outputs scalar to small buffer
module loss_gpu;
import common;

[[vk::binding(8)]] [format("r32f")] RWTexture2D<float> renderedFlux;

// Output: partial sums per group, then reduced to scalar
[[vk::binding(15)]] RWStructuredBuffer<float> lossReduceBuf; // [0]=result, [1..]=partials

struct LossPC { float s95Level; };
[[vk::push_constant]] LossPC pushConst;

static const uint kLossGroupSize = 256u;
groupshared float gs_lossSum;

// Stage 1: each group reduces its portion of the flux texture
[shader("compute")]
[numthreads(kLossGroupSize, 1, 1)]
void reduceLossPartial(uint3 gid : SV_GroupID, uint3 gtid : SV_GroupThreadID) {
    uint lid = gtid.x;
    uint2 dims = getReceiverDims();
    uint totalPixels = dims.x * dims.y;
    float sum = 0.0f;

    // Each thread sums a strided range of pixels
    for (uint i = lid; i < totalPixels; i += kLossGroupSize) {
        uint px = i % dims.x;
        uint py = i / dims.x;
        float f = renderedFlux[uint2(px, py)];
        float s = 1.0f / (1.0f + exp(-6.0f * (f / max(pushConst.s95Level, kEpsilon) - 1.0f)));
        sum += s;
    }

    // Group reduction
    gs_lossSum = 0.0f;
    GroupMemoryBarrierWithGroupSync();
    sum = WaveActiveSum(sum);
    if (WaveIsFirstLane()) {
        // Use atomic add via CAS loop on float-as-uint
        uint prevVal;
        uint expected;
        uint newVal;
        uint idx = 1u + gid.x;
        // Simple: just write to group slot (no atomic needed since each group writes to unique slot)
        lossReduceBuf[idx] = sum;
    }
}

// Stage 2: single group sums all partials into final result
[shader("compute")]
[numthreads(kLossGroupSize, 1, 1)]
void reduceLossFinal(uint3 gid : SV_GroupID, uint3 gtid : SV_GroupThreadID) {
    uint lid = gtid.x;
    uint totalGroups = (getReceiverDims().x * getReceiverDims().y + kLossGroupSize - 1u) / kLossGroupSize;
    float sum = 0.0f;
    for (uint i = lid; i < totalGroups; i += kLossGroupSize) {
        sum += lossReduceBuf[1u + i];
    }
    sum = WaveActiveSum(sum);
    if (lid == 0u) {
        lossReduceBuf[0] = sum;
    }
}
