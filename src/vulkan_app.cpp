#include "vulkan_app.h"
#include <fmt/core.h>
#include <algorithm>
#include <cstdio>
#include <cstring>

namespace bezier {

void checkVk(VkResult result, const char *msg) {
    if (result != VK_SUCCESS) {
        throw std::runtime_error(fmt::format("Vulkan error: {} (code {})", msg, static_cast<int>(result)));
    }
}

VulkanApp::VulkanApp() {
    createInstance();
    pickPhysicalDevice();
    createDevice();
    createCommandPool();
    createDescriptorPool();
}

VulkanApp::~VulkanApp() {
    if (m_device) {
        vkQueueWaitIdle(m_computeQueue);
        vkDestroyDescriptorPool(m_device, m_descriptorPool, nullptr);
        vkDestroyCommandPool(m_device, m_cmdPool, nullptr);
        vkDestroyDevice(m_device, nullptr);
        vkDestroyInstance(m_instance, nullptr);
    }
}

void VulkanApp::createInstance() {
    VkApplicationInfo appInfo{};
    appInfo.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    appInfo.pApplicationName = "Bezier Heliostat Optimizer";
    appInfo.apiVersion = VK_API_VERSION_1_3;

    const std::vector<const char *> layers = {
#ifndef NDEBUG
        "VK_LAYER_KHRONOS_validation",
#endif
    };

    VkInstanceCreateInfo createInfo{};
    createInfo.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    createInfo.pApplicationInfo = &appInfo;
    createInfo.enabledLayerCount = static_cast<uint32_t>(layers.size());
    createInfo.ppEnabledLayerNames = layers.data();

    checkVk(vkCreateInstance(&createInfo, nullptr, &m_instance), "create instance");
}

void VulkanApp::pickPhysicalDevice() {
    uint32_t count = 0;
    vkEnumeratePhysicalDevices(m_instance, &count, nullptr);
    std::vector<VkPhysicalDevice> devices(count);
    vkEnumeratePhysicalDevices(m_instance, &count, devices.data());

    // Prefer discrete GPU, fall back to integrated, then fall back to any
    VkPhysicalDevice integrated = VK_NULL_HANDLE;
    for (auto dev : devices) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(dev, &props);
        if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) {
            m_physicalDevice = dev;
            fmt::print("Selected GPU: {} (discrete)\n", props.deviceName);
            return;
        }
        if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU && !integrated) {
            integrated = dev;
        }
    }
    if (integrated) {
        m_physicalDevice = integrated;
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(integrated, &props);
        fmt::print("Selected GPU: {} (integrated — no discrete GPU found)\n", props.deviceName);
        return;
    }
    if (count > 0) m_physicalDevice = devices[0];
    if (!m_physicalDevice) throw std::runtime_error("No Vulkan-capable GPU found");
}

void VulkanApp::createDevice() {
    uint32_t queueFamilyCount = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(m_physicalDevice, &queueFamilyCount, nullptr);
    std::vector<VkQueueFamilyProperties> queueFamilies(queueFamilyCount);
    vkGetPhysicalDeviceQueueFamilyProperties(m_physicalDevice, &queueFamilyCount, queueFamilies.data());

    for (uint32_t i = 0; i < queueFamilyCount; i++) {
        if (queueFamilies[i].queueFlags & VK_QUEUE_COMPUTE_BIT) {
            m_computeQueueFamily = i;
            break;
        }
    }

    float priority = 1.0f;
    VkDeviceQueueCreateInfo queueInfo{};
    queueInfo.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    queueInfo.queueFamilyIndex = m_computeQueueFamily;
    queueInfo.queueCount = 1;
    queueInfo.pQueuePriorities = &priority;

    VkDeviceCreateInfo deviceInfo{};
    deviceInfo.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    deviceInfo.queueCreateInfoCount = 1;
    deviceInfo.pQueueCreateInfos = &queueInfo;

    checkVk(vkCreateDevice(m_physicalDevice, &deviceInfo, nullptr, &m_device), "create device");
    vkGetDeviceQueue(m_device, m_computeQueueFamily, 0, &m_computeQueue);
}

void VulkanApp::createCommandPool() {
    VkCommandPoolCreateInfo poolInfo{};
    poolInfo.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    poolInfo.queueFamilyIndex = m_computeQueueFamily;
    checkVk(vkCreateCommandPool(m_device, &poolInfo, nullptr, &m_cmdPool), "create command pool");
}

