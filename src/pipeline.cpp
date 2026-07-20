#include "pipeline.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <fmt/core.h>
namespace fs = std::filesystem;

namespace bezier {

std::vector<uint32_t> BezierPipeline::loadSpv(const std::string &name) {
    std::string path = "shaders/" + name + ".spv";
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f) throw std::runtime_error("Cannot open: " + path + ". Run from project root.");
    size_t size = f.tellg();
    f.seekg(0);
    std::vector<uint32_t> result(size / sizeof(uint32_t));
    f.read(reinterpret_cast<char *>(result.data()), size);
    return result;
}

BezierPipeline::BezierPipeline(VulkanApp &app, const Config &cfg) : m_app(app), m_cfg(cfg) {
    m_totalPixels = cfg.pixelWidth * cfg.pixelHeight;
    m_totalSpp = cfg.gridSize * cfg.gridSize;
    m_totalRays = m_totalPixels * m_totalSpp;
    // Phase 1: pool size computation removed — inline Box-Muller needs no lookup table
    uint32_t tileCount = (m_totalSpp + 255) / 256;
    m_totalBackwardGroups = m_totalPixels * tileCount;
    loadShaders();
    if (cfg.useBoltParameterization) loadBoltShaders();
}

BezierPipeline::~BezierPipeline() {
    if (!m_pipelinesCreated) return;
    // All pipelines share the same descriptor set layout — only destroy once.
    // First destroy the layout via any pipeline, then clean up the rest manually.
    auto destroyPipeNoLayout = [this](ComputePipeline &p) {
        if (p.pipeline) { vkDestroyPipeline(m_app.device(), p.pipeline, nullptr); p.pipeline = VK_NULL_HANDLE; }
        if (p.layout)    { vkDestroyPipelineLayout(m_app.device(), p.layout, nullptr);    p.layout = VK_NULL_HANDLE; }
    };
    // Destroy shared layout once
    if (m_pipeForward.setLayout) {
        vkDestroyDescriptorSetLayout(m_app.device(), m_pipeForward.setLayout, nullptr);
        m_pipeForward.setLayout = VK_NULL_HANDLE;
    }
    destroyPipeNoLayout(m_pipeBezier);
    destroyPipeNoLayout(m_pipeForward);
    for (int i = 0; i < 3; i++) destroyPipeNoLayout(m_pipeForwardTyped[i]);  // P1-A2
    destroyPipeNoLayout(m_pipeClear);
    destroyPipeNoLayout(m_pipeBackward);
    destroyPipeNoLayout(m_pipeBackwardReduce);
    destroyPipeNoLayout(m_pipeLoss);
    destroyPipeNoLayout(m_pipeCount);
    destroyPipeNoLayout(m_pipeLossPartial);
    destroyPipeNoLayout(m_pipeLossFinal);
    destroyPipeNoLayout(m_pipeAdam);
    destroyPipeNoLayout(m_pipeClearFluxGrad);

    // Bolt pipelines (separate layout)
    if (m_pipeBoltSurface.layout) {
        vkDestroyDescriptorSetLayout(m_app.device(), m_pipeBoltSurface.setLayout, nullptr);
        m_pipeBoltSurface.setLayout = VK_NULL_HANDLE;
    }
    destroyPipeNoLayout(m_pipeBoltSurface);
    destroyPipeNoLayout(m_pipeBoltBackward);
    for (int i = 0; i < 3; i++) destroyPipeNoLayout(m_pipeBoltBackwardTyped[i]);  // P1-A2
    destroyPipeNoLayout(m_pipeBoltBackwardReduce);
    destroyPipeNoLayout(m_pipeBoltProject);
    destroyPipeNoLayout(m_pipeBoltClearSurface);
    destroyPipeNoLayout(m_pipeBoltAdam);

    // Bolt descriptor set layout (if created separately)
    if (m_boltSetLayout) {
        vkDestroyDescriptorSetLayout(m_app.device(), m_boltSetLayout, nullptr);
        m_boltSetLayout = VK_NULL_HANDLE;
    }
}

void BezierPipeline::loadShaders() {
    m_spvBezier   = loadSpv("computeBezierSurface");
    m_spvForward  = loadSpv("renderForward");
    m_spvClear    = loadSpv("clearFlux");
    m_spvFinalize = loadSpv("finalizeFlux");
    m_spvBackward = loadSpv("renderBackward");
    m_spvBackwardReduce = loadSpv("reduceBackwardGradients");
    m_spvLoss     = loadSpv("computeS95Loss");
    m_spvCount    = loadSpv("countS95Simple");
    m_spvLossPartial = loadSpv("reduceLossPartial");
    m_spvLossFinal   = loadSpv("reduceLossFinal");
    m_spvAdam     = loadSpv("adamUpdate");
    m_spvClearFluxGrad = loadSpv("clearFluxGradient");
}

void BezierPipeline::loadBoltShaders() {
    m_spvBoltSurface   = loadSpv("computeBoltSurface");
    m_spvBoltBackward  = loadSpv("renderBackwardBolt");
    m_spvBoltBackwardReduce = loadSpv("reduceSurfaceGradients");
    m_spvBoltProject   = loadSpv("projectBoltGradients");
    m_spvBoltClearSurface = loadSpv("clearSurfaceGradient");
    m_spvBoltAdam      = loadSpv("adamUpdateBolt");
    m_spvS95FindLevel  = loadSpv("computeS95FindLevel");
    m_spvS95LossBUF    = loadSpv("computeS95LossBUF");
    // P1-A2: specialized sunshape variants
    m_spvForwardTyped[0]  = loadSpv("renderForwardBuie");
    m_spvForwardTyped[1]  = loadSpv("renderForwardPillbox");
    m_spvForwardTyped[2]  = loadSpv("renderForwardGaussian");
    m_spvBoltBackwardTyped[0] = loadSpv("renderBackwardBoltBuie");
    m_spvBoltBackwardTyped[1] = loadSpv("renderBackwardBoltPillbox");
    m_spvBoltBackwardTyped[2] = loadSpv("renderBackwardBoltGaussian");
}

