#pragma once

#include <vulkan/vulkan.h>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace bezier {

// Minimal Vulkan compute abstraction.
// Manages: instance, device, compute queue, command pool, descriptor pool,
// pipelines, buffers, and textures.

struct ComputePipeline {
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkDescriptorSetLayout setLayout = VK_NULL_HANDLE;
    std::vector<VkDescriptorSet> descriptorSets; // one per frame-in-flight (we use 1)
};

struct GpuBuffer {
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkDeviceSize size = 0;
    void *mapped = nullptr; // if host-visible
};

struct GpuTexture {
    VkImage image = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkFormat format = VK_FORMAT_R32_SFLOAT;
    uint32_t width = 0;
    uint32_t height = 0;
};

struct ComputePass {
    VkCommandBuffer cmd = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
};

class VulkanApp {
public:
    VulkanApp();
    ~VulkanApp();

    VulkanApp(const VulkanApp &) = delete;
    VulkanApp &operator=(const VulkanApp &) = delete;

    // Device access
    VkDevice device() const { return m_device; }
    VkPhysicalDevice physicalDevice() const { return m_physicalDevice; }
    VkQueue computeQueue() const { return m_computeQueue; }
    uint32_t computeQueueFamily() const { return m_computeQueueFamily; }
    VkDescriptorPool descriptorPool() const { return m_descriptorPool; }

    // Pipeline creation
    ComputePipeline createComputePipeline(std::span<const uint32_t> spirvCode, const char *entryPoint,
                                          uint32_t pushConstantSize,
                                          std::span<const VkDescriptorSetLayoutBinding> bindings);

    void destroyPipeline(ComputePipeline &pipeline);

    // Update descriptor set with buffer/texture bindings
    void updateDescriptorSet(VkDescriptorSet set, std::span<const VkDescriptorBufferInfo> buffers,
                             std::span<const VkDescriptorImageInfo> images);

    // Buffer management
    GpuBuffer createBuffer(VkDeviceSize size, VkBufferUsageFlags usage, bool hostVisible);
    void uploadBuffer(GpuBuffer &buffer, const void *data, VkDeviceSize size);
    void downloadBuffer(const GpuBuffer &buffer, void *data, VkDeviceSize size);
    void fillBuffer(GpuBuffer &buffer, uint32_t value);
    void destroyBuffer(GpuBuffer &buffer);

    // Texture management
    GpuTexture createTexture(uint32_t width, uint32_t height, VkFormat format, VkImageUsageFlags usage);
    void uploadTexture(GpuTexture &tex, const void *data);
    void downloadTexture(const GpuTexture &tex, std::vector<float> &data);
    void clearTexture(GpuTexture &tex);
    void destroyTexture(GpuTexture &tex);

    // Command execution
    ComputePass beginComputePass();
    void endComputePass(ComputePass &pass);
    void waitIdle();

    // Dispatch helpers
    void bindPipeline(VkCommandBuffer cmd, const ComputePipeline &pipeline);
    void pushConstants(VkCommandBuffer cmd, VkPipelineLayout layout, const void *data, uint32_t size);
    void dispatch(VkCommandBuffer cmd, uint32_t gx, uint32_t gy, uint32_t gz);

    // Memory barrier
    void pipelineBarrier(VkCommandBuffer cmd);

private:
    void createInstance();
    void pickPhysicalDevice();
    void createDevice();
    void createCommandPool();
    void createDescriptorPool();

    uint32_t findMemoryType(uint32_t typeFilter, VkMemoryPropertyFlags props) const;

    VkInstance m_instance = VK_NULL_HANDLE;
    VkPhysicalDevice m_physicalDevice = VK_NULL_HANDLE;
    VkDevice m_device = VK_NULL_HANDLE;
    VkQueue m_computeQueue = VK_NULL_HANDLE;
    VkCommandPool m_cmdPool = VK_NULL_HANDLE;
    VkDescriptorPool m_descriptorPool = VK_NULL_HANDLE;
    uint32_t m_computeQueueFamily = 0;
};

// Throw on Vulkan error
void checkVk(VkResult result, const char *msg);

} // namespace bezier
