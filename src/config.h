#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace bezier {

enum class SunShapeType : uint32_t { BUIE = 0, PILLBOX = 1, GAUSSIAN = 2 };
enum class ProxyMode : uint32_t { TPS = 0, POD_LINEAR = 1, POD_MLP = 2 };

struct Config {
    // Files
    std::string sunTrainFile = "data/36_sundir_fast.txt";
    std::string sunValidationFile = "data/738_sundir_year.txt";
    std::string ellipseFile = "data/ellipse.txt";
    std::string outputDir = "results";

    // Receiver
    std::array<float, 3> receiverPosition = {0.0f, 180.0f, 0.0f};
    float receiverRadius = 10.0f;
    float receiverHeight = 20.0f;
    uint32_t pixelWidth = 157;
    uint32_t pixelHeight = 50;

    // Heliostat
    float heliostatWidth = 12.84f;
    float heliostatLength = 9.45f;
    uint32_t gridSize = 32;
    float glassDepth = 0.004f;
    float refractiveIndex = 1.523f;
    float slopeError = 0.001f;
    float reflectivity = 0.88f;

    // Sun
    SunShapeType sunType = SunShapeType::BUIE;
    float dni = 1000.0f;
    float csr = 0.01f;
    float sigma = 0.00251f;     // Gaussian sigma (radians)
    float thetaMax = 0.00465f;  // Pillbox half-angle (radians)
    // Buie model: 4-component shapeParams = {thetaInner, kappa, scale, gamma}
    float buieThetaInner = 0.00465f;
    float buieKappa = 0.0f;
    float buieScale = 0.0f;
    float buieGamma = 0.0f;
    // Sunshape integral (precomputed numerically)
    float sunShapeIntegral = 0.0f;

    // Optimization
    uint32_t iterations = 200;
    float learningRate = 1e-5f;
    float minLearningRate = 1e-7f;
    float beta1 = 0.9f;
    float beta2 = 0.999f;
    float adamEpsilon = 1e-8f;
    int patience = 15;

    // Sampling
    uint32_t randomSeed = 12345;
    uint32_t samplePoolPow = 25;  // 2^25 = 33,554,432 floats

    // Physics-informed loss terms (all disabled by default)
    uint32_t geometrySampleGrid = 20;

    // Bolt parameterization (bolt mode replaces Bezier CP with bolt heights)
    bool useBoltParameterization = false;
    uint32_t numBolts = 35;
    uint32_t numBoltsX = 7;
    uint32_t numBoltsZ = 5;
    float boltMargin = 0.08f;              // edge margin fraction (0..0.5)
    bool enableMSELoss = false;          // MSE loss: match ideal elliptical flux pixel-by-pixel
    bool disableGravity = false;       // if true, zero out gravity in proxy model
    // P1: gravity normal coupling — derivatives enter surface normal (0=legacy phantom)
    bool gravityNormalCoupling = true;
    std::string influenceDataPath = "data_proxy";
    ProxyMode proxyMode = ProxyMode::TPS;

    // B-spline dimensionality reduction (25 CPs -> 35 bolts)
    bool useBSpline = false;
    uint32_t numCpX = 5;
    uint32_t numCpZ = 5;

    // Initial bolt heights file (elliptic guess, overrides zero-init)
    std::string boltInitFile;
    // Directory prefix for bolt init files when bolt_init_file="auto"
    std::string boltInitDir = "data/init/";

    // P1-L4: max bolt stroke for tanh bounded parameterization (m)
    float maxBoltStroke = 0.040f;
    // P1-L4: stroke regularization weight (0 = disabled)
    float strokeRegularization = 0.0f;
    // P1-A3: use reflection-only optics for ablation study (default false = full optics)
    bool reflectionOnlyOptimization = false;
    // P1-L3: per-iteration seed randomization (0 = fixed seed, 1 = randomize)
    bool randomizeSeed = false;

    // P3: Regularization suite (activated in Phase 3, declared now)
    float anchorLambda = 0.0f;         // lambda_s: shape anchor strength
    float bendLambda = 0.0f;            // lambda_b: bending energy strength
    float softStrokeLambda = 0.0f;      // lambda_h: soft stroke wall strength
    bool tanhBound = true;              // 1=legacy tanh; 0=physical space + soft wall
    // Phase 5.4: L1 (LASSO) proximal strength on bolt strokes for sparse
    // layout optimization. 0 = disabled (bit-exact legacy behavior).
    float boltL1Lambda = 0.0f;
    // Phase 5.4 (A3): dump per-sun surface gradients at the last iteration
    // (surface_grad_{Mirror}.bin + _meta.csv in outputDir). 0 = off.
    int dumpSurfaceGrad = 0;

    // A1: per-ray angular pre-cull — skip Box-Muller + glass + sunshape for
    // rays whose macro-normal reflection falls outside sun support + margin
    // (their true energy contribution is zero). cos cutoff is passed in the
    // SunParams UBO; disable for bit-exact A/B against the old path.
    bool rayCull = true;
    float rayCullMarginMrad = 8.0f;

    // L1: efficiency term weight lambda for L_eff = lambda * M * E_ref / E
    // (ARCAim-style scale-invariant energy guard; M = receiver pixel count
    // keeps lambda ~ O(1) against the sigmoid sum). E_ref is the per-sun
    // total flux captured at iteration 0. 0 disables (bit-exact S95-only).
    float lambdaEnergy = 0.0f;
};

// Load config from JSON file, compute Buie constants
Config loadConfig(const std::string &path);
// Precompute sunshape integral = ∫ φ(θ)·sin(θ) dθ for energy normalization
float computeSunShapeIntegral(const Config &cfg);

} // namespace bezier
