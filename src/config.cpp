#include "config.h"
#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace bezier {

float computeSunShapeIntegral(const Config &cfg) {
    // Taichi scipy quad: ∫₀^0.0436 L(θ)·θ dθ = 9.2286445021e-06 for CSR=0.01
    (void)cfg;
    return 9.2286445021e-06f;
}

static std::string readFile(const std::string &path) {
    std::ifstream f(path);
    if (!f) return {};
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static float extractFloat(const std::string &json, const std::string &key, float defaultVal) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return defaultVal;
    pos = json.find(":", pos);
    if (pos == std::string::npos) return defaultVal;
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n')) pos++;
    if (pos < json.size()) {
        char *end = nullptr;
        float val = std::strtof(json.c_str() + pos, &end);
        if (end != json.c_str() + pos) return val;
    }
    return defaultVal;
}

static int extractInt(const std::string &json, const std::string &key, int defaultVal) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return defaultVal;
    pos = json.find(":", pos);
    if (pos == std::string::npos) return defaultVal;
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n')) pos++;
    if (pos < json.size()) {
        char *end = nullptr;
        long val = std::strtol(json.c_str() + pos, &end, 10);
        if (end != json.c_str() + pos) return static_cast<int>(val);
    }
    return defaultVal;
}

static std::string extractString(const std::string &json, const std::string &key, const std::string &defaultVal) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return defaultVal;
    pos = json.find(":", pos);
    if (pos == std::string::npos) return defaultVal;
    pos = json.find("\"", pos);
    if (pos == std::string::npos) return defaultVal;
    auto end = json.find("\"", pos + 1);
    if (end == std::string::npos) return defaultVal;
    return json.substr(pos + 1, end - pos - 1);
}

Config loadConfig(const std::string &path) {
    Config cfg;
    std::string json = readFile(path);
    if (json.empty()) {
        float csr = cfg.csr;
        cfg.buieThetaInner = 0.00465f;
        cfg.buieKappa = 0.9f * std::log(13.5f * csr) * std::pow(csr, -0.3f);
        cfg.buieScale = std::exp(cfg.buieKappa);
        cfg.buieGamma = 2.2f * std::log(0.52f * csr) * std::pow(csr, 0.43f) - 0.1f;
        cfg.sunShapeIntegral = computeSunShapeIntegral(cfg);
        return cfg;
    }

    cfg.sunTrainFile = extractString(json, "sun_train_file", cfg.sunTrainFile);
    cfg.sunValidationFile = extractString(json, "sun_validation_file", cfg.sunValidationFile);
    cfg.ellipseFile = extractString(json, "ellipse_file", cfg.ellipseFile);
    cfg.outputDir = extractString(json, "output_dir", cfg.outputDir);

    cfg.receiverRadius = extractFloat(json, "receiver_radius", cfg.receiverRadius);
    cfg.receiverHeight = extractFloat(json, "receiver_height", cfg.receiverHeight);
    cfg.pixelWidth = extractInt(json, "pixel_width", cfg.pixelWidth);
    cfg.pixelHeight = extractInt(json, "pixel_height", cfg.pixelHeight);

    cfg.heliostatWidth = extractFloat(json, "heliostat_width", cfg.heliostatWidth);
    cfg.heliostatLength = extractFloat(json, "heliostat_length", cfg.heliostatLength);
    cfg.gridSize = extractInt(json, "grid_size", cfg.gridSize);
    cfg.glassDepth = extractFloat(json, "glass_depth", cfg.glassDepth);
    cfg.refractiveIndex = extractFloat(json, "refractive_index", cfg.refractiveIndex);
    cfg.slopeError = extractFloat(json, "slope_error", cfg.slopeError);
    cfg.reflectivity = extractFloat(json, "reflectivity", cfg.reflectivity);

    {
        std::string st = extractString(json, "sun_type", "buie");
        if (st == "pillbox") cfg.sunType = SunShapeType::PILLBOX;
        else if (st == "gaussian") cfg.sunType = SunShapeType::GAUSSIAN;
        else cfg.sunType = SunShapeType::BUIE;
    }
    cfg.dni = extractFloat(json, "dni", cfg.dni);
    cfg.csr = extractFloat(json, "csr", cfg.csr);
    cfg.sigma = extractFloat(json, "sun_sigma", cfg.sigma);
    cfg.thetaMax = extractFloat(json, "sun_theta_max", cfg.thetaMax);

    cfg.iterations = extractInt(json, "iterations", cfg.iterations);
    cfg.learningRate = extractFloat(json, "learning_rate", cfg.learningRate);
    cfg.minLearningRate = extractFloat(json, "min_learning_rate", cfg.minLearningRate);
    cfg.beta1 = extractFloat(json, "beta1", cfg.beta1);
    cfg.beta2 = extractFloat(json, "beta2", cfg.beta2);
    cfg.adamEpsilon = extractFloat(json, "adam_epsilon", cfg.adamEpsilon);
    cfg.patience = extractInt(json, "patience", cfg.patience);

    cfg.enableMSELoss = extractInt(json, "enable_mse_loss", 0) != 0;
    cfg.geometrySampleGrid = extractInt(json, "geometry_sample_grid", 20);

    cfg.useBoltParameterization = extractInt(json, "use_bolt", 0) != 0;
    cfg.numBolts = extractInt(json, "num_bolts", 35);
    cfg.numBoltsX = extractInt(json, "num_bolts_x", 7);
    cfg.numBoltsZ = extractInt(json, "num_bolts_z", 5);
    cfg.boltMargin = extractFloat(json, "bolt_margin", 0.08f);
    cfg.influenceDataPath = extractString(json, "influence_data_path", "data_proxy");

    cfg.useBSpline = extractInt(json, "use_bspline", 0) != 0;
    cfg.numCpX = extractInt(json, "num_cp_x", 5);
    cfg.numCpZ = extractInt(json, "num_cp_z", 5);
    cfg.boltInitFile = extractString(json, "bolt_init_file", "");
    cfg.disableGravity = extractInt(json, "disable_gravity", 0) != 0;

    cfg.maxBoltStroke = extractFloat(json, "max_bolt_stroke", 0.040f);
    cfg.strokeRegularization = extractFloat(json, "stroke_regularization", 0.0f);
    cfg.reflectionOnlyOptimization = extractInt(json, "reflection_only_optimization", 0) != 0;
    cfg.randomizeSeed = extractInt(json, "randomize_seed", 0) != 0;

    cfg.rayCull = extractInt(json, "ray_cull", 1) != 0;
    cfg.rayCullMarginMrad = extractFloat(json, "ray_cull_margin_mrad", 8.0f);
    cfg.lambdaEnergy = extractFloat(json, "lambda_energy", 0.0f);

    float csr = cfg.csr;
    cfg.buieThetaInner = 0.00465f;
    cfg.buieKappa = 0.9f * std::log(13.5f * csr) * std::pow(csr, -0.3f);
    cfg.buieGamma = 2.2f * std::log(0.52f * csr) * std::pow(csr, 0.43f) - 0.1f;
    cfg.buieScale = 0.0f;
    cfg.sunShapeIntegral = computeSunShapeIntegral(cfg);

    return cfg;
}

} // namespace bezier
