// sunshape.slang — Differentiable sun shape models (Buie / Pillbox / Gaussian)
// Shape values are RAW (not normalized). Energy formula applies 1/(2π·integral·spp).
// Sun shape type constants kSunshape* are defined in common.slang.
module sunshape;
import common;

static const float kPillboxSmoothWidthRatio = 0.1f;
static const float kPillboxMinSmoothWidth   = 1.0e-4f;

float noDiffIdentity(float x) { return x; }

// ---- Buie (2-region with outer cutoff at 0.0436 rad, matching Taichi) ----
// shapeParams: x=theta_inner(0.00465), y=kappa, z=gamma, w=unused
[Differentiable]
public float computeSunshapeBuie(float sunTheta, no_diff float4 shapeParams) {
    if (sunTheta <= 0.00465f) {
        return cos(326.0f * sunTheta) / cos(308.0f * sunTheta);
    }
    if (sunTheta <= 0.0436f) {
        return exp(shapeParams.y) * pow(sunTheta * 1000.0f, shapeParams.z);
    }
    return 0.0f;
}

// ---- Pillbox (smoothed step for differentiability) ----
// shapeParams layout: x = theta_max
[Differentiable]
public float computeSunshapePillbox(float sunTheta, no_diff float4 shapeParams) {
    float thetaMax   = shapeParams.x;
    float smoothHalf = max(thetaMax * kPillboxSmoothWidthRatio, kPillboxMinSmoothWidth);
    float t = saturate((sunTheta - (thetaMax - smoothHalf)) / max(2.0f * smoothHalf, 1.0e-6f));
    float smooth = 1.0f - t * t * (3.0f - 2.0f * t);
    float hard   = sunTheta <= thetaMax ? 1.0f : 0.0f;
    return hard + smooth - no_diff(noDiffIdentity(smooth));
}

// ---- Gaussian ----
// shapeParams layout: x = sigma
[Differentiable]
public float computeSunshapeGaussian(float sunTheta, no_diff float4 shapeParams) {
    float sigma = shapeParams.x;
    return exp(-(sunTheta * sunTheta) / max(2.0f * sigma * sigma, 1.0e-6f));
}

// ---- Generic dispatch ----
[Differentiable]
public float computeSunshape(float sunTheta, float4 shapeParams, float type) {
    if (type > 1.5f)  return computeSunshapeGaussian(sunTheta, shapeParams);
    if (type > 0.5f)  return computeSunshapePillbox(sunTheta, shapeParams);
    return computeSunshapeBuie(sunTheta, shapeParams);
}
