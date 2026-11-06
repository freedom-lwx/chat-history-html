cmake_minimum_required(VERSION 3.20)

# New ASC-language build path (CANN 9.x); do not silently fall back to old tik2.
set(CMAKE_ASC_ARCHITECTURES "dav-2201" CACHE STRING "Teaching target architecture")
if(NOT CMAKE_ASC_ARCHITECTURES STREQUAL "dav-2201")
    message(FATAL_ERROR "This source implements the dav-2201 Cube layout only")
endif()
if(NOT DEFINED ENV{ASCEND_HOME_PATH})
    message(FATAL_ERROR "Source your CANN set_env.sh before configuring")
endif()
find_package(ASC REQUIRED)
project(NpuLab VERSION 1.0.0 LANGUAGES ASC CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_path(ACL_INCLUDE_DIR acl/acl.h
    HINTS "$ENV{ASCEND_HOME_PATH}/include" REQUIRED)
find_library(ACL_LIBRARY ascendcl
    HINTS "$ENV{ASCEND_HOME_PATH}/lib64" REQUIRED)

add_library(npu_lab SHARED
    src/host/npu_ops.cpp
    src/kernel/add.asc
    src/kernel/add_relu.asc
    src/kernel/reduce_sum.asc
    src/kernel/matmul.asc)
add_library(NpuLab::npu_lab ALIAS npu_lab)
set_target_properties(npu_lab PROPERTIES
    LINKER_LANGUAGE ASC
    VERSION ${PROJECT_VERSION}
    SOVERSION 1
    POSITION_INDEPENDENT_CODE ON)
target_compile_options(npu_lab PRIVATE
    $<$<COMPILE_LANGUAGE:ASC>:--npu-arch=${CMAKE_ASC_ARCHITECTURES}>
    $<$<COMPILE_LANGUAGE:ASC>:-fPIC>
    $<$<COMPILE_LANGUAGE:ASC>:-std=c++17>)
target_include_directories(npu_lab
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE ${ACL_INCLUDE_DIR})
target_link_libraries(npu_lab PRIVATE ${ACL_LIBRARY})

# Ordinary CPU unit test; this target does not execute NPU code.
add_executable(npu_lab_tiling_test tests/tiling_test.cpp)
target_include_directories(npu_lab_tiling_test PRIVATE src/host)
enable_testing()
add_test(NAME host_tiling COMMAND npu_lab_tiling_test)

include(CMakePackageConfigHelpers)
configure_package_config_file(cmake/NpuLabConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/NpuLabConfig.cmake"
    INSTALL_DESTINATION lib/cmake/NpuLab)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/NpuLabConfigVersion.cmake"
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(TARGETS npu_lab EXPORT NpuLabTargets
    LIBRARY DESTINATION lib ARCHIVE DESTINATION lib RUNTIME DESTINATION bin)
install(FILES include/npu_lab.h DESTINATION include)
install(EXPORT NpuLabTargets NAMESPACE NpuLab:: DESTINATION lib/cmake/NpuLab)
install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/NpuLabConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/NpuLabConfigVersion.cmake"
    DESTINATION lib/cmake/NpuLab)
