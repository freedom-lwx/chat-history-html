cmake_minimum_required(VERSION 3.20)
project(NpuLabConsumer LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# This is a genuinely separate consumer: it needs the installed package,
# not the operator's src/ directory or the ASC compiler.
find_package(NpuLab 1 CONFIG REQUIRED)
find_path(ACL_INCLUDE_DIR acl/acl.h
    HINTS "$ENV{ASCEND_HOME_PATH}/include" REQUIRED)
find_library(ACL_LIBRARY ascendcl
    HINTS "$ENV{ASCEND_HOME_PATH}/lib64" REQUIRED)
add_executable(npu_lab_client main.cpp)
target_include_directories(npu_lab_client PRIVATE ${ACL_INCLUDE_DIR})
target_link_libraries(npu_lab_client PRIVATE NpuLab::npu_lab ${ACL_LIBRARY})