void VulkanApp::createDescriptorPool() {
    // Allocate a generous pool
    std::vector<VkDescriptorPoolSize> poolSizes = {
        {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 64},
        {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 16},
        {VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 32},
    };

    VkDescriptorPoolCreateInfo poolInfo{};
    poolInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
    poolInfo.maxSets = 64;
    poolInfo.poolSizeCount = static_cast<uint32_t>(poolSizes.size());
    poolInfo.pPoolSizes = poolSizes.data();

    checkVk(vkCreateDescriptorPool(m_device, &poolInfo, nullptr, &m_descriptorPool), "create descriptor pool");
}

ComputePipeline VulkanApp::createComputePipeline(std::span<const uint32_t> spirvCode, const char *entryPoint,
                                                  uint32_t pushConstantSize,
                                                  std::span<const VkDescriptorSetLayoutBinding> bindings) {
    ComputePipeline result;
    // Descriptor set layout
    VkDescriptorSetLayoutCreateInfo setLayoutInfo{};
    setLayoutInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    setLayoutInfo.bindingCount = static_cast<uint32_t>(bindings.size());
    setLayoutInfo.pBindings = bindings.data();
    checkVk(vkCreateDescriptorSetLayout(m_device, &setLayoutInfo, nullptr, &result.setLayout), "create descriptor set layout");

    // Pipeline layout
    VkPipelineLayoutCreateInfo layoutInfo{};
    layoutInfo.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
    layoutInfo.setLayoutCount = 1;
    layoutInfo.pSetLayouts = &result.setLayout;
    VkPushConstantRange pushRange{};
    if (pushConstantSize > 0) {
        pushRange.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
        pushRange.size = pushConstantSize;
        layoutInfo.pushConstantRangeCount = 1;
        layoutInfo.pPushConstantRanges = &pushRange;
    }
    checkVk(vkCreatePipelineLayout(m_device, &layoutInfo, nullptr, &result.layout), "create pipeline layout");

    // Shader module
    VkShaderModuleCreateInfo shaderInfo{};
    shaderInfo.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
    shaderInfo.codeSize = spirvCode.size() * sizeof(uint32_t);
    shaderInfo.pCode = spirvCode.data();
    VkShaderModule shaderModule;
    checkVk(vkCreateShaderModule(m_device, &shaderInfo, nullptr, &shaderModule), "create shader module");

    // Compute pipeline
    VkComputePipelineCreateInfo pipelineInfo{};
    pipelineInfo.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
    pipelineInfo.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    pipelineInfo.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    pipelineInfo.stage.module = shaderModule;
    pipelineInfo.stage.pName = entryPoint;
    pipelineInfo.layout = result.layout;
    checkVk(vkCreateComputePipelines(m_device, VK_NULL_HANDLE, 1, &pipelineInfo, nullptr, &result.pipeline),
            "create compute pipeline");

    vkDestroyShaderModule(m_device, shaderModule, nullptr);

    // Allocate descriptor set
    VkDescriptorSetAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    allocInfo.descriptorPool = m_descriptorPool;
    allocInfo.descriptorSetCount = 1;
    allocInfo.pSetLayouts = &result.setLayout;
    result.descriptorSets.resize(1);
    checkVk(vkAllocateDescriptorSets(m_device, &allocInfo, result.descriptorSets.data()), "allocate descriptor sets");

    return result;
}

void VulkanApp::destroyPipeline(ComputePipeline &pipeline) {
    vkDestroyPipeline(m_device, pipeline.pipeline, nullptr);
    vkDestroyPipelineLayout(m_device, pipeline.layout, nullptr);
    vkDestroyDescriptorSetLayout(m_device, pipeline.setLayout, nullptr);
}

void VulkanApp::updateDescriptorSet(VkDescriptorSet set, std::span<const VkDescriptorBufferInfo> buffers,
                                     std::span<const VkDescriptorImageInfo> images) {
    std::vector<VkWriteDescriptorSet> writes;
    writes.reserve(buffers.size() + images.size());

    for (size_t i = 0; i < buffers.size(); i++) {
        if (buffers[i].buffer == VK_NULL_HANDLE) continue;
        VkWriteDescriptorSet w{};
        w.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        w.dstSet = set;
        w.dstBinding = static_cast<uint32_t>(i);
        w.descriptorCount = 1;
        w.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        w.pBufferInfo = &buffers[i];
        writes.push_back(w);
    }

    for (size_t i = 0; i < images.size(); i++) {
        if (images[i].imageView == VK_NULL_HANDLE) continue;
        VkWriteDescriptorSet w{};
        w.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        w.dstSet = set;
        w.dstBinding = static_cast<uint32_t>(buffers.size() + i);
        w.descriptorCount = 1;
        w.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE;
        w.pImageInfo = &images[i];
        writes.push_back(w);
    }

    vkUpdateDescriptorSets(m_device, static_cast<uint32_t>(writes.size()), writes.data(), 0, nullptr);
}

