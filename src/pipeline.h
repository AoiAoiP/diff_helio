#pragma once

#include "config.h"
#include "input.h"
#include "vulkan_app.h"
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace bezier {

struct OptimizationResult {
    std::vector<float> bestControlY;
    std::vector<float> lossHistory;
    std::vector<float> s95History;
    float initialS95 = 0.0f;
    float bestS95 = 0.0f;
};

class BezierPipeline {
public:
    BezierPipeline(VulkanApp &app, const Config &cfg);
    ~BezierPipeline();

    BezierPipeline(const BezierPipeline &) = delete;
    BezierPipeline &operator=(const BezierPipeline &) = delete;

    OptimizationResult optimize(const HeliostatConfig &hc,
                                 const std::vector<std::array<float, 3>> &trainDirs,
                                 const std::vector<std::array<float, 3>> &validationDirs,
                                 const std::string &overrideBoltInitFile = "");

    void verifyGradients(const std::vector<float> &initCY, const std::array<float, 3> &sunDir,
                         const std::array<float, 3> &helioPos, const std::array<float, 3> &aimPoint, float pixelArea);

    // Bolt-mode gradient verification: AD vs FD per-bolt
    void verifyBoltGradients(const std::array<float, 3> &sunDir,
                             const std::array<float, 3> &helioPos,
                             const std::array<float, 3> &aimPoint, float pixelArea);

    // WoS offline influence computation
    void computeWoSInfluence(const std::string &outputDir);

    // Public for --dump-flux and external use
    void createPipelines();
    void createBuffersAndTextures();
    void createBoltPipelines();
    void createBoltBuffers();
    void uploadHeliostatData(const std::vector<float> &initControlY);
    void uploadBoltData(const std::vector<float> &initBoltHeights);
    void updateUniforms(const std::array<float, 3> &sunDir, const std::array<float, 3> &helioPos,
                        const std::array<float, 3> &aimPoint);
    // A2: pack SunParams UBO contents (13 floats) for inline cmd-buffer updates
    void fillSunParams(const std::array<float, 3> &sunDir, float *sunp) const;
    void forwardRender(bool withBezier = true);
    void boltForwardSurface(float gravityScale);
    void boltForwardSurface(const std::vector<std::array<float,3>>& trainDirs,
        const std::array<float,3>& hp, const std::array<float,3>& ap, int batchStart, uint32_t batchCount);
    void uploadSurfaceFromFile(const std::string &path);  // bypass bolt, upload UY from file
    std::vector<float> readFlux();
    std::array<uint32_t, 6> getDiagCounts() const;  // read all diagnostic counters

private:
    void loadShaders();
    void backwardPass();

    static float computeMaxEnergy(const std::vector<float> &flux);
    static float computeTotalEnergy(const std::vector<float> &flux);
    static float computeSumAbove(const std::vector<float> &flux, float threshold);
    static float computeS95Level(const std::vector<float> &flux);

    float computeS95Loss(float s95Level);
    float computeLossGPU(float s95Level);
    uint32_t countS95PixelsGPU(float s95Level);
    void adamStep(uint32_t iteration);

    // Flux gradient management
    void clearFluxGradient();

    // Sampling
    void clearRayValidity();

    // A1: Sparse pixel culling — precompute receiver pixels facing the heliostat
    void buildActivePixelList(const std::array<float, 3> &hp);

    // Bolt-mode methods
    void loadBoltShaders();
    void boltBackwardPass();
    void boltAdamStep(uint32_t iteration);

    // Phase 2: Batched dispatch helpers (operate within existing command buffer)
    void boltForwardSurfaceCmd(VkCommandBuffer cmd, uint32_t batchCount);
    void forwardRenderCmd(VkCommandBuffer cmd);
    void clearRayValidityCmd(VkCommandBuffer cmd);
    void clearFluxGradientCmd(VkCommandBuffer cmd);
    void computeS95LossCmd(VkCommandBuffer cmd, float s95Level);
    void boltBackwardPassCmd(VkCommandBuffer cmd);

    // B-spline CP optimization
    void loadBSplineMatrix();
    void cpToBoltHeights();
    void boltGradToCpGrad();
    void cpAdamStep(uint32_t iteration);

    std::vector<uint32_t> loadSpv(const std::string &name);

    VulkanApp &m_app;
    Config m_cfg;
    uint32_t m_totalPixels = 0;
    uint32_t m_totalSpp = 0;
    uint32_t m_totalRays = 0;
    // Phase 1: m_poolSize removed — gaussianPool eliminated
    uint32_t m_totalBackwardGroups = 0;

    // SPIR-V (Bezier mode)
    std::vector<uint32_t> m_spvBezier, m_spvForward, m_spvClear, m_spvFinalize, m_spvBackward,
                         m_spvBackwardReduce, m_spvLoss, m_spvCount, m_spvAdam,
                         m_spvLossPartial, m_spvLossFinal, m_spvClearFluxGrad;

    // SPIR-V (Bolt mode)
    std::vector<uint32_t> m_spvBoltSurface, m_spvBoltBackward, m_spvBoltBackwardReduce,
                         m_spvBoltProject, m_spvBoltClearSurface, m_spvBoltAdam;

    // Pipelines (Bezier mode)
    ComputePipeline m_pipeBezier, m_pipeForward, m_pipeClear, m_pipeFinalize,
                    m_pipeBackward, m_pipeBackwardReduce, m_pipeLoss, m_pipeAdam, m_pipeCount,
                    m_pipeLossPartial, m_pipeLossFinal, m_pipeClearFluxGrad;

    // Pipelines (Bolt mode)
    ComputePipeline m_pipeBoltSurface, m_pipeBoltBackward, m_pipeBoltBackwardReduce,
                    m_pipeBoltProject, m_pipeBoltClearSurface, m_pipeBoltAdam;

    // GPU resources (shared)
    GpuBuffer m_yGrid, m_nGrid, m_s95CountBuf, m_fluxPartial;  // Phase1: m_gaussianPool removed
    GpuTexture m_renderedFlux, m_fluxGradient;
    GpuBuffer m_uboReceiver, m_uboHeliostat, m_uboSun, m_uboHelioPos, m_uboAimPoint;

    // Bezier-mode GPU resources
    GpuBuffer m_controlY, m_controlYGradient, m_adamM, m_adamV;
    GpuBuffer m_gradPartial;

    // Bolt-mode GPU resources
    GpuBuffer m_boltHeights, m_boltHeightGradient, m_boltAdamM, m_boltAdamV;
    GpuBuffer m_influencePhi, m_influencePhiU, m_influencePhiV;
    // Sampling (P0-P3)
    GpuBuffer m_rayValidity;
    // A1: Sparse pixel culling — compacted active pixel index list (binding 55)
    GpuBuffer m_activePixelList;
    uint32_t m_activePixelCount = 0;
    // Phase 1: m_samplePoolSize/Mask/Pow removed — gaussianPool eliminated

    // B-spline CP optimization (CPU-side)
    std::vector<float> m_bsplineT;    // T matrix [(n_bolts) × (n_cp)], row-major
    std::vector<float> m_cpHeights;   // CP heights (n_cp)
    std::vector<float> m_cpGradient;  // CP gradient (n_cp)
    std::vector<float> m_cpAdamM;     // CP Adam M (n_cp)
    std::vector<float> m_cpAdamV;     // CP Adam V (n_cp)
    int m_nCp = 0;                    // total CP count = nCpX * nCpZ

    // MSE loss: ideal flux target from elliptical surface
    bool m_useMSELoss = false;
    std::vector<float> m_idealFlux;
    GpuBuffer m_gravityY, m_gravityBins[20], m_yuGrid, m_yvGrid, m_surfaceGradient;
    GpuBuffer m_tirCountBuf;  // TIR fallback statistics (1 uint32)
    // Phase 5: m_boltGradPartial removed — replaced by 12 KB m_boltGradPartialTile
    GpuBuffer m_boltGradPartialTile;
    GpuBuffer m_dummyBuf; // small dummy buffer for unused bindings
    GpuBuffer m_sunBatchFlat; // Phase 2: sun batch data (binding 41)
    std::array<float,3> m_lastSunDir = {0,1,0};
    static constexpr uint32_t kSunBatchSize = 6;

    // Descriptor layouts (one shared Bezier layout, one shared bolt layout)
    VkDescriptorSetLayout m_boltSetLayout = VK_NULL_HANDLE;
    VkDescriptorSet m_boltDescriptorSet = VK_NULL_HANDLE;

    bool m_pipelinesCreated = false;
    bool m_buffersCreated = false;
    bool m_boltPipelinesCreated = false;
    bool m_boltBuffersCreated = false;
};

} // namespace bezier
