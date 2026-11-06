# 来源与实现说明

此工程为本次讨论新编写的教学实现。它使用 Ascend C API，未打包 SDK、编译器或厂商二进制。
使用 SDK 需遵守相应 SDK 许可。本包不宣称经过厂商认证或设备验证。

实际查阅的源码基线：ASC-DevKit 的 GitHub 镜像 `mirror-cann/asc-devkit`，
固定树/提交引用 `82b89a15f26329511fc7fbc807d5132a1f9b4ba7`。
这是 GitHub 镜像入口，不能混称为本次从 GitCode 官网直接下载的发行版。

- 动态库与 CANN 基线支持表：
  https://github.com/mirror-cann/asc-devkit/blob/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/examples/01_simd_cpp_api/02_features/04_compile/02_dynamic_library_compile/README.md
- ASC 动态库 CMake：
  https://github.com/mirror-cann/asc-devkit/blob/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/examples/01_simd_cpp_api/02_features/04_compile/02_dynamic_library_compile/CMakeLists.txt
- TPipe/TQue Add API 用法：
  https://github.com/mirror-cann/asc-devkit/blob/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/examples/01_simd_cpp_api/00_introduction/01_add/add_tpipe_tque/add_tpipe_tque.asc
- ReduceSum 接口声明：
  https://github.com/mirror-cann/asc-devkit/blob/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/include/basic_api/kernel_operator_vec_reduce_intf.h
- DataCopyPad 接口声明：
  https://github.com/mirror-cann/asc-devkit/blob/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/include/basic_api/kernel_operator_data_copy_intf.h
- Cube 数据路径、Mmad 与 Fixpipe 参考：
  https://github.com/mirror-cann/asc-devkit/blob/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/mmad/mmad.asc

工程自行实现的部分：公开 C ABI、参数与别名检查、分块策略、动态长度尾块、
融合案例、两阶段 ReduceSum、按16分块的矩阵遍历、打包导出、C++/Python消费端和测试。
接口存在及参考样例可阅读，不等于本工程的具体组合已经通过目标版本编译与执行。