GpuBuffer VulkanApp::createBuffer(VkDeviceSize size, VkBufferUsageFlags usage, bool hostVisible) {
    GpuBuffer result;
    result.size = size;

    VkBufferCreateInfo bufferInfo{};
    bufferInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    bufferInfo.size = size;
    // Device-local buffers need TRANSFER_DST for uploadBuffer; host-visible need TRANSFER_SRC for downloadBuffer
    bufferInfo.usage = hostVisible
        ? (usage | VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT)
        : (usage | VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT);
    bufferInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    checkVk(vkCreateBuffer(m_device, &bufferInfo, nullptr, &result.buffer), "create buffer");

    VkMemoryRequirements memReqs;
    vkGetBufferMemoryRequirements(m_device, result.buffer, &memReqs);

    VkMemoryPropertyFlags props =
        hostVisible ? (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)
                    : VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT;

    VkMemoryAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocInfo.allocationSize = memReqs.size;
    allocInfo.memoryTypeIndex = findMemoryType(memReqs.memoryTypeBits, props);
    checkVk(vkAllocateMemory(m_device, &allocInfo, nullptr, &result.memory), "allocate buffer memory");
    vkBindBufferMemory(m_device, result.buffer, result.memory, 0);

    if (hostVisible) {
        vkMapMemory(m_device, result.memory, 0, size, 0, &result.mapped);
    }

    return result;
}

void VulkanApp::uploadBuffer(GpuBuffer &buffer, const void *data, VkDeviceSize size) {
    if (buffer.mapped) {
        std::memcpy(buffer.mapped, data, size);
    } else {
        // Staging buffer copy
        auto staging = createBuffer(size, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, true);
        std::memcpy(staging.mapped, data, size);
        // Copy staging -> device
        VkCommandBufferAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        allocInfo.commandPool = m_cmdPool;
        allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocInfo.commandBufferCount = 1;
        VkCommandBuffer cmd;
        vkAllocateCommandBuffers(m_device, &allocInfo, &cmd);

        VkCommandBufferBeginInfo beginInfo{};
        beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        vkBeginCommandBuffer(cmd, &beginInfo);

        VkBufferCopy copyRegion{};
        copyRegion.size = size;
        vkCmdCopyBuffer(cmd, staging.buffer, buffer.buffer, 1, &copyRegion);

        vkEndCommandBuffer(cmd);

        VkSubmitInfo submitInfo{};
        submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submitInfo.commandBufferCount = 1;
        submitInfo.pCommandBuffers = &cmd;
        vkQueueSubmit(m_computeQueue, 1, &submitInfo, VK_NULL_HANDLE);
        vkQueueWaitIdle(m_computeQueue);

        vkFreeCommandBuffers(m_device, m_cmdPool, 1, &cmd);
        destroyBuffer(staging);
    }
}

void VulkanApp::downloadBuffer(const GpuBuffer &buffer, void *data, VkDeviceSize size) {
    if (buffer.mapped) {
        std::memcpy(data, buffer.mapped, size);
    } else {
        auto staging = createBuffer(size, VK_BUFFER_USAGE_TRANSFER_DST_BIT, true);

        VkCommandBufferAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        allocInfo.commandPool = m_cmdPool;
        allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocInfo.commandBufferCount = 1;
        VkCommandBuffer cmd;
        vkAllocateCommandBuffers(m_device, &allocInfo, &cmd);

        VkCommandBufferBeginInfo beginInfo{};
        beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        vkBeginCommandBuffer(cmd, &beginInfo);

        VkBufferCopy copyRegion{};
        copyRegion.size = size;
        vkCmdCopyBuffer(cmd, buffer.buffer, staging.buffer, 1, &copyRegion);

        vkEndCommandBuffer(cmd);

        VkSubmitInfo submitInfo{};
        submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submitInfo.commandBufferCount = 1;
        submitInfo.pCommandBuffers = &cmd;
        vkQueueSubmit(m_computeQueue, 1, &submitInfo, VK_NULL_HANDLE);
        vkQueueWaitIdle(m_computeQueue);

        vkFreeCommandBuffers(m_device, m_cmdPool, 1, &cmd);

        std::memcpy(data, staging.mapped, size);
        destroyBuffer(staging);
    }
}

