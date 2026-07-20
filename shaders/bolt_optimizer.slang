// bolt_optimizer.slang — Adam optimizer for N bolt heights
// P1-L4: Tanh-bounded parameterization — Adam operates on unbounded eps,
// physical heights are h = h_max * tanh(eps). This enforces |h| < h_max
// with no projection, and gradients naturally soften near the boundary.
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
    float hMax;          // P1-L4: max bolt stroke (m), tanh bound
    float lambdaStroke;  // P1-L4: stroke regularization weight (0 = disabled)
};
[[vk::push_constant]] AdamBoltPC pc;

[shader("compute")]
[numthreads(kMaxBolts, 1, 1)]
void adamUpdateBolt(uint3 tid : SV_DispatchThreadID) {
    uint i = tid.x;
    if (i >= pc.numBolts) return;

    float h_b = boltHeights[i];

    // P1-L4: recover unbounded variable from physical height
    // Each iteration starts from the last physical height, maps back to eps
    // via atanh, updates in eps space, then maps back. This ensures the
    // Adam moments track the unbounded variable (not the bounded physical one).
    float hMax = max(pc.hMax, 1e-6f);
    float ratio = clamp(h_b / hMax, -0.999f, 0.999f);
    float eps_b = atanh(ratio);

    // Chain rule: dL/d(eps) = dL/dh * dh/d(eps)
    // dh/d(eps) = hMax * (1 - tanh^2(eps)) = hMax * (1 - ratio^2)
    float dh_deps = hMax * (1.0f - ratio * ratio);
    float grad_eps = boltHeightGradient[i] * dh_deps;

    // P1-L4: optional stroke regularization L_reg = lambda * ||h||^2
    // dL_reg/d(eps) = 2 * lambda * h * dh/d(eps)
    if (pc.lambdaStroke > 0.0f) {
        grad_eps += 2.0f * pc.lambdaStroke * h_b * dh_deps;
    }

    // Adam update in epsilon space (unbounded)
    float m = pc.beta1 * adamM[i] + (1.0f - pc.beta1) * grad_eps;
    float v = pc.beta2 * adamV[i] + (1.0f - pc.beta2) * grad_eps * grad_eps;
    adamM[i] = m;
    adamV[i] = v;

    float mHat = m / (1.0f - pow(pc.beta1, pc.iterF));
    float vHat = v / (1.0f - pow(pc.beta2, pc.iterF));
    eps_b -= pc.lr * mHat / (sqrt(vHat) + pc.eps);

    // Map back to physical space
    boltHeights[i] = hMax * tanh(eps_b);
    boltHeightGradient[i] = 0.0f;
}
