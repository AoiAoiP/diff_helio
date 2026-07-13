cmake_minimum_required(VERSION 3.25)
project(bezier_opt
    VERSION 1.0.0
    DESCRIPTION "Bezier heliostat surface optimization with Vulkan/Slang autodiff"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# MSVC settings
if(MSVC)
    add_compile_options(/utf-8 /W3)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS WIN32_LEAN_AND_MEAN NOMINMAX)
endif()

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

# ---- Vulkan SDK ----
find_package(Vulkan REQUIRED)
message(STATUS "Vulkan found: ${Vulkan_INCLUDE_DIRS}")

# ---- Slang (bundled with Vulkan SDK) ----
find_package(Slang REQUIRED)
message(STATUS "Slang found: ${SLANGC_EXECUTABLE}")

# ---- Dependencies via FetchContent ----
include(FetchContent)

FetchContent_Declare(fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG 11.1.4
    OVERRIDE_FIND_PACKAGE
)
FetchContent_MakeAvailable(fmt)

FetchContent_Declare(glm
    GIT_REPOSITORY https://github.com/g-truc/glm.git
    GIT_TAG 1.0.1
    OVERRIDE_FIND_PACKAGE
)
FetchContent_MakeAvailable(glm)


# ---- Shader compilation ----
set(SHADER_DIR "${CMAKE_CURRENT_SOURCE_DIR}/shaders")
set(SHADER_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/shaders")

# List of all shader source files (including __include headers for dep tracking)
set(SHADER_SOURCES
    ${SHADER_DIR}/common.slang
    ${SHADER_DIR}/sunshape.slang
    ${SHADER_DIR}/forward.slang
    ${SHADER_DIR}/backward.slang
    ${SHADER_DIR}/loss.slang
    ${SHADER_DIR}/loss_gpu.slang
    ${SHADER_DIR}/optimizer.slang
    ${SHADER_DIR}/bolt_common.slang
    ${SHADER_DIR}/bolt_forward.slang
    ${SHADER_DIR}/bolt_backward.slang
    ${SHADER_DIR}/bolt_optimizer.slang
    ${SHADER_DIR}/wos_common.slang
    ${SHADER_DIR}/wos_influence.slang
)

# Entry points: name -> source file
set(SHADER_ENTRIES
    "computeBezierSurface:forward.slang"
    "clearFlux:forward.slang"
    "renderForward:forward.slang"
    "finalizeFlux:forward.slang"
    "renderBackward:backward.slang"
    "reduceBackwardGradients:backward.slang"
    "computeS95Loss:loss.slang"
    "countS95Simple:loss.slang"
    "clearFluxGradient:loss.slang"
    "reduceLossPartial:loss_gpu.slang"
    "reduceLossFinal:loss_gpu.slang"
    "adamUpdate:optimizer.slang"
    "computeBoltSurface:bolt_forward.slang"
    "renderBackwardBolt:bolt_backward.slang"
    "reduceSurfaceGradients:bolt_backward.slang"
    "projectBoltGradients:bolt_backward.slang"
    "clearSurfaceGradient:bolt_backward.slang"
    "adamUpdateBolt:bolt_optimizer.slang"
    "computeWoSInfluence:wos_influence.slang"
)

# Compile each entry point to SPIR-V
foreach(entry_def ${SHADER_ENTRIES})
    string(REPLACE ":" ";" entry_parts "${entry_def}")
    list(GET entry_parts 0 ENTRY_NAME)
    list(GET entry_parts 1 SOURCE_FILE)

    set(SPV_OUTPUT "${SHADER_OUTPUT_DIR}/${ENTRY_NAME}.spv")
    add_custom_command(
        OUTPUT ${SPV_OUTPUT}
        COMMAND ${CMAKE_COMMAND} -E make_directory "${SHADER_OUTPUT_DIR}"
        COMMAND ${SLANGC_EXECUTABLE}
            -std 2026
            -target spirv
            -O2
            -entry ${ENTRY_NAME}
            -o ${SPV_OUTPUT}
            "${SHADER_DIR}/${SOURCE_FILE}"
        DEPENDS ${SHADER_SOURCES} ${SLANGC_EXECUTABLE}
        COMMENT "Compiling Slang shader: ${ENTRY_NAME}"
        VERBATIM
    )
    list(APPEND ALL_SPV_FILES ${SPV_OUTPUT})
endforeach()

add_custom_target(shaders ALL DEPENDS ${ALL_SPV_FILES})

# ---- Main target ----
add_subdirectory(src)