void VulkanApp::fillBuffer(GpuBuffer &buffer, uint32_t value) {
    if (buffer.mapped) {
        std::memset(buffer.mapped, value, buffer.size);
    } else {
        VkCommandBufferAllocateInfo allocInfo{};
        allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        allocInfo.commandPool = m_cmdPool;
        allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocInfo.commandBufferCount = 1;
        VkCommandBuffer cmd;
        vkAllocateCommandBuffers(m_device, &allocInfo, &cmd);

        VkCommandBufferBeginInfo beginInfo{};
        beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        vkBeginCommandBuffer(cmd, &beginInfo);
        vkCmdFillBuffer(cmd, buffer.buffer, 0, buffer.size, value);
        vkEndCommandBuffer(cmd);

        VkSubmitInfo submitInfo{};
        submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submitInfo.commandBufferCount = 1;
        submitInfo.pCommandBuffers = &cmd;
        vkQueueSubmit(m_computeQueue, 1, &submitInfo, VK_NULL_HANDLE);
        vkQueueWaitIdle(m_computeQueue);

        vkFreeCommandBuffers(m_device, m_cmdPool, 1, &cmd);
    }
}

void VulkanApp::destroyBuffer(GpuBuffer &buffer) {
    if (buffer.mapped) vkUnmapMemory(m_device, buffer.memory);
    if (buffer.buffer) vkDestroyBuffer(m_device, buffer.buffer, nullptr);
    if (buffer.memory) vkFreeMemory(m_device, buffer.memory, nullptr);
    buffer = {};
}

GpuTexture VulkanApp::createTexture(uint32_t width, uint32_t height, VkFormat format, VkImageUsageFlags usage) {
    GpuTexture result;
    result.width = width;
    result.height = height;
    result.format = format;

    VkImageCreateInfo imageInfo{};
    imageInfo.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    imageInfo.imageType = VK_IMAGE_TYPE_2D;
    imageInfo.format = format;
    imageInfo.extent = {width, height, 1};
    imageInfo.mipLevels = 1;
    imageInfo.arrayLayers = 1;
    imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
    imageInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
    imageInfo.usage = usage | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    checkVk(vkCreateImage(m_device, &imageInfo, nullptr, &result.image), "create image");

    VkMemoryRequirements memReqs;
    vkGetImageMemoryRequirements(m_device, result.image, &memReqs);
    VkMemoryAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocInfo.allocationSize = memReqs.size;
    allocInfo.memoryTypeIndex = findMemoryType(memReqs.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    checkVk(vkAllocateMemory(m_device, &allocInfo, nullptr, &result.memory), "allocate image memory");
    vkBindImageMemory(m_device, result.image, result.memory, 0);

    VkImageViewCreateInfo viewInfo{};
    viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
    viewInfo.image = result.image;
    viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
    viewInfo.format = format;
    viewInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    viewInfo.subresourceRange.levelCount = 1;
    viewInfo.subresourceRange.layerCount = 1;
    checkVk(vkCreateImageView(m_device, &viewInfo, nullptr, &result.view), "create image view");

    // Transition to GENERAL layout for compute
    VkCommandBufferAllocateInfo allocInfo2{};
    allocInfo2.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    allocInfo2.commandPool = m_cmdPool;
    allocInfo2.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    allocInfo2.commandBufferCount = 1;
    VkCommandBuffer cmd;
    vkAllocateCommandBuffers(m_device, &allocInfo2, &cmd);

    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vkBeginCommandBuffer(cmd, &beginInfo);

    VkImageMemoryBarrier barrier{};
    barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    barrier.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    barrier.newLayout = VK_IMAGE_LAYOUT_GENERAL;
    barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    barrier.image = result.image;
    barrier.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    barrier.subresourceRange.levelCount = 1;
    barrier.subresourceRange.layerCount = 1;
    barrier.srcAccessMask = 0;
    barrier.dstAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 0, nullptr, 0,
                         nullptr, 1, &barrier);

    vkEndCommandBuffer(cmd);
    VkSubmitInfo submitInfo{};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &cmd;
    vkQueueSubmit(m_computeQueue, 1, &submitInfo, VK_NULL_HANDLE);
    vkQueueWaitIdle(m_computeQueue);
    vkFreeCommandBuffers(m_device, m_cmdPool, 1, &cmd);

    return result;
}