void BezierPipeline::createPipelines() {
    if (m_pipelinesCreated) return;

    auto sb = [](uint32_t b, VkDescriptorType t = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER) -> VkDescriptorSetLayoutBinding {
        return {b, t, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
    };

    std::vector<VkDescriptorSetLayoutBinding> allBindings;
    // Uniform buffers: 0-4
    for (uint32_t i = 0; i <= 4; i++)
        allBindings.push_back(sb(i, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER));
    // Storage buffers: 5-7, 9, 11, 13-16
    allBindings.push_back(sb(5));   // controlY
    allBindings.push_back(sb(6));   // yGrid
    allBindings.push_back(sb(7));   // nGrid
    // Storage images: 8, 12
    allBindings.push_back({8, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr});
    allBindings.push_back(sb(9));   // gaussianPool
    allBindings.push_back(sb(10));  // fluxAtomic
    allBindings.push_back(sb(11));  // gradPartial
    allBindings.push_back({12, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr});
    allBindings.push_back(sb(13));  // adamM
    allBindings.push_back(sb(14));  // adamV
    allBindings.push_back(sb(15));  // s95CountBuf / debugBuf
    allBindings.push_back(sb(16));  // controlYGradientOut
    allBindings.push_back(sb(29));  // rayValidity (P2)
    allBindings.push_back(sb(31));  // tirCountBuf (TIR statistics)
    allBindings.push_back(sb(55));  // activePixelList (A1: sparse culling)

    VkDescriptorSetLayout sharedLayout = VK_NULL_HANDLE;
    {
        VkDescriptorSetLayoutCreateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        info.bindingCount = static_cast<uint32_t>(allBindings.size());
        info.pBindings = allBindings.data();
        checkVk(vkCreateDescriptorSetLayout(m_app.device(), &info, nullptr, &sharedLayout), "shared set layout");
    }

    VkDescriptorSet sharedSet = VK_NULL_HANDLE;
    {
        VkDescriptorSetAllocateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        info.descriptorPool = m_app.descriptorPool();
        info.descriptorSetCount = 1;
        info.pSetLayouts = &sharedLayout;
        checkVk(vkAllocateDescriptorSets(m_app.device(), &info, &sharedSet), "shared descriptor set");
    }

    auto createPipe = [&](std::span<const uint32_t> spv, const char *entry, uint32_t pcSize) -> ComputePipeline {
        ComputePipeline p;
        p.setLayout = sharedLayout;
        p.descriptorSets.resize(1);
        p.descriptorSets[0] = sharedSet;

        VkPipelineLayoutCreateInfo linfo{};
        linfo.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        linfo.setLayoutCount = 1;
        linfo.pSetLayouts = &sharedLayout;
        VkPushConstantRange pcRange{};
        if (pcSize > 0) {
            pcRange.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
            pcRange.size = pcSize;
            linfo.pushConstantRangeCount = 1;
            linfo.pPushConstantRanges = &pcRange;
        }
        checkVk(vkCreatePipelineLayout(m_app.device(), &linfo, nullptr, &p.layout), "pipeline layout");

        VkShaderModuleCreateInfo sinfo{};
        sinfo.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        sinfo.codeSize = spv.size() * sizeof(uint32_t);
        sinfo.pCode = spv.data();
        VkShaderModule sm;
        checkVk(vkCreateShaderModule(m_app.device(), &sinfo, nullptr, &sm), "shader module");

        VkComputePipelineCreateInfo pinfo{};
        pinfo.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
        pinfo.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        pinfo.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        pinfo.stage.module = sm;
        pinfo.stage.pName = entry;
        pinfo.layout = p.layout;
        checkVk(vkCreateComputePipelines(m_app.device(), VK_NULL_HANDLE, 1, &pinfo, nullptr, &p.pipeline), "pipeline");

        vkDestroyShaderModule(m_app.device(), sm, nullptr);
        return p;
    };

    m_pipeBezier   = createPipe(m_spvBezier,   "main", 0);
    m_pipeForward  = createPipe(m_spvForward,  "main", 0);
    m_pipeClear    = createPipe(m_spvClear,    "main", 0);
    m_pipeFinalize = createPipe(m_spvFinalize, "main", 0);
    m_pipeBackward = createPipe(m_spvBackward, "main", 0);
    m_pipeBackwardReduce = createPipe(m_spvBackwardReduce, "main", 0);
    m_pipeLoss     = createPipe(m_spvLoss,     "main", sizeof(float));
    m_pipeCount    = createPipe(m_spvCount,    "main", sizeof(float));
    m_pipeLossPartial = createPipe(m_spvLossPartial, "main", sizeof(float));
    m_pipeLossFinal   = createPipe(m_spvLossFinal,   "main", 0);
    m_pipeAdam     = createPipe(m_spvAdam,     "main", sizeof(float) * 5);
    m_pipeClearFluxGrad = createPipe(m_spvClearFluxGrad, "main", 0);

    m_pipelinesCreated = true;
}

void BezierPipeline::createBuffersAndTextures() {
    if (m_buffersCreated) return;

    m_controlY = m_app.createBuffer(16 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    uint32_t gridPts = m_cfg.gridSize * m_cfg.gridSize;
    m_yGrid    = m_app.createBuffer(kSunBatchSize * gridPts * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
    m_nGrid    = m_app.createBuffer(kSunBatchSize * gridPts * 4 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);

    // Phase 1: gaussianPool removed — inline Box-Muller replaces precomputed Sobol pool.
    // This saves ~1.5 GB GPU memory and eliminates ~11.6B global memory reads per iteration.

    // P2: Ray validity cache (1 bit per ray)
    m_rayValidity = m_app.createBuffer(((m_totalRays + 31u) / 32u) * sizeof(uint32_t),
                                        VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);

    // A1: Active pixel list (sparse culling). Device-local — read once per
    // workgroup in the hot render loops (host-visible here costs a PCIe round
    // trip per workgroup). Defaults to identity mapping so every path that
    // skips buildActivePixelList() keeps full-dispatch behavior.
    m_activePixelList = m_app.createBuffer(m_totalPixels * sizeof(uint32_t),
                                            VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
    {
        std::vector<uint32_t> identity(m_totalPixels);
        for (uint32_t i = 0; i < m_totalPixels; i++) identity[i] = i;
        m_app.uploadBuffer(m_activePixelList, identity.data(), m_totalPixels * sizeof(uint32_t));
    }
    m_activePixelCount = m_totalPixels;

    // Multi-sun batch: renderedFlux & fluxGradient hold 36 sun-frames each.
    // Switched from RWTexture2D to RWStructuredBuffer to allow sunIndex linear indexing.
    m_renderedFlux = m_app.createTexture(m_cfg.pixelWidth, m_cfg.pixelHeight, VK_FORMAT_R32_SFLOAT,
                                         VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
    m_fluxGradient = m_app.createTexture(m_cfg.pixelWidth, m_cfg.pixelHeight, VK_FORMAT_R32_SFLOAT,
                                          VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT);

    // Gradient + Adam state
    m_controlYGradient = m_app.createBuffer(16 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_adamM = m_app.createBuffer(16 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_adamV = m_app.createBuffer(16 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_s95CountBuf = m_app.createBuffer(256, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT, true);
    m_tirCountBuf = m_app.createBuffer(6 * sizeof(uint32_t), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT, true);
    // fluxPartial holds one partial-sum slot per (pixel, tile). Tile count =
    // ceil(totalSpp/256) and grows with grid resolution (3 at 25x25, 4 at 32x32).
    // Must match kTileCount in forward.slang — hardcoding 3 dropped tile-3 energy
    // and corrupted neighbor pixels at 32x32.
    uint32_t fluxTileCount = (m_totalSpp + 255u) / 256u;
    m_fluxPartial = m_app.createBuffer(kSunBatchSize * m_totalPixels * fluxTileCount * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);

    // Partial gradient accumulation buffer (per-group × 16 floats)
    m_gradPartial = m_app.createBuffer(m_totalBackwardGroups * 16 * sizeof(float),
                                        VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);

    // ---- Uniform buffers (tight packing, matching spirv-cross verified layout) ----
    // Binding 0: ReceiverParams (40 bytes = 10 floats)
    m_uboReceiver = m_app.createBuffer(10 * sizeof(float), VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, true);
    // Binding 1: HeliostatParams (44 bytes = 11 floats; P4: +2 for culling dir)
    m_uboHeliostat = m_app.createBuffer(11 * sizeof(float), VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, true);
    // Binding 2: SunParams (52 bytes = 13 floats; was 36 = 9 floats)
    m_uboSun = m_app.createBuffer(13 * sizeof(float), VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, true);
    // Binding 3: heliostatPosition float3 (12 bytes)
    m_uboHelioPos = m_app.createBuffer(3 * sizeof(float), VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, true);
    // Binding 4: aimPoint float3 (12 bytes)
    m_uboAimPoint = m_app.createBuffer(3 * sizeof(float), VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT, true);

    // ---- Bind all descriptors ----
    VkDescriptorSet set = m_pipeForward.descriptorSets[0];

    VkDescriptorBufferInfo uboInfos[] = {
        {m_uboReceiver.buffer, 0, m_uboReceiver.size},
        {m_uboHeliostat.buffer, 0, m_uboHeliostat.size},
        {m_uboSun.buffer, 0, m_uboSun.size},
        {m_uboHelioPos.buffer, 0, m_uboHelioPos.size},
        {m_uboAimPoint.buffer, 0, m_uboAimPoint.size},
    };

    VkDescriptorBufferInfo sbufInfos[] = {
        {m_controlY.buffer, 0, m_controlY.size},             // 5
        {m_yGrid.buffer, 0, m_yGrid.size},                   // 6
        {m_nGrid.buffer, 0, m_nGrid.size},                   // 7
        {m_s95CountBuf.buffer, 0, 4},                        // 9 (was gaussianPool, Phase 1: dummy)
        {m_fluxPartial.buffer, 0, m_fluxPartial.size},       // 10
        {m_gradPartial.buffer, 0, m_gradPartial.size},       // 11
        {m_adamM.buffer, 0, m_adamM.size},                   // 13
        {m_adamV.buffer, 0, m_adamV.size},                   // 14
        {m_s95CountBuf.buffer, 0, m_s95CountBuf.size},       // 15
        {m_controlYGradient.buffer, 0, m_controlYGradient.size}, // 16
        {m_rayValidity.buffer, 0, m_rayValidity.size},       // 29
        {m_tirCountBuf.buffer, 0, m_tirCountBuf.size},       // 31
        {m_activePixelList.buffer, 0, m_activePixelList.size}, // 55 (A1: sparse culling)
    };

    VkDescriptorImageInfo imgInfos[] = {
        {VK_NULL_HANDLE, m_renderedFlux.view, VK_IMAGE_LAYOUT_GENERAL},  // 8
        {VK_NULL_HANDLE, m_fluxGradient.view, VK_IMAGE_LAYOUT_GENERAL},  // 12
    };

    std::vector<VkWriteDescriptorSet> writes(20);
    for (int i = 0; i < 20; i++) {
        writes[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[i].dstSet = set;
        writes[i].dstArrayElement = 0;
        writes[i].descriptorCount = 1;
    }
    for (int i = 0; i < 5; i++) {
        writes[i].dstBinding = (uint32_t)i;
        writes[i].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        writes[i].pBufferInfo = &uboInfos[i];
    }
    writes[5].dstBinding  = 5;  writes[5].descriptorType  = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[5].pBufferInfo  = &sbufInfos[0];
    writes[6].dstBinding  = 6;  writes[6].descriptorType  = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[6].pBufferInfo  = &sbufInfos[1];
    writes[7].dstBinding  = 7;  writes[7].descriptorType  = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[7].pBufferInfo  = &sbufInfos[2];
    writes[8].dstBinding  = 8;  writes[8].descriptorType  = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE;   writes[8].pImageInfo   = &imgInfos[0];
    writes[9].dstBinding  = 9;  writes[9].descriptorType  = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[9].pBufferInfo  = &sbufInfos[3];
    writes[10].dstBinding  = 10; writes[10].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[10].pBufferInfo = &sbufInfos[4];
    writes[11].dstBinding  = 11; writes[11].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[11].pBufferInfo = &sbufInfos[5];
    writes[12].dstBinding  = 12; writes[12].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE;   writes[12].pImageInfo  = &imgInfos[1];
    writes[13].dstBinding  = 13; writes[13].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[13].pBufferInfo = &sbufInfos[6];
    writes[14].dstBinding  = 14; writes[14].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[14].pBufferInfo = &sbufInfos[7];
    writes[15].dstBinding  = 15; writes[15].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[15].pBufferInfo = &sbufInfos[8];
    writes[16].dstBinding  = 16; writes[16].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[16].pBufferInfo = &sbufInfos[9];
    writes[17].dstBinding  = 29; writes[17].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[17].pBufferInfo = &sbufInfos[10];
    writes[18].dstBinding  = 31; writes[18].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[18].pBufferInfo = &sbufInfos[11];  // tirCountBuf
    writes[19].dstBinding  = 55; writes[19].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[19].pBufferInfo = &sbufInfos[12];  // activePixelList (A1)

    fmt::print("  [diag] binding 31: buf=0x{:x}, size={}, writes_cnt={}\n",
               (uint64_t)m_tirCountBuf.buffer, m_tirCountBuf.size, writes.size());


    vkUpdateDescriptorSets(m_app.device(), static_cast<uint32_t>(writes.size()), writes.data(), 0, nullptr);

    m_buffersCreated = true;
}

void BezierPipeline::uploadHeliostatData(const std::vector<float> &initCY) {
    m_app.uploadBuffer(m_controlY, initCY.data(), 16 * sizeof(float));
    std::vector<float> z16(16, 0.0f);
    m_app.uploadBuffer(m_controlYGradient, z16.data(), 16 * sizeof(float));
    m_app.uploadBuffer(m_adamM, z16.data(), 16 * sizeof(float));
    m_app.uploadBuffer(m_adamV, z16.data(), 16 * sizeof(float));
}

// ---- Bolt-mode methods ----

void BezierPipeline::createBoltPipelines() {
    if (m_boltPipelinesCreated) return;

    auto sb = [](uint32_t b, VkDescriptorType t = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER) -> VkDescriptorSetLayoutBinding {
        return {b, t, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
    };

    std::vector<VkDescriptorSetLayoutBinding> bindings;
    // UBOs 0-4
    for (uint32_t i = 0; i <= 4; i++)
        bindings.push_back(sb(i, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER));
    // Storage buffers 5-7
    bindings.push_back(sb(5));  // controlY (dummy for bolt mode)
    bindings.push_back(sb(6));  // yGrid
    bindings.push_back(sb(7));  // nGrid
    // Storage images 8, 12
    bindings.push_back({8, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr});
    bindings.push_back(sb(9));  // gaussianPool
    bindings.push_back(sb(51)); // Phase 2: sunBatchFlat
    bindings.push_back(sb(10)); // fluxPartial
    bindings.push_back(sb(11)); // gradPartial (bolt-sized)
    bindings.push_back({12, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr});
    bindings.push_back(sb(13)); // adamM
    bindings.push_back(sb(14)); // adamV
    bindings.push_back(sb(15)); // s95CountBuf / debugBuf
    bindings.push_back(sb(16)); // controlYGradient (dummy for bolt mode)
    // Bolt-specific bindings 17-25
    bindings.push_back(sb(17)); // boltHeights
    bindings.push_back(sb(18)); // boltHeightGradient
    bindings.push_back(sb(19)); // influencePhi
    bindings.push_back(sb(20)); // influencePhiU
    bindings.push_back(sb(21)); // influencePhiV
    bindings.push_back(sb(22)); // gravityY
    bindings.push_back(sb(23)); // yuGrid
    bindings.push_back(sb(24)); // yvGrid
    bindings.push_back(sb(25)); // surfaceGradient
    bindings.push_back(sb(29)); // rayValidity (P2)
    bindings.push_back(sb(30)); // gravityBase (legacy, kept for compat)
    // Bindings 31-50: multi-angle FEA gravity bins (10/14/18/.../78/80 deg)
    for (uint32_t b = 31; b <= 50; b++)
        bindings.push_back(sb(b));
    bindings.push_back(sb(52)); // s95State (GPU S95 level)
    bindings.push_back(sb(53)); // lossAccumFixed (GPU scalar loss)
    bindings.push_back(sb(55)); // activePixelList (A1: sparse culling)

    VkDescriptorSetLayoutCreateInfo linfo{};
    linfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    linfo.bindingCount = static_cast<uint32_t>(bindings.size());
    linfo.pBindings = bindings.data();
    checkVk(vkCreateDescriptorSetLayout(m_app.device(), &linfo, nullptr, &m_boltSetLayout), "bolt set layout");

    VkDescriptorSetAllocateInfo ainfo{};
    ainfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    ainfo.descriptorPool = m_app.descriptorPool();
    ainfo.descriptorSetCount = 1;
    ainfo.pSetLayouts = &m_boltSetLayout;
    checkVk(vkAllocateDescriptorSets(m_app.device(), &ainfo, &m_boltDescriptorSet), "bolt descriptor set");

    auto createPipe = [&](std::span<const uint32_t> spv, const char *entry, uint32_t pcSize) -> ComputePipeline {
        ComputePipeline p;
        p.setLayout = m_boltSetLayout;
        p.descriptorSets.resize(1);
        p.descriptorSets[0] = m_boltDescriptorSet;

        VkPipelineLayoutCreateInfo plinfo{};
        plinfo.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        plinfo.setLayoutCount = 1;
        plinfo.pSetLayouts = &m_boltSetLayout;
        VkPushConstantRange pcRange{};
        if (pcSize > 0) {
            pcRange.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
            pcRange.size = pcSize;
            plinfo.pushConstantRangeCount = 1;
            plinfo.pPushConstantRanges = &pcRange;
        }
        checkVk(vkCreatePipelineLayout(m_app.device(), &plinfo, nullptr, &p.layout), "bolt pipeline layout");

        VkShaderModuleCreateInfo sinfo{};
        sinfo.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        sinfo.codeSize = spv.size() * sizeof(uint32_t);
        sinfo.pCode = spv.data();
        VkShaderModule sm;
        checkVk(vkCreateShaderModule(m_app.device(), &sinfo, nullptr, &sm), "bolt shader module");

        VkComputePipelineCreateInfo pinfo{};
        pinfo.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
        pinfo.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        pinfo.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        pinfo.stage.module = sm;
        pinfo.stage.pName = entry;
        pinfo.layout = p.layout;
        checkVk(vkCreateComputePipelines(m_app.device(), VK_NULL_HANDLE, 1, &pinfo, nullptr, &p.pipeline), "bolt pipeline");

        vkDestroyShaderModule(m_app.device(), sm, nullptr);
        return p;
    };

    m_pipeBoltSurface   = createPipe(m_spvBoltSurface,   "main", sizeof(uint32_t) * 5);  // BoltSurfacePC
    m_pipeBoltBackward  = createPipe(m_spvBoltBackward,  "main", sizeof(uint32_t) * 4);  // BoltBackwardPC
    m_pipeBoltBackwardReduce = createPipe(m_spvBoltBackwardReduce, "main", 0);
    m_pipeBoltProject   = createPipe(m_spvBoltProject,   "main", sizeof(uint32_t) * 4);  // BoltBackwardPC
    m_pipeBoltClearSurface = createPipe(m_spvBoltClearSurface, "main", 0);
    // AdamBoltPC: lr(4)+beta1(4)+beta2(4)+eps(4)+iterF(4)+numBolts:uint(4)+hMax(4)+lambda(4)=32B
    m_pipeBoltAdam      = createPipe(m_spvBoltAdam,      "main", 32);
    // P1-A2: specialized sunshape pipelines
    for (int i = 0; i < 3; i++) {
        m_pipeForwardTyped[i]     = createPipe(m_spvForwardTyped[i],     "main", 0);
        m_pipeBoltBackwardTyped[i] = createPipe(m_spvBoltBackwardTyped[i], "main", sizeof(uint32_t) * 4);
    }
    m_pipeS95FindLevel  = createPipe(m_spvS95FindLevel,  "main", 0);
    m_pipeS95LossBUF    = createPipe(m_spvS95LossBUF,    "main", sizeof(float) * 4);  // S95LossPC

    m_boltPipelinesCreated = true;
}

void BezierPipeline::createBoltBuffers() {
    if (m_boltBuffersCreated) return;

    uint32_t n = m_cfg.numBolts;
    uint32_t gridSize = m_cfg.gridSize;
    uint32_t gridPts = gridSize * gridSize;

    m_boltHeights = m_app.createBuffer(n * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_boltHeightGradient = m_app.createBuffer(n * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_boltAdamM = m_app.createBuffer(n * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_boltAdamV = m_app.createBuffer(n * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_yuGrid = m_app.createBuffer(kSunBatchSize * gridPts * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
    m_yvGrid = m_app.createBuffer(kSunBatchSize * gridPts * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
    m_surfaceGradient = m_app.createBuffer(gridPts * 3u * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_gravityY = m_app.createBuffer(gridPts * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);

    // Load 20-bin gravity angles (hardcoded, must match data_proxy/ and shaders/bolt_common.slang)
    {
        const int gravityAngles[20] = {10, 14, 18, 22, 26, 30, 34, 38, 42, 46,
                                        50, 54, 58, 62, 66, 70, 73, 76, 78, 80};
        for (int i = 0; i < 20; i++) {
            m_gravityBins[i] = m_app.createBuffer(gridPts * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
            std::string gravPath = m_cfg.influenceDataPath + "/gravity_" + std::to_string(gravityAngles[i]) + "deg.bin";
            std::ifstream fg(gravPath, std::ios::binary);
            if (fg) {
                std::vector<float> gData(gridPts);
                fg.read(reinterpret_cast<char*>(gData.data()), gridPts * sizeof(float));
                m_app.uploadBuffer(m_gravityBins[i], gData.data(), gridPts * sizeof(float));
                fmt::print("  Loaded gravity_{}deg.bin (PV={:.3f} mm)\n",
                    gravityAngles[i],
                    (*std::max_element(gData.begin(), gData.end()) - *std::min_element(gData.begin(), gData.end())) * 1000.0f);
            } else {
                fmt::print("  WARNING: no gravity_{}deg.bin, using zeros\n", gravityAngles[i]);
                std::vector<float> zeros(gridPts, 0.0f);
                m_app.uploadBuffer(m_gravityBins[i], zeros.data(), gridPts * sizeof(float));
            }
        }
    }

    // Load influence data from binary files
    size_t infSize = n * gridPts * sizeof(float);
    auto loadBin = [&](const std::string &fname, GpuBuffer &buf) -> bool {
        std::string path = m_cfg.influenceDataPath + "/" + fname;
        std::ifstream f(path, std::ios::binary);
        if (!f) {
            fmt::print("  WARNING: Cannot open {}\n", path);
            return false;
        }
        std::vector<float> data(n * gridPts);
        f.read(reinterpret_cast<char*>(data.data()), infSize);
        buf = m_app.createBuffer(infSize, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
        m_app.uploadBuffer(buf, data.data(), infSize);
        return true;
    };

    m_influencePhi = {}; m_influencePhiU = {}; m_influencePhiV = {};
    bool ok = loadBin("influence_phi.bin", m_influencePhi);
    ok = loadBin("influence_phi_u.bin", m_influencePhiU) && ok;
    ok = loadBin("influence_phi_v.bin", m_influencePhiV) && ok;
    ok = loadBin("gravity_y.bin", m_gravityY) && ok;
    if (!ok) throw std::runtime_error("Failed to load influence data. Run scripts/generate_influence.py first.");

    // Phase 5: gradPartialTile (fixed-point int, per-grid-point, 12 KB) replaces 386 MB boltGradPartial
    m_boltGradPartialTile = m_app.createBuffer(gridPts * 3u * sizeof(int32_t),
                                                VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);

    // Dummy buffer for unused Bezier bindings (binding 5: controlY, binding 16: controlYGradient)
    m_dummyBuf = m_app.createBuffer(64, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    std::vector<float> dummyData(16, 0.0f);
    m_app.uploadBuffer(m_dummyBuf, dummyData.data(), 64);
    m_sunBatchFlat = m_app.createBuffer(kSunBatchSize * 8 * sizeof(float),
                                         VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
    // GPU S95: [0]=level, [2]=total, [3]=maxFlux + fixed-point scalar-loss accum.
    // Host-visible so the per-iteration loss readback is a bare memcpy.
    m_s95State = m_app.createBuffer(4 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);
    m_lossAccum = m_app.createBuffer(sizeof(uint32_t), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);

    // Bind all descriptors
    VkDescriptorSet set = m_boltDescriptorSet;

    VkDescriptorBufferInfo uboInfos[] = {
        {m_uboReceiver.buffer, 0, m_uboReceiver.size},
        {m_uboHeliostat.buffer, 0, m_uboHeliostat.size},
        {m_uboSun.buffer, 0, m_uboSun.size},
        {m_uboHelioPos.buffer, 0, m_uboHelioPos.size},
        {m_uboAimPoint.buffer, 0, m_uboAimPoint.size},
    };

    VkDescriptorBufferInfo sbInfos[] = {
        {m_dummyBuf.buffer, 0, m_dummyBuf.size},             // 5: controlY (dummy)
        {m_yGrid.buffer, 0, m_yGrid.size},                   // 6
        {m_nGrid.buffer, 0, m_nGrid.size},                   // 7
        {m_dummyBuf.buffer, 0, 4},                           // 9 (was gaussianPool, Phase 1: dummy)
        {m_fluxPartial.buffer, 0, m_fluxPartial.size},       // 10
        {m_boltGradPartialTile.buffer, 0, m_boltGradPartialTile.size}, // 11 (gradPartialTile, Phase 5)
        {m_boltAdamM.buffer, 0, m_boltAdamM.size},           // 13
        {m_boltAdamV.buffer, 0, m_boltAdamV.size},           // 14
        {m_s95CountBuf.buffer, 0, m_s95CountBuf.size},       // 15
        {m_dummyBuf.buffer, 0, m_dummyBuf.size},             // 16: controlYGradient (dummy)
        {m_boltHeights.buffer, 0, m_boltHeights.size},       // 17
        {m_boltHeightGradient.buffer, 0, m_boltHeightGradient.size}, // 18
        {m_influencePhi.buffer, 0, m_influencePhi.size},     // 19
        {m_influencePhiU.buffer, 0, m_influencePhiU.size},   // 20
        {m_influencePhiV.buffer, 0, m_influencePhiV.size},   // 21
        {m_gravityY.buffer, 0, m_gravityY.size},             // 22
        {m_yuGrid.buffer, 0, m_yuGrid.size},                 // 23
        {m_yvGrid.buffer, 0, m_yvGrid.size},                 // 24
        {m_surfaceGradient.buffer, 0, m_surfaceGradient.size}, // 25
        {m_rayValidity.buffer, 0, m_rayValidity.size},         // 29
        {m_gravityBins[0].buffer, 0, m_gravityBins[0].size},   // 30: gravityBase (legacy)
        {m_gravityBins[0].buffer, 0, m_gravityBins[0].size},   // 31: gravityBin10
        {m_gravityBins[1].buffer, 0, m_gravityBins[1].size},   // 32: gravityBin14
        {m_gravityBins[2].buffer, 0, m_gravityBins[2].size},   // 33: gravityBin18
        {m_gravityBins[3].buffer, 0, m_gravityBins[3].size},   // 34: gravityBin22
        {m_gravityBins[4].buffer, 0, m_gravityBins[4].size},   // 35: gravityBin26
        {m_gravityBins[5].buffer, 0, m_gravityBins[5].size},   // 36: gravityBin30
        {m_gravityBins[6].buffer, 0, m_gravityBins[6].size},   // 37: gravityBin34
        {m_gravityBins[7].buffer, 0, m_gravityBins[7].size},   // 38: gravityBin38
        {m_gravityBins[8].buffer, 0, m_gravityBins[8].size},   // 39: gravityBin42
        {m_gravityBins[9].buffer, 0, m_gravityBins[9].size},   // 40: gravityBin46
        {m_gravityBins[10].buffer, 0, m_gravityBins[10].size}, // 41: gravityBin50
        {m_gravityBins[11].buffer, 0, m_gravityBins[11].size}, // 42: gravityBin54
        {m_gravityBins[12].buffer, 0, m_gravityBins[12].size}, // 43: gravityBin58
        {m_gravityBins[13].buffer, 0, m_gravityBins[13].size}, // 44: gravityBin62
        {m_gravityBins[14].buffer, 0, m_gravityBins[14].size}, // 45: gravityBin66
        {m_gravityBins[15].buffer, 0, m_gravityBins[15].size}, // 46: gravityBin70
        {m_gravityBins[16].buffer, 0, m_gravityBins[16].size}, // 47: gravityBin73
        {m_gravityBins[17].buffer, 0, m_gravityBins[17].size}, // 48: gravityBin76
        {m_gravityBins[18].buffer, 0, m_gravityBins[18].size}, // 49: gravityBin78
        {m_gravityBins[19].buffer, 0, m_gravityBins[19].size}, // 50: gravityBin80
        {m_sunBatchFlat.buffer, 0, m_sunBatchFlat.size},       // 51: sunBatchFlat (Phase 2)
        {m_activePixelList.buffer, 0, m_activePixelList.size}, // 55: activePixelList (A1)
        {m_s95State.buffer, 0, m_s95State.size},               // 52: s95State (GPU S95)
        {m_lossAccum.buffer, 0, m_lossAccum.size},             // 53: lossAccumFixed (GPU S95)
    };

    VkDescriptorImageInfo imgInfos[] = {
        {VK_NULL_HANDLE, m_renderedFlux.view, VK_IMAGE_LAYOUT_GENERAL},  // 8
        {VK_NULL_HANDLE, m_fluxGradient.view, VK_IMAGE_LAYOUT_GENERAL},  // 12
    };

    std::vector<VkWriteDescriptorSet> writes(52);
    for (int i = 0; i < 52; i++) {
        writes[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[i].dstSet = set;
        writes[i].dstArrayElement = 0;
        writes[i].descriptorCount = 1;
    }
    // UBOs 0-4
    for (int i = 0; i < 5; i++) {
        writes[i].dstBinding = (uint32_t)i;
        writes[i].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        writes[i].pBufferInfo = &uboInfos[i];
    }
    // Storage buffers
    writes[5].dstBinding = 5;  writes[5].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[5].pBufferInfo = &sbInfos[0];
    writes[6].dstBinding = 6;  writes[6].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[6].pBufferInfo = &sbInfos[1];
    writes[7].dstBinding = 7;  writes[7].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[7].pBufferInfo = &sbInfos[2];
    writes[8].dstBinding = 8;  writes[8].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE;  writes[8].pImageInfo = &imgInfos[0];
    writes[9].dstBinding = 9;  writes[9].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[9].pBufferInfo = &sbInfos[3];
    writes[10].dstBinding = 10; writes[10].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[10].pBufferInfo = &sbInfos[4];
    writes[11].dstBinding = 11; writes[11].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[11].pBufferInfo = &sbInfos[5];
    writes[12].dstBinding = 12; writes[12].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; writes[12].pImageInfo = &imgInfos[1];
    writes[13].dstBinding = 13; writes[13].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[13].pBufferInfo = &sbInfos[6];
    writes[14].dstBinding = 14; writes[14].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[14].pBufferInfo = &sbInfos[7];
    writes[15].dstBinding = 15; writes[15].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[15].pBufferInfo = &sbInfos[8];
    writes[16].dstBinding = 16; writes[16].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; writes[16].pBufferInfo = &sbInfos[9];
    // Bolt-specific 17-25
    for (int i = 17; i <= 25; i++) {
        writes[i].dstBinding = (uint32_t)i;
        writes[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        writes[i].pBufferInfo = &sbInfos[10 + (i - 17)];
    }
    // Binding 29: rayValidity
    writes[26].dstBinding = 29;
    writes[26].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    writes[26].pBufferInfo = &sbInfos[19];  // rayValidity
    // Binding 30: gravityBase (legacy compat, now points to gravityBin0)
    writes[27].dstBinding = 30;
    writes[27].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    writes[27].pBufferInfo = &sbInfos[20];  // gravityBins[0]
    // Bindings 31-50: 20 gravity bins
    for (int gi = 0; gi < 20; gi++) {
        uint32_t wi = 28u + (uint32_t)gi;
        writes[wi].dstBinding = 31u + (uint32_t)gi;
        writes[wi].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        writes[wi].pBufferInfo = &sbInfos[21 + gi];
    }
    // Binding 51: sunBatchFlat (Phase 2)
    writes[48].dstBinding = 51;
    writes[48].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    writes[48].pBufferInfo = &sbInfos[41];
    // Binding 55: activePixelList (A1: sparse culling)
    writes[49].dstBinding = 55;
    writes[49].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    writes[49].pBufferInfo = &sbInfos[42];
    // Binding 52/53: GPU S95 state + loss accumulator
    writes[50].dstBinding = 52;
    writes[50].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    writes[50].pBufferInfo = &sbInfos[43];
    writes[51].dstBinding = 53;
    writes[51].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    writes[51].pBufferInfo = &sbInfos[44];
    vkUpdateDescriptorSets(m_app.device(), static_cast<uint32_t>(writes.size()), writes.data(), 0, nullptr);

    m_boltBuffersCreated = true;
}

void BezierPipeline::uploadBoltData(const std::vector<float> &initBoltHeights) {
    m_app.uploadBuffer(m_boltHeights, initBoltHeights.data(), initBoltHeights.size() * sizeof(float));
    uint32_t n = m_cfg.numBolts;
    std::vector<float> zeros(n, 0.0f);
    m_app.uploadBuffer(m_boltHeightGradient, zeros.data(), n * sizeof(float));
    m_app.uploadBuffer(m_boltAdamM, zeros.data(), n * sizeof(float));
    m_app.uploadBuffer(m_boltAdamV, zeros.data(), n * sizeof(float));
}

static float computeCosThetaStatic(const std::array<float,3>& sd, const std::array<float,3>& hp,
                                    const std::array<float,3>& ap);

// Phase 2: helper to pack 1 sun into sunBatchFlat + dispatch
static void packGravityParams(float cosTheta, uint32_t& lo, uint32_t& hi, float& gt) {
    const int numGravityAngles = 20;
    const float gravityAnglesDeg[20] = {10.0f, 14.0f, 18.0f, 22.0f, 26.0f, 30.0f, 34.0f, 38.0f, 42.0f, 46.0f,
                                        50.0f, 54.0f, 58.0f, 62.0f, 66.0f, 70.0f, 73.0f, 76.0f, 78.0f, 80.0f};
    float angDeg = std::acos(std::max(0.0f,std::min(1.0f,cosTheta)))*180.0f/3.14159265f;
    if(angDeg<=gravityAnglesDeg[0]){lo=0;hi=0;gt=0.0f;}
    else if(angDeg>=gravityAnglesDeg[numGravityAngles-1]){lo=numGravityAngles-1;hi=lo;gt=0.0f;}
    else for(int j=0;j<numGravityAngles-1;j++) if(angDeg>=gravityAnglesDeg[j]&&angDeg<=gravityAnglesDeg[j+1])
        {lo=(uint32_t)j;hi=(uint32_t)(j+1);gt=(angDeg-gravityAnglesDeg[j])/(gravityAnglesDeg[j+1]-gravityAnglesDeg[j]);break;}
}

void BezierPipeline::boltForwardSurface(const std::vector<std::array<float,3>>& trainDirs,
    const std::array<float,3>& hp, const std::array<float,3>& ap, int batchStart, uint32_t batchCount) {
    // Pack sun batch data: 8 floats/sun (dir[3],pad,gravLo,gravHi,gravT,pad)
    std::vector<float> batch(batchCount*8, 0.0f);
    for(uint32_t i=0;i<batchCount;i++){
        const auto& sd=trainDirs[batchStart+i];
        batch[i*8+0]=sd[0];batch[i*8+1]=sd[1];batch[i*8+2]=sd[2];
        uint32_t lo,hi;float gt;
        packGravityParams(computeCosThetaStatic(sd,hp,ap),lo,hi,gt);
        std::memcpy(&batch[i*8+4],&lo,4);std::memcpy(&batch[i*8+5],&hi,4);batch[i*8+6]=gt;
        if(i==0){static bool fc=true;if(fc){float ca=computeCosThetaStatic(sd,hp,ap);fmt::print("  [gravity] cos={:.4f} ang={:.2f} lo={} hi={} t={:.4f}\n",ca,std::acos(std::max(0.0f,std::min(1.0f,ca)))*180.0f/3.14159265f,lo,hi,gt);fc=false;}}
    }
    m_app.uploadBuffer(m_sunBatchFlat, batch.data(), batch.size()*sizeof(float));
    auto pass=m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeBoltSurface);
    struct{uint32_t numBolts;uint32_t disableGravity;uint32_t sunBatchCount;uint32_t _pad;}pc;
    pc.numBolts=m_cfg.numBolts;pc.disableGravity=m_cfg.disableGravity?1u:0u;pc.sunBatchCount=batchCount;pc._pad=0;
    m_app.pushConstants(pass.cmd, m_pipeBoltSurface.layout, &pc, sizeof(pc));
    m_app.dispatch(pass.cmd, 1, 1, batchCount);
    m_app.pipelineBarrier(pass.cmd);
    m_app.endComputePass(pass);
}

void BezierPipeline::boltForwardSurface(float cosTheta) {
    uint32_t lo,hi;float gt;
    packGravityParams(cosTheta,lo,hi,gt);
    std::vector<float> batch(8,0.0f);
    batch[0]=m_lastSunDir[0];batch[1]=m_lastSunDir[1];batch[2]=m_lastSunDir[2];
    std::memcpy(&batch[4],&lo,4);std::memcpy(&batch[5],&hi,4);batch[6]=gt;
    m_app.uploadBuffer(m_sunBatchFlat, batch.data(), 8*sizeof(float));
    auto pass=m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeBoltSurface);
    struct{uint32_t numBolts;uint32_t disableGravity;uint32_t sunBatchCount;uint32_t _pad;}pc;
    pc.numBolts=m_cfg.numBolts;pc.disableGravity=m_cfg.disableGravity?1u:0u;pc.sunBatchCount=1;pc._pad=0;
    m_app.pushConstants(pass.cmd, m_pipeBoltSurface.layout, &pc, sizeof(pc));
    m_app.dispatch(pass.cmd, 1, 1, 1);
    m_app.pipelineBarrier(pass.cmd);
    m_app.endComputePass(pass);
}

void BezierPipeline::uploadSurfaceFromFile(const std::string &path) {
    // Load XYZ point cloud (format: x z uy), extract UY and compute derivatives.
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open surface file: " + path);

    std::vector<float> uy;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        float x, z, u;
        if (ss >> x >> z >> u) uy.push_back(u);
    }
    if (uy.size() != m_cfg.gridSize * m_cfg.gridSize)
        throw std::runtime_error("Surface file must have " +
            std::to_string(m_cfg.gridSize*m_cfg.gridSize) + " points, got " + std::to_string(uy.size()));

    // Compute yu, yv via finite differences
    float dx = m_cfg.heliostatWidth / (m_cfg.gridSize - 1);
    float dz = m_cfg.heliostatLength / (m_cfg.gridSize - 1);
    std::vector<float> yu(uy.size(), 0.0f), yv(uy.size(), 0.0f);

    for (uint32_t z = 0; z < m_cfg.gridSize; z++) {
        for (uint32_t x = 0; x < m_cfg.gridSize; x++) {
            uint32_t idx = z * m_cfg.gridSize + x;
            // du derivative
            if (x == 0) yu[idx] = (uy[idx+1] - uy[idx]) / dx;
            else if (x == m_cfg.gridSize - 1) yu[idx] = (uy[idx] - uy[idx-1]) / dx;
            else yu[idx] = (uy[idx+1] - uy[idx-1]) / (2.0f * dx);
            // dv derivative
            if (z == 0) yv[idx] = (uy[idx + m_cfg.gridSize] - uy[idx]) / dz;
            else if (z == m_cfg.gridSize - 1) yv[idx] = (uy[idx] - uy[idx - m_cfg.gridSize]) / dz;
            else yv[idx] = (uy[idx + m_cfg.gridSize] - uy[idx - m_cfg.gridSize]) / (2.0f * dz);
        }
    }

    // Upload to GPU surface buffers
    m_app.uploadBuffer(m_yGrid, uy.data(), uy.size() * sizeof(float));
    m_app.uploadBuffer(m_yuGrid, yu.data(), yu.size() * sizeof(float));
    m_app.uploadBuffer(m_yvGrid, yv.data(), yv.size() * sizeof(float));

    // Compute and upload nGrid (normals) from yu/yv
    {
        float W = m_cfg.heliostatWidth;
        float L = m_cfg.heliostatLength;
        std::vector<float> nGrid(uy.size() * 4, 0.0f);
        for (size_t i = 0; i < uy.size(); i++) {
            // tu = (W, yu, 0), tv = (0, yv, L)
            // nrm = -cross(tu, tv) / |cross(tu, tv)|
            float nx = -(yu[i] * 0.0f - L * 0.0f);  // cross_y = tuz*tvx - tux*tvz ...
            // cross(tu, tv) = (yu*L - 0*0, 0*0 - W*L, W*yv - yu*0) = (yu*L, -W*L, W*yv)
            // actually: tu=(W, yu, 0), tv=(0, yv, L)
            // cross = (yu*L - 0*yv, 0*0 - W*L, W*yv - yu*0) = (yu*L, -W*L, W*yv)
            float cx = yu[i] * L;
            float cy = -W * L;
            float cz = W * yv[i];
            float len = std::sqrt(cx*cx + cy*cy + cz*cz);
            if (len < 1e-12f) len = 1e-12f;
            // nrm = -cross/len (negative sign from shader convention)
            nGrid[i*4 + 0] = -cx / len;
            nGrid[i*4 + 1] = -cy / len;
            nGrid[i*4 + 2] = -cz / len;
            nGrid[i*4 + 3] = 0.0f;
        }
        m_app.uploadBuffer(m_nGrid, nGrid.data(), nGrid.size() * sizeof(float));
    }

    fmt::print("  Loaded surface: {} pts, UY PV={:.3f}mm\n", uy.size(),
        (*std::max_element(uy.begin(), uy.end()) - *std::min_element(uy.begin(), uy.end())) * 1000.0f);
}

void BezierPipeline::boltBackwardPass() {
    // Legacy: one-pass-per-dispatch. Use boltBackwardPassCmd in hot path.
    uint32_t gridPts = m_cfg.gridSize * m_cfg.gridSize;
    auto pass = m_app.beginComputePassRaw();
    boltBackwardPassCmd(pass.cmd);
    m_app.submitAndWait(pass);
}

// Phase 2: Batched backward pass — all 4 stages in single command buffer
void BezierPipeline::boltBackwardPassCmd(VkCommandBuffer cmd) {
    uint32_t n = m_cfg.numBolts;
    uint32_t tileCount = (m_totalSpp + 255) / 256;
    uint32_t gridPts = m_cfg.gridSize * m_cfg.gridSize;

    // Phase 5: Clear surfaceGradient and gradPartialTile via vkCmdFillBuffer
    m_app.fillBufferCmd(cmd, m_surfaceGradient, 0u);
    m_app.fillBufferCmd(cmd, m_boltGradPartialTile, 0u);
    m_app.pipelineBarrier(cmd);

    // Stage 1: optical backward → gradPartial (P1-A2: specialized by sunshape)
    {
        uint32_t st = static_cast<uint32_t>(m_cfg.sunType);
        m_app.bindPipeline(cmd, m_pipeBoltBackwardTyped[st]);
    }
    struct { uint32_t numBolts; float _pad[3]; } bwPC;
    bwPC.numBolts = n; bwPC._pad[0] = 0; bwPC._pad[1] = 0; bwPC._pad[2] = 0;
    m_app.pushConstants(cmd, m_pipeBoltBackwardTyped[0].layout, &bwPC, sizeof(bwPC));
    m_app.dispatch(cmd, m_activePixelCount, tileCount, 1);  // A1: sparse culling
    m_app.pipelineBarrier(cmd);

    // Stage 1b: reduce gradPartial → surfaceGradient
    m_app.bindPipeline(cmd, m_pipeBoltBackwardReduce);
    m_app.dispatch(cmd, 1, 1, 1);
    m_app.pipelineBarrier(cmd);

    // Stage 2: project surfaceGradient → boltHeightGradient
    m_app.bindPipeline(cmd, m_pipeBoltProject);
    struct { uint32_t numBolts; float _pad[3]; } projPC;
    projPC.numBolts = n; projPC._pad[0] = 0; projPC._pad[1] = 0; projPC._pad[2] = 0;
    m_app.pushConstants(cmd, m_pipeBoltProject.layout, &projPC, sizeof(projPC));
    m_app.dispatch(cmd, (n + 49) / 50, 1, 1);
}

// Phase 2: Surface forward dispatch (caller uploads sunBatchFlat before pass)
void BezierPipeline::boltForwardSurfaceCmd(VkCommandBuffer cmd, uint32_t batchCount) {
    m_app.bindPipeline(cmd, m_pipeBoltSurface);
    struct { uint32_t numBolts; uint32_t disableGravity; uint32_t sunBatchCount; uint32_t _pad; } pc;
    pc.numBolts = m_cfg.numBolts;
    pc.disableGravity = m_cfg.disableGravity ? 1u : 0u;
    pc.sunBatchCount = batchCount;
    pc._pad = 0;
    m_app.pushConstants(cmd, m_pipeBoltSurface.layout, &pc, sizeof(pc));
    m_app.dispatch(cmd, 1, 1, batchCount);
    m_app.pipelineBarrier(cmd);
}

// Phase 2: Forward render dispatches within existing command buffer
void BezierPipeline::forwardRenderCmd(VkCommandBuffer cmd) {
    // 1. Clear flux
    m_app.bindPipeline(cmd, m_pipeClear);
    m_app.dispatch(cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.pipelineBarrier(cmd);
    // 2. Forward render — P1-A2: use specialized pipeline by sunshape type
    {
        uint32_t st = static_cast<uint32_t>(m_cfg.sunType);
        m_app.bindPipeline(cmd, m_pipeForwardTyped[st]);
    }
    uint32_t tileCount = (m_totalSpp + 255) / 256;
    m_app.dispatch(cmd, tileCount, m_activePixelCount, 1);  // A1: sparse culling
    m_app.pipelineBarrier(cmd);
    // 3. Finalize: atomic buffer → texture
    m_app.bindPipeline(cmd, m_pipeFinalize);
    m_app.dispatch(cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.pipelineBarrier(cmd);
}

// Phase 2: Clear ray validity via vkCmdFillBuffer (avoids CPU upload sync)
void BezierPipeline::clearRayValidityCmd(VkCommandBuffer cmd) {
    m_app.fillBufferCmd(cmd, m_rayValidity, 0u);
}

// Phase 2: Clear flux gradient within existing command buffer
void BezierPipeline::clearFluxGradientCmd(VkCommandBuffer cmd) {
    m_app.bindPipeline(cmd, m_pipeClearFluxGrad);
    m_app.dispatch(cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.pipelineBarrier(cmd);
}

// Phase 2: Compute S95 loss within existing command buffer
void BezierPipeline::computeS95LossCmd(VkCommandBuffer cmd, float s95Level) {
    m_app.bindPipeline(cmd, m_pipeLoss);
    m_app.pushConstants(cmd, m_pipeLoss.layout, &s95Level, sizeof(float));
    m_app.dispatch(cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.pipelineBarrier(cmd);
}

// GPU S95: cooperative binary-search level find (single workgroup), level
// stays on GPU in m_s95State[0] — replaces readFlux() + CPU binary search.
void BezierPipeline::computeS95FindLevelCmd(VkCommandBuffer cmd) {
    m_app.bindPipeline(cmd, m_pipeS95FindLevel);
    m_app.dispatch(cmd, 1, 1, 1);
    m_app.pipelineBarrier(cmd);
}

// GPU S95: sigmoid loss reading the level from m_s95State (no push constant,
// no host round trip); also accumulates the scalar loss into m_lossAccum.
// GPU S95: sigmoid loss reading the level from m_s95State (no push constant,
// no host round trip); also accumulates the scalar loss into m_lossAccum.
// L1: eRef/lambdaEff feed the efficiency term via push constants.
void BezierPipeline::computeS95LossBUFCmd(VkCommandBuffer cmd, float eRef, float lambdaEff) {
    m_app.bindPipeline(cmd, m_pipeS95LossBUF);
    float pc[4] = {eRef, lambdaEff, 0.0f, 0.0f};
    m_app.pushConstants(cmd, m_pipeS95LossBUF.layout, pc, sizeof(pc));
    m_app.dispatch(cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.pipelineBarrier(cmd);
}

void BezierPipeline::boltAdamStep(uint32_t iteration) {
    uint32_t n = m_cfg.numBolts;
    float lr = m_cfg.minLearningRate +
               (m_cfg.learningRate - m_cfg.minLearningRate) * (1.0f - (float)iteration / m_cfg.iterations);
    // P1-L4: compensate lr for tanh parameterization scaling.
    // dL/deps = dL/dh * hMax * sech²(eps), so lr_eps = lr / hMax preserves
    // the physical step magnitude. The sech² factor naturally softens near bounds.
    float hMax = std::max(m_cfg.maxBoltStroke, 1e-6f);
    float lrComp = lr / hMax;
    // Layout: lr, beta1, beta2, eps, iterF, numBolts(uint), hMax, lambdaStroke = 32B
    float pc[8] = {
        lrComp, m_cfg.beta1, m_cfg.beta2, m_cfg.adamEpsilon,
        0.0f,  // pc[4]=iterF placeholder (overwritten below)
        0.0f,  // pc[5] placeholder (numBolts via memcpy)
        hMax,
        m_cfg.strokeRegularization
    };
    pc[4] = static_cast<float>(iteration);
    std::memcpy(&pc[5], &n, sizeof(uint32_t));  // numBolts at offset 20

    auto pass = m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeBoltAdam);
    m_app.pushConstants(pass.cmd, m_pipeBoltAdam.layout, pc, sizeof(pc));
    m_app.dispatch(pass.cmd, 1, 1, 1);
    m_app.endComputePass(pass);
}

// ── B-spline CP optimization methods ─────────────────────────────────────

void BezierPipeline::loadBSplineMatrix() {
    m_nCp = m_cfg.numCpX * m_cfg.numCpZ;
    int nBolts = m_cfg.numBolts;

    // Try binary format first, then text
    std::string path = m_cfg.influenceDataPath + "/bspline_T.bin";
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        path = m_cfg.influenceDataPath + "/bspline_T.txt";
        fmt::print("  B-spline T: loading from text {}\n", path);
        std::ifstream ftxt(path);
        if (!ftxt) throw std::runtime_error("Cannot open " + path);
        m_bsplineT.resize(nBolts * m_nCp);
        for (int i = 0; i < nBolts * m_nCp; i++) ftxt >> m_bsplineT[i];
    } else {
        fmt::print("  B-spline T: loading {}x{} binary ({})\n", nBolts, m_nCp, path);
        m_bsplineT.resize(nBolts * m_nCp);
        f.read(reinterpret_cast<char*>(m_bsplineT.data()), nBolts * m_nCp * sizeof(float));
    }

    // Check row sums (partition of unity)
    double maxDev = 0.0;
    for (int i = 0; i < nBolts; i++) {
        double sum = 0.0;
        for (int j = 0; j < m_nCp; j++) sum += m_bsplineT[i * m_nCp + j];
        maxDev = std::max(maxDev, std::abs(sum - 1.0));
    }
    fmt::print("  B-spline T row sum max dev: {:.6f}\n", maxDev);

    // Initialize CP vectors
    m_cpHeights.assign(m_nCp, 0.0f);
    m_cpGradient.assign(m_nCp, 0.0f);
    m_cpAdamM.assign(m_nCp, 0.0f);
    m_cpAdamV.assign(m_nCp, 0.0f);
}

void BezierPipeline::cpToBoltHeights() {
    // h = T @ c  (nBolts = nBolts × nCp @ nCp)
    int nBolts = m_cfg.numBolts;
    std::vector<float> h(nBolts, 0.0f);
    for (int i = 0; i < nBolts; i++) {
        float sum = 0.0f;
        for (int j = 0; j < m_nCp; j++) {
            sum += m_bsplineT[i * m_nCp + j] * m_cpHeights[j];
        }
        h[i] = sum;
    }
    m_app.uploadBuffer(m_boltHeights, h.data(), nBolts * sizeof(float));
}

void BezierPipeline::boltGradToCpGrad() {
    // dL/dc = T^T @ dL/dh  (nCp = nCp × nBolts @ nBolts)
    int nBolts = m_cfg.numBolts;
    std::vector<float> dLdh(nBolts);
    m_app.downloadBuffer(m_boltHeightGradient, dLdh.data(), nBolts * sizeof(float));

    for (int j = 0; j < m_nCp; j++) {
        float sum = 0.0f;
        for (int i = 0; i < nBolts; i++) {
            sum += m_bsplineT[i * m_nCp + j] * dLdh[i];
        }
        m_cpGradient[j] = sum;
    }
}

void BezierPipeline::cpAdamStep(uint32_t iteration) {
    float lr = m_cfg.learningRate;
    float beta1 = m_cfg.beta1;
    float beta2 = m_cfg.beta2;
    float eps = m_cfg.adamEpsilon;
    float b1c = 1.0f - std::pow(beta1, (float)iteration);
    float b2c = 1.0f - std::pow(beta2, (float)iteration);

    for (int i = 0; i < m_nCp; i++) {
        float g = m_cpGradient[i];
        m_cpAdamM[i] = beta1 * m_cpAdamM[i] + (1.0f - beta1) * g;
        m_cpAdamV[i] = beta2 * m_cpAdamV[i] + (1.0f - beta2) * g * g;
        float mHat = m_cpAdamM[i] / b1c;
        float vHat = m_cpAdamV[i] / b2c;
        m_cpHeights[i] -= lr * mHat / (std::sqrt(vHat) + eps);
    }
}

// ── WoS influence function computation ──────────────────────────────────

void BezierPipeline::computeWoSInfluence(const std::string &outputDir) {
    fmt::print("=== WoS Influence Computation ===\n");
    const uint32_t TEX_W = 256, TEX_H = 192, N_BOLTS = 35, N_WALKS = 5000;
    const size_t totalPixels = TEX_W * TEX_H * N_BOLTS;

    // Load WoS SPIR-V and create independent pipeline
    auto spvWoS = loadSpv("computeWoSInfluence");
    ComputePipeline pipeWoS;
    VkShaderModule sm = VK_NULL_HANDLE;

    // Create descriptor set layout: binding 0 = bolt positions, binding 1 = output
    std::array<VkDescriptorSetLayoutBinding, 2> wosBindings = {{
        {0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
        {1, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
    }};
    VkDescriptorSetLayoutCreateInfo dslCI{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    dslCI.bindingCount = (uint32_t)wosBindings.size();
    dslCI.pBindings = wosBindings.data();
    VkResult vr = vkCreateDescriptorSetLayout(m_app.device(), &dslCI, nullptr, &pipeWoS.setLayout);
    if (vr != VK_SUCCESS) throw std::runtime_error(fmt::format("WoS descriptor set layout: {}", (int)vr));

    // Pipeline layout
    VkPushConstantRange pcr{VK_SHADER_STAGE_COMPUTE_BIT, 0, 16};  // WoS_PC = 4 floats
    VkPipelineLayoutCreateInfo layoutCI{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    layoutCI.setLayoutCount = 1;
    layoutCI.pSetLayouts = &pipeWoS.setLayout;
    layoutCI.pushConstantRangeCount = 1;
    layoutCI.pPushConstantRanges = &pcr;
    vr = vkCreatePipelineLayout(m_app.device(), &layoutCI, nullptr, &pipeWoS.layout);
    if (vr != VK_SUCCESS) throw std::runtime_error(fmt::format("WoS pipeline layout: {}", (int)vr));

    // Shader module
    {
        VkShaderModuleCreateInfo sinfo{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        sinfo.codeSize = spvWoS.size() * sizeof(uint32_t);
        sinfo.pCode = spvWoS.data();
        vr = vkCreateShaderModule(m_app.device(), &sinfo, nullptr, &sm);
        if (vr != VK_SUCCESS) throw std::runtime_error(fmt::format("WoS shader module: {}", (int)vr));
    }

    // Compute pipeline
    {
        VkComputePipelineCreateInfo ci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        ci.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        ci.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        ci.stage.module = sm;
        ci.stage.pName = "computeWoSInfluence";
        ci.layout = pipeWoS.layout;
        vr = vkCreateComputePipelines(m_app.device(), VK_NULL_HANDLE, 1, &ci, nullptr, &pipeWoS.pipeline);
        if (vr != VK_SUCCESS) throw std::runtime_error(fmt::format("WoS pipeline: {} — check shader entry point name matches SPIR-V", (int)vr));
    }

    // Bolt positions buffer
    float margin = m_cfg.boltMargin;
    uint32_t nbolts_x = m_cfg.numBoltsX;
    uint32_t nbolts_z = m_cfg.numBoltsZ;
    uint32_t nb = m_cfg.numBolts;
    std::vector<float> boltPos(nb * 2);
    for (uint32_t j = 0; j < nbolts_z; j++) {
        float v = margin + (1.f - 2.f*margin) * j / float(nbolts_z - 1);
        for (uint32_t i = 0; i < nbolts_x; i++) {
            float u = margin + (1.f - 2.f*margin) * i / float(nbolts_x - 1);
            uint32_t idx = j * nbolts_x + i;
            boltPos[idx*2]   = (u - 0.5f) * m_cfg.heliostatWidth;
            boltPos[idx*2+1] = (v - 0.5f) * m_cfg.heliostatLength;
        }
    }
    auto boltBuf = m_app.createBuffer(boltPos.size() * sizeof(float),
                                       VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, false);
    m_app.uploadBuffer(boltBuf, boltPos.data(), boltPos.size() * sizeof(float));

    // Output influence buffer
    auto outBuf = m_app.createBuffer(totalPixels * sizeof(float),
                                      VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, true);

    // Descriptor set
    VkDescriptorSetLayout setLayout = pipeWoS.setLayout;
    VkDescriptorSet descSet = VK_NULL_HANDLE;
    {
        VkDescriptorSetAllocateInfo ai{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
        ai.descriptorPool = m_app.descriptorPool();
        ai.descriptorSetCount = 1;
        ai.pSetLayouts = &setLayout;
        VkResult vr = vkAllocateDescriptorSets(m_app.device(), &ai, &descSet);
        if (vr != VK_SUCCESS || descSet == VK_NULL_HANDLE)
            throw std::runtime_error(fmt::format("WoS desc set alloc: {}", (int)vr));
    }
    {
        VkDescriptorBufferInfo boltInfo{boltBuf.buffer, 0, boltBuf.size};
        VkDescriptorBufferInfo outInfo{outBuf.buffer, 0, outBuf.size};
        VkWriteDescriptorSet writes[2] = {
            {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, nullptr, descSet, 0, 0, 1,
             VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, nullptr, &boltInfo, nullptr},
            {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, nullptr, descSet, 1, 0, 1,
             VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, nullptr, &outInfo, nullptr},
        };
        vkUpdateDescriptorSets(m_app.device(), 2, writes, 0, nullptr);
    }

    // Push constants
    float D_plate = 7e10f * std::pow(0.004f, 3) / (12.f * (1.f - 0.22f * 0.22f));
    struct { float W, L, D, nu; } pc = {m_cfg.heliostatWidth, m_cfg.heliostatLength, D_plate, 0.22f};

    // Dispatch
    uint32_t totalThreads = uint32_t(totalPixels);
    uint32_t groupCount = (totalThreads + 255) / 256;

    fmt::print("  Texture: {}x{} x {} bolts = {} pixels\n", TEX_W, TEX_H, N_BOLTS, totalPixels);
    fmt::print("  Walks per pixel: {}\n", N_WALKS);
    fmt::print("  Groups: {}, Threads: {}\n", groupCount, totalThreads);
    fmt::print("  Expected GPU time: ~2 min\n");
    fflush(stdout);

    fmt::print("  DEBUG: pipeline={} layout={} descSet={}\n",
               (void*)pipeWoS.pipeline, (void*)pipeWoS.layout, (void*)descSet);
    fflush(stdout);

    auto t0 = std::chrono::steady_clock::now();
    fmt::print("  DEBUG: beginComputePass...\n"); fflush(stdout);
    auto pass = m_app.beginComputePass();
    fmt::print("  DEBUG: got pass cmd={}\n", (void*)pass.cmd); fflush(stdout);

    vkCmdBindPipeline(pass.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeWoS.pipeline);
    fmt::print("  DEBUG: bindPipeline done\n"); fflush(stdout);

    vkCmdBindDescriptorSets(pass.cmd, VK_PIPELINE_BIND_POINT_COMPUTE,
                            pipeWoS.layout, 0, 1, &descSet, 0, nullptr);
    fmt::print("  DEBUG: bindDescSets done\n"); fflush(stdout);

    vkCmdPushConstants(pass.cmd, pipeWoS.layout, VK_SHADER_STAGE_COMPUTE_BIT,
                       0, sizeof(pc), &pc);
    fmt::print("  DEBUG: pushConstants done\n"); fflush(stdout);

    vkCmdDispatch(pass.cmd, groupCount, 1, 1);
    fmt::print("  DEBUG: dispatch done\n"); fflush(stdout);

    m_app.endComputePass(pass);
    fmt::print("  DEBUG: endComputePass done\n"); fflush(stdout);
    vkDeviceWaitIdle(m_app.device());
    auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    fmt::print("  GPU time: {:.1f}s\n", elapsed);

    // Read back and save as .bin files
    std::vector<float> outData(totalPixels);
    m_app.downloadBuffer(outBuf, outData.data(), totalPixels * sizeof(float));

    // Compute phi_u, phi_v via finite differences
    auto computeDerivs = [&](std::vector<float> &u, std::vector<float> &v) {
        u.resize(totalPixels); v.resize(totalPixels);
        float du = 1.f / (TEX_W - 1), dv = 1.f / (TEX_H - 1);
        for (uint32_t b = 0; b < N_BOLTS; b++) {
            size_t bOff = b * TEX_W * TEX_H;
            for (uint32_t y = 0; y < TEX_H; y++) {
                for (uint32_t x = 0; x < TEX_W; x++) {
                    size_t idx = bOff + y * TEX_W + x;
                    uint32_t xp1 = (x+1 < TEX_W) ? x+1 : x;
                    uint32_t xm1 = (x > 0) ? x-1 : x;
                    uint32_t yp1 = (y+1 < TEX_H) ? y+1 : y;
                    uint32_t ym1 = (y > 0) ? y-1 : y;
                    float f_xp1 = outData[bOff + y*TEX_W + xp1];
                    float f_xm1 = outData[bOff + y*TEX_W + xm1];
                    float f_yp1 = outData[bOff + yp1*TEX_W + x];
                    float f_ym1 = outData[bOff + ym1*TEX_W + x];
                    u[idx] = (f_xp1 - f_xm1) / (2.f * du);
                    v[idx] = (f_yp1 - f_ym1) / (2.f * dv);
                }
            }
        }
    };
    std::vector<float> phiU, phiV;
    computeDerivs(phiU, phiV);

    // Save raw high-res .bin files
    auto saveBin = [&](const std::string &name, const std::vector<float> &d) {
        std::ofstream f(outputDir + "/" + name, std::ios::binary);
        f.write((const char*)d.data(), d.size() * sizeof(float));
    };
    fs::create_directories(outputDir);
    saveBin("influence_phi.bin", outData);
    saveBin("influence_phi_u.bin", phiU);
    saveBin("influence_phi_v.bin", phiV);
    fmt::print("  Saved: {}/influence_phi*.bin ({}x{} x {} bolts, {} MB)\n",
               outputDir, TEX_W, TEX_H, N_BOLTS, outData.size()*4/1024/1024);

    // Cleanup
    vkDestroyShaderModule(m_app.device(), sm, nullptr);
    vkDestroyPipeline(m_app.device(), pipeWoS.pipeline, nullptr);
    vkDestroyPipelineLayout(m_app.device(), pipeWoS.layout, nullptr);
    vkDestroyDescriptorSetLayout(m_app.device(), pipeWoS.setLayout, nullptr);
}

// A2: pack SunParams UBO contents (13 floats, layout matching binding 2)
void BezierPipeline::fillSunParams(const std::array<float, 3> &sd, float *sunp) const {
    // Layout: dir(3), dni(1), shapeParams(4), shapeIntegral(1), type(1), _pad(3)
    sunp[0]=sd[0]; sunp[1]=sd[1]; sunp[2]=sd[2];
    sunp[3]=m_cfg.dni;
    // Buie shapeParams: {thetaInner, kappa, gamma, unused}
    sunp[4]=m_cfg.buieThetaInner; sunp[5]=m_cfg.buieKappa;
    sunp[6]=m_cfg.buieGamma; sunp[7]=0.0f;
    sunp[8]=m_cfg.sunShapeIntegral;
    sunp[9]=(float)(uint32_t)m_cfg.sunType;
    // P1-L3: iteration seed for Gaussian randomization (sunp[10] = iterationSeed)
    sunp[10] = m_cfg.randomizeSeed ? (float)m_currentIteration + 1.0f : 0.0f;
    // A1: per-ray pre-cull cosine (sunp[11] = cullCosCutoff)
    float support = 0.0436f;
    if (m_cfg.sunType == SunShapeType::PILLBOX) support = m_cfg.thetaMax;
    else if (m_cfg.sunType == SunShapeType::GAUSSIAN) support = 5.0f * m_cfg.sigma;
    float cullCos = -2.0f;
    if (m_cfg.rayCull) {
        float cutoff = support + m_cfg.rayCullMarginMrad * 1e-3f;
        cullCos = std::cos(cutoff);
    }
    sunp[11] = cullCos; sunp[12] = 0.0f;
}

void BezierPipeline::updateUniforms(const std::array<float, 3> &sd, const std::array<float, 3> &hp,
                                     const std::array<float, 3> &ap) {
    m_lastSunDir = sd; // Phase 2: cache for convenience overload
    // ---- Binding 0: ReceiverParams (10 floats, 40 bytes) ----
    std::vector<float> recv(10, 0.0f);
    recv[0]=m_cfg.receiverPosition[0]; recv[1]=m_cfg.receiverPosition[1]; recv[2]=m_cfg.receiverPosition[2];
    recv[3]=m_cfg.receiverRadius;
    recv[4]=m_cfg.receiverHeight;
    { uint32_t d[2]={m_cfg.pixelWidth, m_cfg.pixelHeight}; std::memcpy(&recv[6], d, 8); }
    recv[8]=m_cfg.receiverHeight/m_cfg.pixelHeight;
    recv[9]=2.0f*3.14159265f*m_cfg.receiverRadius/m_cfg.pixelWidth;
    m_app.uploadBuffer(m_uboReceiver, recv.data(), 10 * sizeof(float));

    // ---- Binding 1: HeliostatParams (9 floats, 36 bytes) ----
    // Layout: size(2), depth(1), refIdx(1), slopeErr(1), refArea(1), reflectivity(1), reflOnly(1), pad(1)
    std::vector<float> helio(11, 0.0f);
    helio[0]=m_cfg.heliostatWidth; helio[1]=m_cfg.heliostatLength;
    helio[2]=m_cfg.glassDepth;
    helio[3]=m_cfg.refractiveIndex;
    helio[4]=m_cfg.slopeError;
    helio[5]=m_cfg.heliostatWidth*m_cfg.heliostatLength;
    helio[6]=m_cfg.reflectivity;
    helio[7]=0.0f; // always refraction (was reflectionOnly)
    helio[8]=0.0f; // was poolMask (Phase 1: gaussianPool removed)
    // P4: cylinder half-face culling direction (from receiver center to heliostat)
    float hdx = hp[0] - m_cfg.receiverPosition[0];
    float hdz = hp[2] - m_cfg.receiverPosition[2];
    float hdLen = std::sqrt(hdx*hdx + hdz*hdz);
    helio[9] = (hdLen > 1e-6f) ? hdx / hdLen : 0.0f;
    helio[10] = (hdLen > 1e-6f) ? hdz / hdLen : 0.0f;
    m_app.uploadBuffer(m_uboHeliostat, helio.data(), 11 * sizeof(float));

    // ---- Binding 2: SunParams (13 floats, 52 bytes) ----
    float sunp[13];
    fillSunParams(sd, sunp);
    m_app.uploadBuffer(m_uboSun, sunp, 13 * sizeof(float));

    // ---- Binding 3: heliostatPosition (3 floats) ----
    m_app.uploadBuffer(m_uboHelioPos, hp.data(), 3 * sizeof(float));

    // ---- Binding 4: aimPoint (3 floats) ----
    m_app.uploadBuffer(m_uboAimPoint, ap.data(), 3 * sizeof(float));
}

void BezierPipeline::forwardRender(bool withBezier) {
    // Zero diagnostic counters before each forward render
    if (m_tirCountBuf.buffer != VK_NULL_HANDLE) {
        uint32_t zeros[6] = {0u, 0u, 0u, 0u, 0u, 0u};
        m_app.uploadBuffer(m_tirCountBuf, zeros, sizeof(zeros));
    }
    auto pass = m_app.beginComputePass();
    // 1. Clear flux
    m_app.bindPipeline(pass.cmd, m_pipeClear);
    m_app.dispatch(pass.cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.pipelineBarrier(pass.cmd);
    // 2. Bezier surface (optional — only once per iteration)
    if (withBezier) {
        m_app.bindPipeline(pass.cmd, m_pipeBezier);
        m_app.dispatch(pass.cmd, 1, 1, 1);
        m_app.pipelineBarrier(pass.cmd);
    }
    // 3. Forward render
    m_app.bindPipeline(pass.cmd, m_pipeForward);
    uint32_t tileCount = (m_totalSpp + 255) / 256;
    m_app.dispatch(pass.cmd, tileCount, m_activePixelCount, 1);  // A1: sparse culling
    m_app.pipelineBarrier(pass.cmd);
    // 4. Finalize: atomic buffer → texture
    m_app.bindPipeline(pass.cmd, m_pipeFinalize);
    m_app.dispatch(pass.cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.endComputePass(pass);
}

std::array<uint32_t, 6> BezierPipeline::getDiagCounts() const {
    std::array<uint32_t, 6> counts = {0u, 0u, 0u, 0u, 0u, 0u};
    if (m_tirCountBuf.buffer != VK_NULL_HANDLE) {
        m_app.downloadBuffer(m_tirCountBuf, counts.data(), 6 * sizeof(uint32_t));
    }
    return counts;
}

void BezierPipeline::clearRayValidity() {
    uint32_t numUints = (m_totalRays + 31u) / 32u;
    std::vector<uint32_t> zeros(numUints, 0u);
    m_app.uploadBuffer(m_rayValidity, zeros.data(), numUints * sizeof(uint32_t));
}

// A1: Precompute receiver pixels facing the heliostat (sun-independent).
// Replicates the forward.slang half-face cull test (normP · cullDir > 0) with a
// small over-inclusive margin, so the shader-side cull remains the source of
// truth and results stay bit-identical to the full dispatch.
void BezierPipeline::buildActivePixelList(const std::array<float, 3> &hp) {
    uint32_t w = m_cfg.pixelWidth, h = m_cfg.pixelHeight;
    float rx = m_cfg.receiverPosition[0], rz = m_cfg.receiverPosition[2];
    float hdx = hp[0] - rx, hdz = hp[2] - rz;
    float hdLen = std::sqrt(hdx * hdx + hdz * hdz);
    float cullX = (hdLen > 1e-6f) ? hdx / hdLen : 0.0f;
    float cullZ = (hdLen > 1e-6f) ? hdz / hdLen : 0.0f;

    std::vector<uint32_t> list;
    list.reserve(m_totalPixels);
    for (uint32_t py = 0; py < h; py++)
        for (uint32_t px = 0; px < w; px++) {
            // Pixel normal on the cylinder: normP = (sin(ang), 0, -cos(ang))
            float ang = float(px) * (2.0f * 3.14159265f / float(w));
            float nx = std::sin(ang), nz = -std::cos(ang);
            if (nx * cullX + nz * cullZ > -1e-4f)
                list.push_back(py * w + px);
        }
    m_activePixelCount = std::max(1u, (uint32_t)list.size());
    // Pad tail with sentinels (>= totalPixels → shader early-out) as defense
    // against any dispatch that still covers the full pixel range.
    list.resize(m_totalPixels, 0xFFFFFFFFu);
    m_app.uploadBuffer(m_activePixelList, list.data(), m_totalPixels * sizeof(uint32_t));
    fmt::print("  Sparse culling: {} active / {} total pixels ({:.0f}%)\n",
               m_activePixelCount, m_totalPixels, 100.0f * m_activePixelCount / m_totalPixels);
}

// ---- CPU-side statistics ----
float BezierPipeline::computeMaxEnergy(const std::vector<float> &flux) {
    return flux.empty() ? 0.0f : *std::max_element(flux.begin(), flux.end());
}

float BezierPipeline::computeTotalEnergy(const std::vector<float> &flux) {
    float sum = 0.0f;
    for (float v : flux) sum += v;
    return sum;
}

float BezierPipeline::computeSumAbove(const std::vector<float> &flux, float threshold) {
    float sum = 0.0f;
    for (float v : flux) if (v > threshold) sum += v;
    return sum;
}

float BezierPipeline::computeS95Level(const std::vector<float> &flux) {
    float total = computeTotalEnergy(flux);
    if (total <= 1e-6f) return 0.0f;
    float low = 0.0f, high = computeMaxEnergy(flux), level = 0.0f;
    for (int i = 0; i < 20; i++) {
        float mid = (low + high) * 0.5f;
        if (computeSumAbove(flux, mid) / total > 0.95f) low = mid;
        else { high = mid; level = mid; }
    }
    return level;
}

float BezierPipeline::computeS95Loss(float s95Level) {
    auto pass = m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeLoss);
    m_app.pushConstants(pass.cmd, m_pipeLoss.layout, &s95Level, sizeof(float));
    m_app.dispatch(pass.cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.endComputePass(pass);

    auto flux = readFlux();
    float level = std::max(s95Level, 1e-6f);
    float loss = 0.0f;
    for (float f : flux) {
        float s = 1.0f / (1.0f + std::exp(-6.0f * (f / level - 1.0f)));
        loss += s;
    }
    return loss;
}

float BezierPipeline::computeLossGPU(float s95Level) {
    // Stage 1: per-group partial reduction
    {
        auto pass = m_app.beginComputePass();
        m_app.bindPipeline(pass.cmd, m_pipeLossPartial);
        m_app.pushConstants(pass.cmd, m_pipeLossPartial.layout, &s95Level, sizeof(float));
        uint32_t totalPixels = m_cfg.pixelWidth * m_cfg.pixelHeight;
        uint32_t nGroups = (totalPixels + 255) / 256;
        m_app.dispatch(pass.cmd, nGroups, 1, 1);
        m_app.pipelineBarrier(pass.cmd);
        // Stage 2: final reduction
        m_app.bindPipeline(pass.cmd, m_pipeLossFinal);
        m_app.dispatch(pass.cmd, 1, 1, 1);
        m_app.endComputePass(pass);
    }
    float loss = 0.0f;
    m_app.downloadBuffer(m_s95CountBuf, &loss, sizeof(float));
    return loss;
}

void BezierPipeline::clearFluxGradient() {
    auto pass = m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeClearFluxGrad);
    m_app.dispatch(pass.cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.endComputePass(pass);
}

uint32_t BezierPipeline::countS95PixelsGPU(float s95Level) {
    uint32_t zero = 0;
    m_app.uploadBuffer(m_s95CountBuf, &zero, sizeof(uint32_t));
    auto pass = m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeCount);
    m_app.pushConstants(pass.cmd, m_pipeCount.layout, &s95Level, sizeof(float));
    m_app.dispatch(pass.cmd, (m_cfg.pixelWidth + 15) / 16, (m_cfg.pixelHeight + 15) / 16, 1);
    m_app.endComputePass(pass);
    uint32_t count = 0;
    m_app.downloadBuffer(m_s95CountBuf, &count, sizeof(uint32_t));
    return count;
}

void BezierPipeline::backwardPass() {
    uint32_t tileCount = (m_totalSpp + 255) / 256;
    // 1. Backward partial: compute per-group gradients
    {
        auto pass = m_app.beginComputePass();
        m_app.bindPipeline(pass.cmd, m_pipeBackward);
        m_app.dispatch(pass.cmd, m_totalPixels, tileCount, 1);
        m_app.endComputePass(pass);
    }

    // DIAG: read energy comparison values (only when --check-grad flag)
    // { ... } — disabled during optimization to reduce output

    // 2. Reduce partial gradients to final 16 values
    {
        auto pass = m_app.beginComputePass();
        m_app.bindPipeline(pass.cmd, m_pipeBackwardReduce);
        m_app.dispatch(pass.cmd, 1, 1, 1);
        m_app.endComputePass(pass);
    }
}

void BezierPipeline::adamStep(uint32_t iteration) {
    float lr = m_cfg.minLearningRate +
               (m_cfg.learningRate - m_cfg.minLearningRate) * (1.0f - (float)iteration / m_cfg.iterations);
    float pc[5] = {lr, m_cfg.beta1, m_cfg.beta2, m_cfg.adamEpsilon, (float)iteration};
    auto pass = m_app.beginComputePass();
    m_app.bindPipeline(pass.cmd, m_pipeAdam);
    m_app.pushConstants(pass.cmd, m_pipeAdam.layout, pc, sizeof(pc));
    m_app.dispatch(pass.cmd, 1, 1, 1);
    m_app.endComputePass(pass);
}

std::vector<float> BezierPipeline::readFlux() {
    std::vector<float> flux;
    m_app.downloadTexture(m_renderedFlux, flux);
    return flux;
}

// ---- Main optimization ----
OptimizationResult BezierPipeline::optimize(const HeliostatConfig &hc,
                                             const std::vector<std::array<float, 3>> &trainDirs,
                                             const std::vector<std::array<float, 3>> &validationDirs,
                                             const std::string &overrideBoltInitFile) {
    if (m_cfg.useBoltParameterization) {
        // ---- Bolt mode ----
        createPipelines();
        createBuffersAndTextures();
        createBoltPipelines();
        createBoltBuffers();

        float dist = std::sqrt(hc.position[0] * hc.position[0] + hc.position[1] * hc.position[1] +
                               hc.position[2] * hc.position[2]);
        fmt::print("Optimizing (BOLT mode, {} bolts): {} (dist={:.1f}m)\n", m_cfg.numBolts, hc.name, dist);
        fflush(stdout);

        // Resolve bolt init file: override > config > "auto" (by heliostat name + distance) > zero
        std::string boltFile = overrideBoltInitFile.empty() ? m_cfg.boltInitFile : overrideBoltInitFile;
        if (boltFile == "auto") {
            boltFile = "data/init/" + hc.name + "_" + std::to_string((int)dist) + "m_bolt_init.txt";
        }

        // Initialize bolt heights: from file, or zero (gravity sag)
        std::vector<float> initBolts(m_cfg.numBolts, 0.0f);
        if (!boltFile.empty()) {
            std::ifstream bf(boltFile);
            if (!bf) throw std::runtime_error("Cannot open bolt init file: " + boltFile);
            std::string line; int count = 0;
            while (std::getline(bf, line) && count < m_cfg.numBolts) {
                if (line.empty() || line[0] == '#') continue;
                const char *s = line.c_str(); char *end;
                float v1 = std::strtof(s, &end);
                while (*end == ' ' || *end == '\t') end++;
                if (*end && *end != '\n') { initBolts[count++] = std::strtof(end, nullptr); }
                else { initBolts[count++] = v1; }
            }
            fmt::print("  Elliptic init: {} bolts loaded, range [{:.3f}, {:.3f}] mm\n",
                count, *std::min_element(initBolts.begin(), initBolts.end()) * 1000.0f,
                *std::max_element(initBolts.begin(), initBolts.end()) * 1000.0f);
        }
        uploadBoltData(initBolts);

        // B-spline CP optimization: load T matrix if enabled
        if (m_cfg.useBSpline) {
            loadBSplineMatrix();
            fmt::print("  B-spline mode: {} CPs -> {} bolts\n", m_nCp, m_cfg.numBolts);
        }

        // Load ideal flux for MSE loss
        m_useMSELoss = m_cfg.enableMSELoss;
        if (m_useMSELoss) {
            float dist = std::sqrt(hc.position[0]*hc.position[0]+hc.position[1]*hc.position[1]+hc.position[2]*hc.position[2]);
            std::string idealPath = "results/" + hc.name + "_" + std::to_string((int)dist) + "m_sun0_flux.bin";
            std::ifstream f(idealPath, std::ios::binary);
            if (f) {
                f.seekg(0, std::ios::end);
                size_t fileSize = f.tellg();
                f.seekg(0, std::ios::beg);
                size_t nFloats = fileSize / sizeof(float);
                if (nFloats == m_totalPixels) {
                    m_idealFlux.resize(m_totalPixels);
                    f.read((char*)m_idealFlux.data(), m_totalPixels * sizeof(float));
                    fmt::print("  Using MSE loss (ideal flux from {}): {} pixels\n", idealPath, m_totalPixels);
                } else {
                    fmt::print("  Ideal flux size mismatch: {} floats vs {} pixels\n", nFloats, m_totalPixels);
                    m_useMSELoss = false;
                }
            } else {
                fmt::print("  MSE loss enabled but ideal flux .bin not found: {}\n", idealPath);
                fmt::print("  Run Bezier with enable_energy_loss=1 to generate it.\n");
                m_useMSELoss = false;
            }
        }

        OptimizationResult result;
        if (m_cfg.useBSpline) {
            result.bestControlY = m_cpHeights;  // CP heights (25)
        } else {
            result.bestControlY = initBolts;    // bolt heights (35)
        }

        float dlen = std::sqrt(hc.position[0] * hc.position[0] + hc.position[2] * hc.position[2]);
        std::array<float, 3> aimPoint;
        if (dlen > 1e-6f) {
            float dx = hc.position[0] / dlen, dz = hc.position[2] / dlen;
            aimPoint = {dx * m_cfg.receiverRadius, m_cfg.receiverPosition[1], dz * m_cfg.receiverRadius};
        } else {
            aimPoint = {0, m_cfg.receiverPosition[1], m_cfg.receiverRadius};
        }

        float pixelArea = (2.0f * 3.14159265f * m_cfg.receiverRadius * m_cfg.receiverHeight) / m_totalPixels;

        // A1: sparse pixel culling — active set depends only on heliostat position
        buildActivePixelList(hc.position);

        auto runValidation = [&]() {
            float totalS95 = 0.0f;
            for (const auto &sd : trainDirs) {
                updateUniforms(sd, hc.position, aimPoint);
                forwardRender(false);
                auto flux = readFlux();
                float level = computeS95Level(flux);
                if (level > 0) {
                    int count = 0;
                    for (float f : flux) if (f >= level) count++;
                    totalS95 += count * pixelArea;
                }
            }
            return totalS95 / trainDirs.size();
        };

        // Helper: cos-theta = |normal.y| for gravity scaling
        auto computeCosTheta = [&](const std::array<float,3>& sd, const std::array<float,3>& hp,
                                    const std::array<float,3>& ap) -> float {
            float sdx=sd[0], sdy=sd[1], sdz=sd[2];
            float sl = std::sqrt(sdx*sdx+sdy*sdy+sdz*sdz);
            float rdx=ap[0]-hp[0], rdy=ap[1]-hp[1], rdz=ap[2]-hp[2];
            float rl = std::sqrt(rdx*rdx+rdy*rdy+rdz*rdz);
            float ny = sdy/sl + rdy/rl;
            float nx = sdx/sl + rdx/rl, nz = sdz/sl + rdz/rl;
            float nl = std::sqrt(nx*nx+ny*ny+nz*nz);
            return std::abs(ny) / nl;
        };

        // Diagnostic first direction
        {
            updateUniforms(trainDirs[0], hc.position, aimPoint);
            boltForwardSurface(computeCosTheta(trainDirs[0], hc.position, aimPoint));
            forwardRender(false);
            auto f = readFlux();
            int nz = 0; float mx = 0, sm = 0;
            for (float v : f) { if (v > 0) { nz++; sm += v; if (v > mx) mx = v; } }
            fmt::print("  init flux: nzPix={} maxF={:.2f} sumF={:.2f}\n", nz, mx, sm);
            // Save initial flux as raw float32 binary (convert to NPY via Python)
            if (m_cfg.enableMSELoss) {

                float dist = std::sqrt(hc.position[0]*hc.position[0]+hc.position[1]*hc.position[1]+hc.position[2]*hc.position[2]);
                std::string rawPath = "results/" + hc.name + "_" + std::to_string((int)dist) + "m_sun0_flux.bin";
                std::ifstream check(rawPath);
                if (!check) {
                    std::ofstream ofs(rawPath, std::ios::binary);
                    ofs.write((char*)f.data(), f.size() * sizeof(float));
                    fmt::print("  Saved ideal flux (raw): {} ({} floats)\n", rawPath, f.size());
                }
            }
        }
        float avgS95 = runValidation();
        fmt::print(" S95={:.4f} m^2\n", avgS95);
        result.initialS95 = avgS95; result.bestS95 = avgS95;
        result.lossHistory.resize(m_cfg.iterations, 0.0f);
        result.s95History.resize(m_cfg.iterations, 0.0f);

        int patience = m_cfg.patience;
        auto tStart = std::chrono::steady_clock::now();

        // A1/L1 feature flags (logged once)
        fmt::print("  Ray pre-cull: {} (margin={:.1f} mrad), efficiency lambda={:.4f}\n",
                   m_cfg.rayCull ? "ON" : "OFF", m_cfg.rayCullMarginMrad, m_cfg.lambdaEnergy);
        // L1: per-sun reference energy captured at iteration 0 (GPU S95 path only)
        std::vector<float> energyRef(trainDirs.size(), 0.0f);

        for (uint32_t iter = 0; iter < m_cfg.iterations; iter++) {
            auto tIter = std::chrono::steady_clock::now();
            m_currentIteration = iter;  // P1-L3: per-iteration seed
            float totalLoss = 0.0f;

            // B-spline: map CP heights to bolt heights before forward pass
            if (m_cfg.useBSpline) {
                cpToBoltHeights();
            }

            // Zero boltHeightGradient
            uint32_t n = m_cfg.numBolts;
            std::vector<float> zeros(n, 0.0f);
            m_app.uploadBuffer(m_boltHeightGradient, zeros.data(), n * sizeof(float));

            const bool useMse = m_useMSELoss && !m_idealFlux.empty();
            // A/B harness: BEZIER_S95_GPU=0 reverts to the CPU readFlux +
            // binary-search path (two submits per sun) for direct comparison.
            static const bool s_gpuS95 = []() {
                const char *e = getenv("BEZIER_S95_GPU");
                return !(e && e[0] == '0');
            }();
            if (m_cfg.lambdaEnergy > 0.0f && (!s_gpuS95 || useMse)) {
                static bool warned = false;
                if (!warned) {
                    fmt::print("  WARNING: lambda_energy>0 requires the GPU S95 path and non-MSE loss; ignoring.\n");
                    warned = true;
                }
            }
            for (size_t si = 0; si < trainDirs.size(); si++) {
                const auto &sd = trainDirs[si];
                // Host-visible UBOs (sun/receiver/heliostat) are persistent-mapped:
                // uploadBuffer is a bare memcpy with no sync — keep it on the CPU.
                updateUniforms(sd, hc.position, aimPoint);

                // A2: sunBatchFlat is DEVICE-LOCAL — uploadBuffer would spin up a
                // staging buffer + submit + vkQueueWaitIdle per sun. Update it
                // inline in the command buffer instead (36 fewer submits/iter).
                float batch[8] = {sd[0], sd[1], sd[2], 0, 0, 0, 0, 0};
                {
                    float cosTheta = computeCosTheta(sd, hc.position, aimPoint);
                    uint32_t lo, hi; float gt;
                    packGravityParams(cosTheta, lo, hi, gt);
                    std::memcpy(&batch[4], &lo, 4); std::memcpy(&batch[5], &hi, 4); batch[6] = gt;
                }

                if (!useMse && s_gpuS95) {
                    // GPU S95 path: forward + cooperative S95 level find + sigmoid
                    // loss + backward in ONE submit. The level stays on GPU
                    // (m_s95State) — no readFlux()/CPU binary search per sun.
                    // L1: at iter 0 the efficiency term is off and the per-sun
                    // reference energy is captured from m_s95State[2] afterwards.
                    auto pass = m_app.beginComputePassRaw();
                    if (si == 0) m_app.fillBufferCmd(pass.cmd, m_lossAccum, 0u);
                    m_app.updateBufferCmd(pass.cmd, m_sunBatchFlat, 0, 8 * sizeof(float), batch);  // A2
                    boltForwardSurfaceCmd(pass.cmd, 1);
                    clearRayValidityCmd(pass.cmd);
                    forwardRenderCmd(pass.cmd);
                    computeS95FindLevelCmd(pass.cmd);
                    clearFluxGradientCmd(pass.cmd);
                    computeS95LossBUFCmd(pass.cmd,
                        (iter == 0) ? 0.0f : energyRef[si],
                        (iter == 0) ? 0.0f : m_cfg.lambdaEnergy);
                    boltBackwardPassCmd(pass.cmd);
                    m_app.submitAndWait(pass);
                    if (iter == 0 && m_cfg.lambdaEnergy > 0.0f) {
                        float st4[4] = {0.0f, 0.0f, 0.0f, 0.0f};
                        m_app.downloadBuffer(m_s95State, st4, sizeof(st4));
                        energyRef[si] = st4[2];
                    }
                    continue;
                }

                // CPU S95 path: forward submit, readFlux + binary search, second submit
                {
                    auto pass = m_app.beginComputePassRaw();
                    m_app.updateBufferCmd(pass.cmd, m_sunBatchFlat, 0, 8 * sizeof(float), batch);  // A2
                    boltForwardSurfaceCmd(pass.cmd, 1);
                    clearRayValidityCmd(pass.cmd);
                    forwardRenderCmd(pass.cmd);
                    m_app.submitAndWait(pass);
                }

                auto flux = readFlux();
                float s95Level = computeS95Level(flux);
                if (s95Level > 0) {
                    if (useMse) {
                        // MSE loss: compute gradient on CPU, upload to fluxGradient
                        std::vector<float> mseGrad(m_totalPixels);
                        float mseLoss = 0.0f;
                        for (uint32_t p = 0; p < m_totalPixels; p++) {
                            float diff = flux[p] - m_idealFlux[p];
                            mseGrad[p] = 2.0f * diff / m_totalPixels;
                            mseLoss += diff * diff;
                        }
                        mseLoss /= m_totalPixels;
                        totalLoss += mseLoss;
                        m_app.uploadTexture(m_fluxGradient, mseGrad.data());
                        // Phase 2 batch: backward only (MSE gradient already uploaded)
                        auto pass = m_app.beginComputePassRaw();
                        boltBackwardPassCmd(pass.cmd);
                        m_app.submitAndWait(pass);
                    } else {
                        // Phase 2 batch 2: clearFluxGradient + computeS95Loss + boltBackward
                        {
                            auto pass = m_app.beginComputePassRaw();
                            clearFluxGradientCmd(pass.cmd);
                            computeS95LossCmd(pass.cmd, s95Level);
                            boltBackwardPassCmd(pass.cmd);
                            m_app.submitAndWait(pass);
                        }
                        // Compute scalar loss from already-read flux (avoids extra readFlux)
                        float level = std::max(s95Level, 1e-6f);
                        float lossVal = 0.0f;
                        for (float f : flux) {
                            float s = 1.0f / (1.0f + std::exp(-6.0f * (f / level - 1.0f)));
                            lossVal += s;
                        }
                        totalLoss += lossVal;
                    }
                }
            }
            if (!useMse && s_gpuS95) {
                // Scalar sigmoid loss accumulated on GPU (fixed-point x1e3)
                uint32_t lossFixed = 0;
                m_app.downloadBuffer(m_lossAccum, &lossFixed, sizeof(uint32_t));
                totalLoss = (float)lossFixed * 1e-3f;
            }
            if (m_cfg.useBSpline) {
                // Download bolt gradients, project to CPs, CPU Adam step
                boltGradToCpGrad();
                cpAdamStep(iter + 1);
            } else {
                boltAdamStep(iter + 1);
            }

            result.lossHistory[iter] = totalLoss;

            if (iter < 3 || iter % 10 == 0) {
                avgS95 = runValidation();
            }
            result.s95History[iter] = avgS95;

            if (iter < 3 || iter % 10 == 0) {
                double iterTime = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - tIter).count();
                fmt::print("  Iter {:3d}: Loss={:.6f}, S95={:.4f} m^2, time={:.1f}s\n",
                    iter, totalLoss, avgS95, iterTime);
            }

            if (avgS95 < result.bestS95) {
                result.bestS95 = avgS95;
                if (m_cfg.useBSpline) {
                    result.bestControlY = m_cpHeights;
                } else {
                    m_app.downloadBuffer(m_boltHeights, result.bestControlY.data(), n * sizeof(float));
                }
                patience = m_cfg.patience;
            } else if (iter > 0 && (iter < 3 || iter % 10 == 0)) {
                float rc = std::abs(result.s95History[iter] - result.s95History[iter-1]) /
                          std::max(result.s95History[iter-1], 1e-10f);
                if (rc < 1e-6f) {
                    if (--patience <= 0) {
                        fmt::print("  Early stopping at iter {}\n", iter);
                        result.lossHistory.resize(iter + 1);
                        result.s95History.resize(iter + 1);
                        break;
                    }
                } else {
                    patience = m_cfg.patience;
                }
            }
        }

        auto tEnd = std::chrono::steady_clock::now();
        double totalTime = std::chrono::duration<double>(tEnd - tStart).count();
        fmt::print("  Done. Best S95: {:.4f} (init: {:.4f}, reduction: {:.1f}%)\n",
                   result.bestS95, result.initialS95,
                   (result.initialS95 - result.bestS95) / std::max(result.initialS95, 1e-6f) * 100.0f);
        fmt::print("  Time: total={:.1f}s\n", totalTime);
        return result;
    }

    // ---- Bezier mode (original path) ----
    createPipelines();
    createBuffersAndTextures();

    float dist = std::sqrt(hc.position[0] * hc.position[0] + hc.position[1] * hc.position[1] +
                           hc.position[2] * hc.position[2]);
    fmt::print("Optimizing: {} (dist={:.1f}m)\n", hc.name, dist);
    fflush(stdout);

    auto initCY = fitBezierFromEllipse(hc.A, hc.B, hc.C, m_cfg.heliostatWidth, m_cfg.heliostatLength);
    uploadHeliostatData(initCY);

    OptimizationResult result;
    result.lossHistory.resize(m_cfg.iterations, 0.0f);
    result.s95History.resize(m_cfg.iterations, 0.0f);
    result.bestControlY = initCY;

    // Aim point: project heliostat position onto receiver cylinder
    float dlen = std::sqrt(hc.position[0] * hc.position[0] + hc.position[2] * hc.position[2]);
    std::array<float, 3> aimPoint;
    if (dlen > 1e-6f) {
        float dx = hc.position[0] / dlen, dz = hc.position[2] / dlen;
        aimPoint = {dx * m_cfg.receiverRadius, m_cfg.receiverPosition[1], dz * m_cfg.receiverRadius};
    } else {
        aimPoint = {0, m_cfg.receiverPosition[1], m_cfg.receiverRadius};
    }

    float pixelArea = (2.0f * 3.14159265f * m_cfg.receiverRadius * m_cfg.receiverHeight) / m_totalPixels;

    // A1: sparse pixel culling — active set depends only on heliostat position
    buildActivePixelList(hc.position);

    auto runValidation = [&]() {
        float totalS95 = 0.0f;
        for (const auto &sd : trainDirs) {
            updateUniforms(sd, hc.position, aimPoint);
            forwardRender();
            auto flux = readFlux();
            float level = computeS95Level(flux);
            if (level > 0) {
                int count = 0;
                for (float f : flux) if (f >= level) count++;
                totalS95 += count * pixelArea;
            }
        }
        return totalS95 / trainDirs.size();
    };

    // Diagnostic: first training sun direction
    {
        updateUniforms(trainDirs[0], hc.position, aimPoint);
        forwardRender();
        auto f = readFlux();
        int nz = 0; float mx = 0, sm = 0;
        for (float v : f) { if (v > 0) { nz++; sm += v; if (v > mx) mx = v; } }
        fmt::print("  init flux: nzPix={} maxF={:.2f} sumF={:.2f}\n", nz, mx, sm);
        // Save initial flux as raw binary (convert to NPY via Python)
        if (m_cfg.enableMSELoss) {
            float dist = std::sqrt(hc.position[0]*hc.position[0]+hc.position[1]*hc.position[1]+hc.position[2]*hc.position[2]);
            std::string rawPath = "results/" + hc.name + "_" + std::to_string((int)dist) + "m_sun0_flux.bin";
            std::ifstream check(rawPath);
            if (!check) {
                std::ofstream ofs(rawPath, std::ios::binary);
                ofs.write((char*)f.data(), f.size() * sizeof(float));
                fmt::print("  Saved ideal flux (raw): {}\n", rawPath);
            }
        }
    }
    // Per-direction S95 average over 36 training directions
    float totalS95Quick = 0;
    int nDirs = std::min((int)trainDirs.size(), 36);
    for (int vi = 0; vi < nDirs; vi++) {
        updateUniforms(trainDirs[vi], hc.position, aimPoint);
        forwardRender();
        auto f = readFlux();
        float lv = computeS95Level(f);
        if (lv > 0) { int c = 0; for (float v : f) if (v >= lv) c++; totalS95Quick += c * pixelArea; }
    }
    float quickS95 = (nDirs > 0) ? totalS95Quick / nDirs : 0;
    fmt::print(" S95={:.4f} m^2\n", quickS95);
    result.initialS95 = quickS95; result.bestS95 = quickS95;
    result.lossHistory.resize(m_cfg.iterations, 0.0f);
    result.s95History.resize(m_cfg.iterations, 0.0f);

    int patience = m_cfg.patience;
    auto tStart = std::chrono::steady_clock::now();
    double timeFwd = 0, timeBwd = 0, timeAdam = 0, timeVal = 0;

    // AD gradient with S95 sigmoid loss (matching Taichi)
    for (uint32_t iter = 0; iter < m_cfg.iterations; iter++) {
        auto tIter = std::chrono::steady_clock::now();
        m_currentIteration = iter;  // P1-L3
        float totalLoss = 0.0f;
        std::vector<float> z16(16, 0.0f);
        m_app.uploadBuffer(m_controlYGradient, z16.data(), 16 * sizeof(float));

        {
            auto pass = m_app.beginComputePass();
            m_app.bindPipeline(pass.cmd, m_pipeBezier);
            m_app.dispatch(pass.cmd, 1, 1, 1);
            m_app.endComputePass(pass);
        }

        for (const auto &sd : trainDirs) {
            updateUniforms(sd, hc.position, aimPoint);
            clearRayValidity();  // P2: clear before each sun direction
            auto t0 = std::chrono::steady_clock::now();
            forwardRender(false);
            auto t1 = std::chrono::steady_clock::now();
            timeFwd += std::chrono::duration<double>(t1 - t0).count();

            auto flux = readFlux();
            float s95Level = computeS95Level(flux);
            if (s95Level > 0) {
                clearFluxGradient();
                totalLoss += computeS95Loss(s95Level);

                auto t2 = std::chrono::steady_clock::now();
                backwardPass();
                auto t3 = std::chrono::steady_clock::now();
                timeBwd += std::chrono::duration<double>(t3 - t2).count();
            }
        }

        auto tPreAdam = std::chrono::steady_clock::now();
        adamStep(iter + 1);
        auto tPostAdam = std::chrono::steady_clock::now();
        timeAdam += std::chrono::duration<double>(tPostAdam - tPreAdam).count();

        result.lossHistory[iter] = totalLoss;

        float avgS95 = result.bestS95;
        if (iter < 3 || iter % 10 == 0) {
            auto tv0 = std::chrono::steady_clock::now();
            avgS95 = runValidation();
            auto tv1 = std::chrono::steady_clock::now();
            timeVal += std::chrono::duration<double>(tv1 - tv0).count();
        }
        result.s95History[iter] = avgS95;

        if (iter < 3 || iter % 10 == 0) {
            double iterTime = std::chrono::duration<double>(tPostAdam - tIter).count();
            fmt::print("  Iter {:3d}: Loss={:.6f}, S95={:.4f} m^2, time={:.1f}s\n",
                iter, totalLoss, avgS95, iterTime);
        }

        if (avgS95 < result.bestS95) {
            result.bestS95 = avgS95;
            m_app.downloadBuffer(m_controlY, result.bestControlY.data(), 16 * sizeof(float));
            patience = m_cfg.patience;
        } else if (iter > 0 && (iter < 3 || iter % 10 == 0)) {
            float rc = std::abs(result.s95History[iter] - result.s95History[iter-1]) /
                      std::max(result.s95History[iter-1], 1e-10f);
            if (rc < 1e-6f) {
                if (--patience <= 0) {
                    fmt::print("  Early stopping at iter {}\n", iter);
                    result.lossHistory.resize(iter + 1);
                    result.s95History.resize(iter + 1);
                    break;
                }
            } else {
                patience = m_cfg.patience;
            }
        }
    }

    auto tEnd = std::chrono::steady_clock::now();
    double totalTime = std::chrono::duration<double>(tEnd - tStart).count();
    fmt::print("  Done. Best S95: {:.4f} (init: {:.4f}, reduction: {:.1f}%)\n",
               result.bestS95, result.initialS95,
               (result.initialS95 - result.bestS95) / std::max(result.initialS95, 1e-6f) * 100.0f);
    fmt::print("  Time: total={:.1f}s fwd={:.1f}s bwd={:.1f}s adam={:.3f}s val={:.1f}s\n",
               totalTime, timeFwd, timeBwd, timeAdam, timeVal);
    return result;
}

void BezierPipeline::verifyGradients(const std::vector<float> &initCY, const std::array<float, 3> &sunDir,
                                      const std::array<float, 3> &helioPos, const std::array<float, 3> &aimPoint,
                                      float pixelArea) {
    createPipelines();
    createBuffersAndTextures();

    const float eps = 1e-3f; // larger eps to reduce FD numerical noise
    // FD loss with VARIABLE S95 (recomputed each perturbation) — matches original formulation
    auto computeLossVarS95 = [&](const std::vector<float> &cy) -> float {
        uploadHeliostatData(cy);
        updateUniforms(sunDir, helioPos, aimPoint);
        forwardRender();
        auto flux = readFlux();
        float level = computeS95Level(flux);
        if (level <= 0) return 0.0f;
        float loss = 0.0f;
        for (float f : flux) {
            float s = 1.0f / (1.0f + std::exp(-6.0f * (f / std::max(level, 1e-6f) - 1.0f)));
            loss += s;
        }
        return loss;
    };
    // FD loss with CONSTANT S95 — matches AD formulation (fluxGradient uses baseLevel)
    auto computeLossConstS95 = [&](const std::vector<float> &cy, float fixedLevel) -> float {
        uploadHeliostatData(cy);
        updateUniforms(sunDir, helioPos, aimPoint);
        forwardRender();
        auto flux = readFlux();
        float loss = 0.0f;
        for (float f : flux) {
            float s = 1.0f / (1.0f + std::exp(-6.0f * (f / std::max(fixedLevel, 1e-6f) - 1.0f)));
            loss += s;
        }
        return loss;
    };

    uploadHeliostatData(initCY);
    updateUniforms(sunDir, helioPos, aimPoint);

    fmt::print("  initCY (4x4 Bezier control points Y, in meters):\n  ");
    for (int r = 0; r < 4; r++) {
        fmt::print("  row{}: ", r);
        for (int c = 0; c < 4; c++) fmt::print("{: .6f} ", initCY[r*4+c]);
    }
    fmt::print("\n");

    std::vector<float> zeroGrad(16, 0.0f);
    m_app.uploadBuffer(m_controlYGradient, zeroGrad.data(), 16 * sizeof(float));
    forwardRender();
    auto flux = readFlux();
    float baseLevel = computeS95Level(flux);

    {
        int nz = 0; float mx = 0, sm = 0;
        for (float v : flux) { if (v > 0) { nz++; sm += v; if (v > mx) mx = v; } }
        fmt::print("  base flux: nzPix={} maxF={:.6e} sumF={:.6e} baseLevel={:.6e}\n", nz, mx, sm, baseLevel);
        fmt::print("  forward flux[0]={:.6e}  flux[1]={:.6e}  flux[3925]={:.6e}\n",
            flux[0], flux[1], flux[3925]);
        float fwdLoss = 0.0f;
        for (float f : flux) {
            float s = 1.0f / (1.0f + std::exp(-6.0f * (f / std::max(baseLevel, 1e-6f) - 1.0f)));
            fwdLoss += s;
        }
        fmt::print("  forward Loss (constant S95={:.4f}) = {:.6f}\n", baseLevel, fwdLoss);

        // Verify yGrid matches Bezier computation
        uint32_t nPts = m_cfg.gridSize * m_cfg.gridSize;
        std::vector<float> yg(nPts);
        m_app.downloadBuffer(m_yGrid, yg.data(), nPts * sizeof(float));
        fmt::print("  yGrid[0]={:.6f}  yGrid[center]={:.6f}  yGrid[end]={:.6f}\n",
            yg[0], yg[nPts / 2], yg[nPts - 1]);
    }
    // === TEST: Simple total-energy loss (no S95) to verify AD gradient ===
    fmt::print("\n--- Simple Loss: Total Flux (dL/dflux = 1) ---\n");
    clearFluxGradient();
    // Upload uniform gradient (all 1.0) to fluxGradient for simple total-flux test
    {
        std::vector<float> uniformGrad(m_totalPixels, 1.0f);
        m_app.uploadTexture(m_fluxGradient, uniformGrad.data());
    }
    m_app.uploadBuffer(m_controlYGradient, zeroGrad.data(), 16 * sizeof(float));
    backwardPass();
    std::vector<float> adGradSimple(16);
    m_app.downloadBuffer(m_controlYGradient, adGradSimple.data(), 16 * sizeof(float));

    auto computeFluxSum = [&](const std::vector<float> &cy) -> float {
        uploadHeliostatData(cy);
        updateUniforms(sunDir, helioPos, aimPoint);
        forwardRender();
        auto f = readFlux();
        float s = 0; for (float v : f) s += v; return s;
    };

    fmt::print("{:>4s} {:>14s} {:>14s} {:>14s} {:>10s}\n", "CP", "FD(fluxSum)", "AutoDiff", "Diff", "Match?");
    fmt::print("{}\n", std::string(60, '-'));
    int matchSimple = 0;
    for (int i = 0; i < 16; i++) {
        auto cyP = initCY; cyP[i] += eps;
        auto cyN = initCY; cyN[i] -= eps;
        float fd = (computeFluxSum(cyP) - computeFluxSum(cyN)) / (2.0f * eps);
        float ad = adGradSimple[i];
        float diff = std::abs(fd - ad);
        float rel = (std::abs(fd) + std::abs(ad) > 1e-10f)
                       ? diff / (std::abs(fd) + std::abs(ad)) * 2.0f : 0.0f;
        bool m = rel < 0.1f || diff < 1e-6f;
        if (m) matchSimple++;
        fmt::print("{:>4d} {:>14.6f} {:>14.6f} {:>14.6f} {:>10s}\n", i, fd, ad, diff, m ? "YES" : "NO");
    }
    fmt::print("{}Simple loss gradient match: {}/16\n\n", std::string(60, '-'), matchSimple);

    // Now run the actual S95 loss test
    m_app.uploadBuffer(m_controlYGradient, zeroGrad.data(), 16 * sizeof(float));
    clearFluxGradient();
    computeS95Loss(baseLevel);
    backwardPass();
    // Read progressive AD test results (debugBuf[0..3])
    {
        std::vector<float> adTest(4);
        m_app.downloadBuffer(m_s95CountBuf, adTest.data(), 4 * sizeof(float));
        fmt::print("  AD test: dY/dc00={:.6e} dNrm/dc00={:.6e} dGlass/dc00={:.6e} dFull/dc00={:.6e}\n",
            adTest[0], adTest[1], adTest[2], adTest[3]);
    }
    // Check gradPartial for non-zero values (debug first few entries)
    {
        std::vector<float> gpCheck(32);
        m_app.downloadBuffer(m_gradPartial, gpCheck.data(), 32 * sizeof(float));
        float gpMax = 0.0f; int gpNz = 0;
        for (int i=0; i<32; i++) { if(gpCheck[i]!=0){gpNz++; gpMax=std::max(gpMax,std::abs(gpCheck[i]));} }
        fmt::print("  gradPartial check: nz={}/32 max={:.6e}\n", gpNz, gpMax);
    }
    std::vector<float> adGrad(16);
    m_app.downloadBuffer(m_controlYGradient, adGrad.data(), 16 * sizeof(float));

    fmt::print("=== Gradient Verification (eps={}) ===\n", eps);
    fmt::print("{:>4s} {:>14s} {:>14s} {:>14s} {:>14s} {:>10s}\n",
        "CP", "FD(varS95)", "FD(constS95)", "AutoDiff", "Diff(cS95)", "Match?");
    fmt::print("{}\n", std::string(80, '-'));

    int matchVar = 0, matchConst = 0;
    for (int i = 0; i < 16; i++) {
        auto cyP = initCY;
        auto cyN = initCY;
        cyP[i] += eps;
        cyN[i] -= eps;

        float lpVar = computeLossVarS95(cyP);
        float lnVar = computeLossVarS95(cyN);
        float fdVar = (lpVar - lnVar) / (2.0f * eps);

        float lpConst = computeLossConstS95(cyP, baseLevel);
        float lnConst = computeLossConstS95(cyN, baseLevel);
        float fdConst = (lpConst - lnConst) / (2.0f * eps);

        float ad = adGrad[i];
        float diffConst = std::abs(fdConst - ad);
        float relConst = (std::abs(fdConst) + std::abs(ad) > 1e-10f)
                            ? diffConst / (std::abs(fdConst) + std::abs(ad)) * 2.0f : 0.0f;
        bool matchC = relConst < 0.1f || diffConst < 1e-6f;
        if (matchC) matchConst++;

        fmt::print("{:>4d} {:>14.6f} {:>14.6f} {:>14.6f} {:>14.6f} {:>10s}\n",
                   i, fdVar, fdConst, ad, diffConst, matchC ? "YES" : "NO");
    }
    fmt::print("{}Gradient match (constant S95): {}/16\n", std::string(80, '-'), matchConst);

    uploadHeliostatData(initCY);
}

// Forward declaration for verifyBoltGradients helper
static void printGradCompare(const char *, const std::vector<float> &,
                             const std::vector<float> &, uint32_t);

// Static helper: compute cos-theta = |normal.y| for gravity scaling
// Mirror normal = bisector of sun direction and reflection direction (from heliostat to aim point)
static float computeCosThetaStatic(const std::array<float,3>& sd, const std::array<float,3>& hp,
                                    const std::array<float,3>& ap) {
    float sdx=sd[0], sdy=sd[1], sdz=sd[2];
    float sl = std::sqrt(sdx*sdx+sdy*sdy+sdz*sdz);
    float rdx=ap[0]-hp[0], rdy=ap[1]-hp[1], rdz=ap[2]-hp[2];
    float rl = std::sqrt(rdx*rdx+rdy*rdy+rdz*rdz);
    float ny = sdy/sl + rdy/rl;
    float nx = sdx/sl + rdx/rl, nz = sdz/sl + rdz/rl;
    float nl = std::sqrt(nx*nx+ny*ny+nz*nz);
    return std::abs(ny) / nl;
}

void BezierPipeline::verifyBoltGradients(const std::array<float, 3> &sunDir,
                                          const std::array<float, 3> &helioPos,
                                          const std::array<float, 3> &aimPoint, float pixelArea) {
    createPipelines();
    createBuffersAndTextures();
    createBoltPipelines();
    createBoltBuffers();

    uint32_t n = m_cfg.numBolts;
    const float eps = 2e-3f; // 2mm — dominant over render noise

    // Build two init configurations: zero-init and small-alternating
    struct InitConfig { const char *name; std::vector<float> heights; };
    std::vector<InitConfig> initConfigs;
    {
        std::vector<float> zero(n, 0.0f);
        initConfigs.push_back({"zero init", zero});
    }
    {
        std::vector<float> alt(n, 0.0f);
        for (uint32_t i = 0; i < n; i++)
            alt[i] = 0.001f * float(int(i % 5) - 2); // -2..+2 mm alternating
        initConfigs.push_back({"alt init (-2..+2mm)", alt});
    }

    updateUniforms(sunDir, helioPos, aimPoint);
    float cosTheta = computeCosThetaStatic(sunDir, helioPos, aimPoint);

    fmt::print("\n========================================\n");
    fmt::print("=== Bolt Gradient Verification (n={}) ===\n", n);
    fmt::print("  eps = {:.1e} m, sun = ({:.3f},{:.3f},{:.3f})\n",
               eps, sunDir[0], sunDir[1], sunDir[2]);
    fmt::print("  cosθ={:.4f} → gravity angle={:.2f}°\n",
               cosTheta, std::acos(std::max(0.0f, std::min(1.0f, cosTheta))) * 180.0f / 3.14159265f);

    for (const auto &ic : initConfigs) {
        const auto &initHeights = ic.heights;
        fmt::print("\n────────────────────────────────────────\n");
        fmt::print("  Config: {}\n", ic.name);
        uploadBoltData(initHeights);

        boltForwardSurface(cosTheta);
        forwardRender(false);
        auto baseFlux = readFlux();

        float s95Level = computeS95Level(baseFlux);
        float s95Loss = computeS95Loss(s95Level);
        float fluxSum = std::accumulate(baseFlux.begin(), baseFlux.end(), 0.0f);
        fmt::print("  S95 level: {:.4f}, S95 loss: {:.6f}, flux sum: {:.1f}\n",
                   s95Level, s95Loss, fluxSum);

        // ── Test 1: total flux sum ──
        fmt::print("\n  ── Test 1: Total Flux Sum ──\n");
        std::vector<float> adGradFlux(n, 0.0f);
        {
            clearFluxGradient();
            // Upload uniform gradient (all 1.0) to fluxGradient for total-flux test
            {
                std::vector<float> uniformGrad(m_totalPixels, 1.0f);
                m_app.uploadTexture(m_fluxGradient, uniformGrad.data());
            }
            boltBackwardPass();
            m_app.downloadBuffer(m_boltHeightGradient, adGradFlux.data(), n * sizeof(float));
        }
        std::vector<float> fdGradFlux(n, 0.0f);
        auto fluxSumForHeights = [&](const std::vector<float> &h) -> float {
            uploadBoltData(h);
            boltForwardSurface(cosTheta);
            forwardRender(false);
            auto f = readFlux();
            return std::accumulate(f.begin(), f.end(), 0.0f);
        };
        // Only run FD for the second config (alt init) to save time
        if (&ic == &initConfigs.back()) {
            for (uint32_t i = 0; i < n; i++) {
                auto hP = initHeights; hP[i] += eps;
                auto hN = initHeights; hN[i] -= eps;
                fdGradFlux[i] = (fluxSumForHeights(hP) - fluxSumForHeights(hN)) / (2.0f * eps);
                if ((i + 1) % 10 == 0) fmt::print("    {}/{}\n", i + 1, n);
            }
            printGradCompare("Total Flux", fdGradFlux, adGradFlux, n);
        } else {
            fmt::print("    (AD-only for this config, FD skipped)\n");
            // Print AD values for diagnostic
            for (uint32_t i = 0; i < n; i++)
                fmt::print("    bolt {}: AD={:.4e}\n", i, adGradFlux[i]);
        }

        // ── Test 2: S95 sigmoid loss ──
        fmt::print("\n  ── Test 2: S95 Sigmoid Loss ──\n");
        std::vector<float> adGradS95(n, 0.0f);
        {
            clearFluxGradient();
            computeS95Loss(s95Level);
            boltBackwardPass();
            m_app.downloadBuffer(m_boltHeightGradient, adGradS95.data(), n * sizeof(float));
        }
        if (&ic == &initConfigs.back()) {
            std::vector<float> fdGradS95(n, 0.0f);
            auto s95LossForHeights = [&](const std::vector<float> &h) -> float {
                uploadBoltData(h);
                boltForwardSurface(cosTheta);
                forwardRender(false);
                return computeS95Loss(s95Level);
            };
            for (uint32_t i = 0; i < n; i++) {
                auto hP = initHeights; hP[i] += eps;
                auto hN = initHeights; hN[i] -= eps;
                fdGradS95[i] = (s95LossForHeights(hP) - s95LossForHeights(hN)) / (2.0f * eps);
                if ((i + 1) % 10 == 0) fmt::print("    {}/{}\n", i + 1, n);
            }
            printGradCompare("S95 Sigmoid", fdGradS95, adGradS95, n);
        } else {
            fmt::print("    (AD-only for this config)\n");
            for (uint32_t i = 0; i < n; i++)
                fmt::print("    bolt {}: AD={:.4e}\n", i, adGradS95[i]);
        }
    }

    // ── Eps sweep for 3 representative bolts ──
    {
        const std::vector<float> &h = initConfigs.back().heights; // use alt init
        uploadBoltData(h);
        boltForwardSurface(cosTheta);
        forwardRender(false);
        auto baseFlux = readFlux();
        float s95Level = computeS95Level(baseFlux);

        // Representative bolts: corner (0), edge (3), center (17)
        uint32_t testBolts[] = {0, 3, 17};
        float epsValues[] = {0.5e-3f, 1e-3f, 2e-3f, 5e-3f, 10e-3f};

        fmt::print("\n────────────────────────────────────────\n");
        fmt::print("  Eps Convergence Sweep (S95 loss)\n");
        fmt::print("  Bolts: #0 (corner), #3 (edge), #17 (center)\n");
        fmt::print("  {:>8s} {:>6s} {:>14s} {:>14s} {:>10s}\n",
                   "eps(mm)", "Bolt", "FD", "AD", "RelErr%");

        for (float ep : epsValues) {
            for (uint32_t bi : testBolts) {
                auto hP = h; hP[bi] += ep;
                auto hN = h; hN[bi] -= ep;
                float lp = 0, ln = 0;
                {
                    uploadBoltData(hP);
                    boltForwardSurface(cosTheta);
                    forwardRender(false);
                    lp = computeS95Loss(s95Level);
                }
                {
                    uploadBoltData(hN);
                    boltForwardSurface(cosTheta);
                    forwardRender(false);
                    ln = computeS95Loss(s95Level);
                }
                float fd = (lp - ln) / (2.0f * ep);

                // Compute AD for this bolt
                uploadBoltData(h);
                boltForwardSurface(cosTheta);
                forwardRender(false);
                clearFluxGradient();
                computeS95Loss(s95Level);
                boltBackwardPass();
                std::vector<float> adAll(n);
                m_app.downloadBuffer(m_boltHeightGradient, adAll.data(), n * sizeof(float));
                float ad = adAll[bi];

                float denom = std::max(std::abs(fd) + std::abs(ad), 1e-12f);
                float relErr = std::abs(fd - ad) / denom * 2.0f * 100.0f;
                fmt::print("  {:8.1f} {:>6d} {:>14.4e} {:>14.4e} {:>9.1f}%\n",
                           ep * 1000.0f, bi, fd, ad, relErr);
            }
        }
    }

    uploadBoltData(initConfigs.back().heights);
}

// Helper: print per-bolt gradient comparison and summary metrics
static void printGradCompare(const char *label,
                             const std::vector<float> &fdGrad,
                             const std::vector<float> &adGrad,
                             uint32_t n) {
    int signMatch = 0;
    float sumAbsFD = 0.0f, sumAbsAD = 0.0f;
    float dotProd = 0.0f, normFDSq = 0.0f, normADSq = 0.0f;
    std::vector<float> relErrors(n);

    fmt::print("\n{:>4s} {:>12s} {:>12s} {:>12s} {:>8s} {:>6s}\n",
               "Bolt", "FD", "AD", "|FD-AD|", "RelErr%", "Sign?");
    fmt::print("{}\n", std::string(62, '-'));

    for (uint32_t i = 0; i < n; i++) {
        float fd = fdGrad[i], ad = adGrad[i];
        float denom = std::max(std::abs(fd) + std::abs(ad), 1e-12f);
        float relErr = std::abs(fd - ad) / denom * 2.0f * 100.0f;
        relErrors[i] = relErr;

        bool signOk = (fd > 0 && ad > 0) || (fd < 0 && ad < 0) ||
                      (std::abs(fd) < 1e-10 && std::abs(ad) < 1e-10);
        if (signOk) signMatch++;

        sumAbsFD += std::abs(fd);
        sumAbsAD += std::abs(ad);
        dotProd += fd * ad;
        normFDSq += fd * fd;
        normADSq += ad * ad;

        fmt::print("{:>4d} {:>12.4e} {:>12.4e} {:>12.4e} {:>7.1f}% {:>6s}\n",
                   i, fd, ad, std::abs(fd - ad), relErr, signOk ? "YES" : "NO");
    }

    float normFD = std::sqrt(normFDSq), normAD = std::sqrt(normADSq);
    float cosSim = (normFD * normAD > 0) ? dotProd / (normFD * normAD) : 0.0f;
    float magRatio = (sumAbsFD > 0) ? sumAbsAD / sumAbsFD : 0.0f;
    std::sort(relErrors.begin(), relErrors.end());

    fmt::print("\n{}", std::string(62, '-'));
    fmt::print("\n  [{}]\n", label);
    fmt::print("  Sign agreement:       {}/{} ({:.1f}%)\n",
               signMatch, n, 100.0f * signMatch / n);
    fmt::print("  Cosine similarity:    {:.6f}  (1.0 = perfect)\n", cosSim);
    fmt::print("  Magnitude ratio AD/FD: {:.4f}  (1.0 = perfect)\n", magRatio);
    fmt::print("  Relative error (median): {:.1f}%\n", relErrors[n / 2]);
    fmt::print("  Relative error (max):   {:.1f}%\n", relErrors.back());

    bool passSign = (signMatch >= n * 0.8f);
    bool passCos  = (cosSim > 0.9f);
    bool passMag  = (magRatio > 0.3f && magRatio < 3.0f);
    bool passMed  = (relErrors[n / 2] < 50.0f);

    fmt::print("  VERDICT: ");
    if (passSign && passCos && passMag && passMed)
        fmt::print("PASS\n");
    else {
        fmt::print("ISSUES\n");
        if (!passSign) fmt::print("    - Sign agreement < 80%\n");
        if (!passCos)  fmt::print("    - Cosine similarity < 0.9\n");
        if (!passMag)  fmt::print("    - Magnitude ratio out of [0.3, 3.0]\n");
        if (!passMed)  fmt::print("    - Median relative error > 50%\n");
    }
}

} // namespace bezier
