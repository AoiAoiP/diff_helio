# Define the main optimization executable
add_executable(bezier_opt
    main.cpp
    vulkan_app.cpp
    config.cpp
    input.cpp
    pipeline.cpp
)

target_include_directories(bezier_opt PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${Vulkan_INCLUDE_DIRS}
    ${Slang_INCLUDE_DIRS}
)

target_link_libraries(bezier_opt PRIVATE
    Vulkan::Vulkan
    Slang::Slang
    fmt::fmt
    glm::glm
)

# Copy shaders, configs, and data to runtime directory
add_custom_command(TARGET bezier_opt POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory
        $<TARGET_FILE_DIR:bezier_opt>/shaders
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        "${SHADER_OUTPUT_DIR}"
        $<TARGET_FILE_DIR:bezier_opt>/shaders
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${CMAKE_SOURCE_DIR}/configs
        $<TARGET_FILE_DIR:bezier_opt>/configs
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${CMAKE_SOURCE_DIR}/data
        $<TARGET_FILE_DIR:bezier_opt>/data
    # Phase 5: copy SPIR-V to source shaders/ so loadSpv("shaders/...") finds them
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${SHADER_OUTPUT_DIR}/renderBackwardBolt.spv" "${SHADER_DIR}/renderBackwardBolt.spv"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${SHADER_OUTPUT_DIR}/reduceSurfaceGradients.spv" "${SHADER_DIR}/reduceSurfaceGradients.spv"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${SHADER_OUTPUT_DIR}/projectBoltGradients.spv" "${SHADER_DIR}/projectBoltGradients.spv"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${SHADER_OUTPUT_DIR}/clearSurfaceGradient.spv" "${SHADER_DIR}/clearSurfaceGradient.spv"
    COMMENT "Copying shaders and data to runtime directory"
)

# On Windows, copy Slang DLLs
if(WIN32)
    add_custom_command(TARGET bezier_opt POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${Slang_RUNTIME_DIR}/slang.dll"
            $<TARGET_FILE_DIR:bezier_opt>
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${Slang_RUNTIME_DIR}/slang-compiler.dll"
            $<TARGET_FILE_DIR:bezier_opt>
        COMMENT "Copying Slang runtime DLLs"
    )
endif()

add_dependencies(bezier_opt shaders)