void VulkanApp::uploadTexture(GpuTexture &tex, const void *data) {
    VkDeviceSize imageSize = tex.width * tex.height * sizeof(float);
    auto staging = createBuffer(imageSize, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, true);
    std::memcpy(staging.mapped, data, imageSize);

    VkCommandBufferAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    allocInfo.commandPool = m_cmdPool;
    allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    allocInfo.commandBufferCount = 1;
    VkCommandBuffer cmd;
    vkAllocateCommandBuffers(m_device, &allocInfo, &cmd);

    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vkBeginCommandBuffer(cmd, &beginInfo);

    VkBufferImageCopy region{};
    region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.imageSubresource.layerCount = 1;
    region.imageExtent = {tex.width, tex.height, 1};
    vkCmdCopyBufferToImage(cmd, staging.buffer, tex.image, VK_IMAGE_LAYOUT_GENERAL, 1, &region);

    vkEndCommandBuffer(cmd);

    VkSubmitInfo submitInfo{};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &cmd;
    vkQueueSubmit(m_computeQueue, 1, &submitInfo, VK_NULL_HANDLE);
    vkQueueWaitIdle(m_computeQueue);

    vkFreeCommandBuffers(m_device, m_cmdPool, 1, &cmd);
    destroyBuffer(staging);
}

void VulkanApp::downloadTexture(const GpuTexture &tex, std::vector<float> &data) {
    VkDeviceSize imageSize = tex.width * tex.height * sizeof(float);
    auto staging = createBuffer(imageSize, VK_BUFFER_USAGE_TRANSFER_DST_BIT, true);

    VkCommandBufferAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    allocInfo.commandPool = m_cmdPool;
    allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    allocInfo.commandBufferCount = 1;
    VkCommandBuffer cmd;
    vkAllocateCommandBuffers(m_device, &allocInfo, &cmd);

    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vkBeginCommandBuffer(cmd, &beginInfo);

    VkBufferImageCopy region{};
    region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.imageSubresource.layerCount = 1;
    region.imageExtent = {tex.width, tex.height, 1};
    vkCmdCopyImageToBuffer(cmd, tex.image, VK_IMAGE_LAYOUT_GENERAL, staging.buffer, 1, &region);

    vkEndCommandBuffer(cmd);

    VkSubmitInfo submitInfo{};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &cmd;
    vkQueueSubmit(m_computeQueue, 1, &submitInfo, VK_NULL_HANDLE);
    vkQueueWaitIdle(m_computeQueue);

    vkFreeCommandBuffers(m_device, m_cmdPool, 1, &cmd);

    data.resize(tex.width * tex.height);
    std::memcpy(data.data(), staging.mapped, imageSize);
    destroyBuffer(staging);
}

void VulkanApp::clearTexture(GpuTexture &tex) {
    std::vector<float> zeros(tex.width * tex.height, 0.0f);
    uploadTexture(tex, zeros.data());
}

void VulkanApp::destroyTexture(GpuTexture &tex) {
    if (tex.view) vkDestroyImageView(m_device, tex.view, nullptr);
    if (tex.image) vkDestroyImage(m_device, tex.image, nullptr);
    if (tex.memory) vkFreeMemory(m_device, tex.memory, nullptr);
    tex = {};
}

ComputePass VulkanApp::beginComputePass() {
    ComputePass pass;

    VkFenceCreateInfo fenceInfo{};
    fenceInfo.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    vkCreateFence(m_device, &fenceInfo, nullptr, &pass.fence);

    VkCommandBufferAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    allocInfo.commandPool = m_cmdPool;
    allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    allocInfo.commandBufferCount = 1;
    vkAllocateCommandBuffers(m_device, &allocInfo, &pass.cmd);

    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vkBeginCommandBuffer(pass.cmd, &beginInfo);

    return pass;
}

