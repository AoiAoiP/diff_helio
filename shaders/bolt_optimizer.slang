// bolt_optimizer.slang — Adam optimizer for N bolt heights
// Replaces optimizer.slang (16-element Adam) with N-dimensional version.
module bolt_optimizer;

static const uint kMaxBolts = 50u;

[[vk::binding(17)]] RWStructuredBuffer<float> boltHeights;
[[vk::binding(13)]] RWStructuredBuffer<float> adamM;
[[vk::binding(14)]] RWStructuredBuffer<float> adamV;
[[vk::binding(18)]] RWStructuredBuffer<float> boltHeightGradient;

struct AdamBoltPC {
    float lr;
    float beta1;
    float beta2;
    float eps;
    float iterF;
    uint  numBolts;
    float _pad[2];
};
[[vk::push_constant]] AdamBoltPC pc;

[shader("compute")]
[numthreads(kMaxBolts, 1, 1)]
void adamUpdateBolt(uint3 tid : SV_DispatchThreadID) {
    uint i = tid.x;
    if (i >= pc.numBolts) return;

    float grad = boltHeightGradient[i];
    float m = pc.beta1 * adamM[i] + (1.0f - pc.beta1) * grad;
    float v = pc.beta2 * adamV[i] + (1.0f - pc.beta2) * grad * grad;
    adamM[i] = m;
    adamV[i] = v;

    float mHat = m / (1.0f - pow(pc.beta1, pc.iterF));
    float vHat = v / (1.0f - pow(pc.beta2, pc.iterF));
    boltHeights[i] -= pc.lr * mHat / (sqrt(vHat) + pc.eps);
    boltHeightGradient[i] = 0.0f;
}
