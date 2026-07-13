#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace bezier {

enum class SunShapeType : uint32_t { BUIE = 0, PILLBOX = 1, GAUSSIAN = 2 };

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
    float glassDepth = 0.003f;
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
    std::string influenceDataPath = "data";

    // B-spline dimensionality reduction (25 CPs -> 35 bolts)
    bool useBSpline = false;
    uint32_t numCpX = 5;
    uint32_t numCpZ = 5;

    // Initial bolt heights file (elliptic guess, overrides zero-init)
    std::string boltInitFile;
};

// Load config from JSON file, compute Buie constants
Config loadConfig(const std::string &path);
// Precompute sunshape integral = ∫ φ(θ)·sin(θ) dθ for energy normalization
float computeSunShapeIntegral(const Config &cfg);

} // namespace bezier
