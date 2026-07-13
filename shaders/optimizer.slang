// optimizer.slang — Adam optimizer for 4×4 Bezier control points
// Reads gradient from binding 16 (controlYGradientOut), writes updated controlY to binding 5.
static const uint kControlCount = 16u;

[[vk::binding(5)]]  RWStructuredBuffer<float> controlY;
[[vk::binding(13)]] RWStructuredBuffer<float> adamM;
[[vk::binding(14)]] RWStructuredBuffer<float> adamV;
[[vk::binding(16)]] RWStructuredBuffer<float> controlYGradient;

struct AdamPC { float lr; float beta1; float beta2; float eps; float iterF; };
[[vk::push_constant]] AdamPC pc;

[shader("compute")]
[numthreads(kControlCount, 1, 1)]
void adamUpdate(uint3 tid : SV_DispatchThreadID) {
    uint i = tid.x;
    if (i >= kControlCount) return;

    float grad = controlYGradient[i];
    float m = pc.beta1 * adamM[i] + (1.0f - pc.beta1) * grad;
    float v = pc.beta2 * adamV[i] + (1.0f - pc.beta2) * grad * grad;
    adamM[i] = m;
    adamV[i] = v;

    float mHat = m / (1.0f - pow(pc.beta1, pc.iterF));
    float vHat = v / (1.0f - pow(pc.beta2, pc.iterF));
    controlY[i] -= pc.lr * mHat / (sqrt(vHat) + pc.eps);
    controlYGradient[i] = 0.0f; // reset gradient for next iteration
}
