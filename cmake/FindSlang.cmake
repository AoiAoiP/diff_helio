# FindSlang.cmake — find the Slang shader compiler bundled with Vulkan SDK
#
# Output variables:
#   Slang_FOUND          — TRUE if found
#   SLANGC_EXECUTABLE    — path to slangc.exe
#   Slang_INCLUDE_DIRS   — include directories
#   Slang_LIBRARY        — slang.lib path
#   Slang_RUNTIME_DIR    — directory containing slang.dll (for post-build copy)
#   Slang::Slang         — imported library target

if(NOT VULKAN_SDK)
    # Try to locate Vulkan SDK via environment or registry
    set(VULKAN_SDK "$ENV{VULKAN_SDK}")
endif()

if(NOT VULKAN_SDK)
    # Fallback: search common install locations
    file(GLOB VK_SDK_CANDIDATES "C:/VulkanSDK/*")
    foreach(CANDIDATE ${VK_SDK_CANDIDATES})
        if(IS_DIRECTORY "${CANDIDATE}")
            list(APPEND VK_SDK_CANDIDATES "${CANDIDATE}")
        endif()
    endforeach()
    if(VK_SDK_CANDIDATES)
        list(GET VK_SDK_CANDIDATES 0 VULKAN_SDK)
    endif()
endif()

find_program(SLANGC_EXECUTABLE
    NAMES slangc slangc.exe
    HINTS "${VULKAN_SDK}/Bin"
    DOC "Slang shader compiler"
)

find_path(Slang_INCLUDE_DIRS
    NAMES slang/slang.h
    HINTS "${VULKAN_SDK}/Include"
    DOC "Slang include directory"
)

find_library(Slang_LIBRARY
    NAMES slang
    HINTS "${VULKAN_SDK}/Lib"
    DOC "Slang link library"
)

find_path(Slang_RUNTIME_DIR
    NAMES slang.dll
    HINTS "${VULKAN_SDK}/Bin"
    DOC "Slang runtime DLL directory"
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Slang
    REQUIRED_VARS SLANGC_EXECUTABLE Slang_INCLUDE_DIRS Slang_LIBRARY Slang_RUNTIME_DIR
)

if(Slang_FOUND AND NOT TARGET Slang::Slang)
    add_library(Slang::Slang UNKNOWN IMPORTED)
    set_target_properties(Slang::Slang PROPERTIES
        IMPORTED_LOCATION "${Slang_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${Slang_INCLUDE_DIRS}"
    )
endif()

mark_as_advanced(SLANGC_EXECUTABLE Slang_INCLUDE_DIRS Slang_LIBRARY Slang_RUNTIME_DIR)