void VulkanApp::endComputePass(ComputePass &pass) {
    vkEndCommandBuffer(pass.cmd);

    VkSubmitInfo submitInfo{};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &pass.cmd;
    vkQueueSubmit(m_computeQueue, 1, &submitInfo, pass.fence);
    vkWaitForFences(m_device, 1, &pass.fence, VK_TRUE, UINT64_MAX);

    vkDestroyFence(m_device, pass.fence, nullptr);
    vkFreeCommandBuffers(m_device, m_cmdPool, 1, &pass.cmd);
}

// Phase 2: Batched compute pass — returns raw cmd+buf+fence, caller emits multiple dispatches
RawComputePass VulkanApp::beginComputePassRaw() {
    RawComputePass pass;

    VkFenceCreateInfo fenceInfo{};
    fenceInfo.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    vkCreateFence(m_device, &fenceInfo, nullptr, &pass.fence);

    VkCommandBufferAllocateInfo allocInfo{};
    allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    allocInfo.commandPool = m_cmdPool;
    allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    allocInfo.commandBufferCount = 1;
    vkAllocateCommandBuffers(m_device, &allocInfo, &pass.cmd);

    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vkBeginCommandBuffer(pass.cmd, &beginInfo);

    return pass;
}

void VulkanApp::submitAndWait(RawComputePass &pass) {
    vkEndCommandBuffer(pass.cmd);

    VkSubmitInfo submitInfo{};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.commandBufferCount = 1;
    submitInfo.pCommandBuffers = &pass.cmd;
    vkQueueSubmit(m_computeQueue, 1, &submitInfo, pass.fence);
    vkWaitForFences(m_device, 1, &pass.fence, VK_TRUE, UINT64_MAX);

    vkDestroyFence(m_device, pass.fence, nullptr);
    vkFreeCommandBuffers(m_device, m_cmdPool, 1, &pass.cmd);
}

// Phase 2: Fill buffer from within an existing command buffer (avoids CPU upload sync)
void VulkanApp::fillBufferCmd(VkCommandBuffer cmd, const GpuBuffer &buffer, uint32_t value) {
    vkCmdFillBuffer(cmd, buffer.buffer, 0, buffer.size, value);
    VkMemoryBarrier barrier{};
    barrier.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER;
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT;
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                         0, 1, &barrier, 0, nullptr, 0, nullptr);
}

// A2: Update buffer from within an existing command buffer (data consumed at
// record time; offset/size must be multiples of 4, size <= 65536).
void VulkanApp::updateBufferCmd(VkCommandBuffer cmd, const GpuBuffer &buffer, VkDeviceSize offset,
                                VkDeviceSize size, const void *data) {
    vkCmdUpdateBuffer(cmd, buffer.buffer, offset, size, data);
    VkMemoryBarrier barrier{};
    barrier.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER;
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_UNIFORM_READ_BIT;
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                         0, 1, &barrier, 0, nullptr, 0, nullptr);
}

void VulkanApp::waitIdle() { vkQueueWaitIdle(m_computeQueue); }

void VulkanApp::bindPipeline(VkCommandBuffer cmd, const ComputePipeline &pipeline) {
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline.pipeline);
    vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline.layout, 0, 1,
                            pipeline.descriptorSets.data(), 0, nullptr);
}

void VulkanApp::pushConstants(VkCommandBuffer cmd, VkPipelineLayout layout, const void *data, uint32_t size) {
    vkCmdPushConstants(cmd, layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, size, data);
}

void VulkanApp::dispatch(VkCommandBuffer cmd, uint32_t gx, uint32_t gy, uint32_t gz) {
    vkCmdDispatch(cmd, gx, gy, gz);
}

void VulkanApp::pipelineBarrier(VkCommandBuffer cmd) {
    VkMemoryBarrier barrier{};
    barrier.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER;
    barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1,
                         &barrier, 0, nullptr, 0, nullptr);
}

uint32_t VulkanApp::findMemoryType(uint32_t typeFilter, VkMemoryPropertyFlags props) const {
    VkPhysicalDeviceMemoryProperties memProps;
    vkGetPhysicalDeviceMemoryProperties(m_physicalDevice, &memProps);
    for (uint32_t i = 0; i < memProps.memoryTypeCount; i++) {
        if ((typeFilter & (1 << i)) && (memProps.memoryTypes[i].propertyFlags & props) == props) {
            return i;
        }
    }
    throw std::runtime_error("Failed to find suitable memory type");
}

} // namespace bezier
