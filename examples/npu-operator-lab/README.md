# NPU Operator Lab — 完整源码教学工程

四个案例：Add、Add+ReLU、两阶段 ReduceSum、Cube MatMul。
它们共享一套可安装的 C ABI 动态库，提供独立 C++ 和 Python ctypes 消费端。

## 0. 验证边界与选定基线

- 教学目标：Linux，Atlas A2/A3 对应 `dav-2201`，CANN >= 9.0.0 的新 ASC 构建模式。
- 构建依赖：匹配设备的驱动/固件、CANN 开发包、C++17 编译环境、CMake >= 3.20；`find_package(ASC REQUIRED)` 必须可用。
- 选这个基线来自已查阅的 ASC-DevKit 动态库示例支持表，不是用户确认的实际设备。
- **本机没有 CANN 编译器或 NPU。源码已提供，不代表已成功编译或上机通过。**
- CPU 检查只覆盖包结构、切分与索引数学、Python 语法；不覆盖 ASC 编译、物理布局、同步和设备数值。
- 不承诺旧版 CANN 8.x、950 架构、任意布局或任意矩阵形状的兼容性。

## 1. 目录与每一块的作用

```text
npu-operator-lab/
  CMakeLists.txt                  编译共享库并生成可安装 CMake package
  cmake/NpuLabConfig.cmake.in      让外部工程 find_package(NpuLab)
  include/npu_lab.h               对外稳定 C ABI、类型与所有权契约
  src/host/tiling.h               长度/形状约束，任务数与块大小
  src/host/npu_ops.cpp            参数检查、Tiling、启动、同步、工作区生命周期
  src/kernel/launchers.h          Host C++ 与 ASC 启动封装之间的内部接口
  src/kernel/elementwise_impl.h   Add/融合共用的 CopyIn → Compute → CopyOut
  src/kernel/add.asc             Add 设备入口与 <<<>>> Host 启动函数
  src/kernel/add_relu.asc         融合入口；中间和不离开 UB
  src/kernel/reduce_sum.asc       局部和及最终合并两个 Kernel
  src/kernel/matmul.asc           GM/L1/L0 布局、Mmad、K 累加与 Fixpipe
  examples/cpp_client/            不依赖源码目录的独立 C++ 应用
  examples/python_client.py       ctypes 调用全部四个公开 API
  tests/tiling_test.cpp           实际 Host Tiling 代码的普通 C++ 测试
  tests/check_package.py          无 SDK 可执行的 Python 模型与结构检查
  NOTICE.md                      来源、改写范围和版本说明
```

调用链：

```text
外部 C++ / Python 应用
    -> include/npu_lab.h 的 nl_* 接口
    -> libnpu_lab.so 中的参数检查与 Host Tiling
    -> .asc 文件中的 Host <<<>>> 启动函数
    -> NPU 上的 __vector__ / __cube__ Kernel
    -> stream 同步完成
    -> 返回状态，应用读取/继续使用设备输出
```

`npu_ops.cpp` 是本工程自己的 Host 包装，不是 OPP 的 OpDef 注册回调。
本路线不生成 `aclnnXxx`，也不会仅靠安装 `.so` 自动出现在 PyTorch 算子列表中。

## 2. 算子契约

| 算子 | 输入与输出 | 范围 | 实现 |
|---|---|---|---|
| Add | FP32 + FP32 -> FP32 | 连续等长；无广播；0 <= N <= 2^24 | Vector，256 元素/块，DataCopyPad 尾块 |
| Add+ReLU | FP32 + FP32 -> FP32 | 同 Add；有限数值测试 | Add 后在 UB 中 Maxs(0) |
| ReduceSum | FP32[N] -> FP32[1] | 1 <= N <= 2^24 | 每任务一个带零填充的32字节局部和槽，再启动合并 Kernel |
| MatMul | FP16[M,K] @ FP16[K,N] -> FP32[M,N] | M,N,K 是16的正倍数且各 <=256 | 每输出块16x16，显式布局、Cube Mmad、K循环 |

全部 API 接收当前 context 的设备指针及非空 stream；输入/输出不得重叠。
输入 A 与 B 可以复用相同地址，但输出不得覆盖它们。
设备内存是否足够、指针是否来自正确设备及 context，由调用者保证。
MatMul 的 `uint16_t*` 是 IEEE FP16 位模式，不是整数矩阵，也不是 float32 地址。

## 3. 构建与安装（在目标 Linux NPU 机器执行）

先按实际安装路径加载环境，例如：

```bash
source /usr/local/Ascend/cann/set_env.sh
# 安装位置不同则使用实际路径；不要混用其他版本的头文件/运行库。
printf '%s\n' "$ASCEND_HOME_PATH"
command -v bisheng
cmake --version
npu-smi info

cmake -S . -B build \
  -DCMAKE_ASC_ARCHITECTURES=dav-2201 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/install"
cmake --build build --parallel
ctest --test-dir build --output-on-failure
cmake --install build
```

这些是待执行步骤，不是本地已经通过的日志。无需 root 或写入系统目录。
产物应包括：

```text
install/include/npu_lab.h
install/lib/libnpu_lab.so         指向对应 SONAME 的共享库链接
install/lib/libnpu_lab.so.1*
install/lib/cmake/NpuLab/NpuLabConfig.cmake
install/lib/cmake/NpuLab/NpuLabTargets.cmake
```

## 4. 其他 C++ 工程怎样应用

`examples/cpp_client` 有自己的 CMakeLists，不引用算子的 `src/`：

```bash
cmake -S examples/cpp_client -B client-build \
  -DCMAKE_PREFIX_PATH="$PWD/install"
cmake --build client-build --parallel
export LD_LIBRARY_PATH="$PWD/install/lib:${LD_LIBRARY_PATH:-}"
./client-build/npu_lab_client 0
```

消费端只需要：安装后的头文件与共享库、CMake package、兼容的 ACL 运行环境，以及驱动设备。
生产端编译 `.asc` 需要 ASC 编译器；链接预编译库的 C++ 消费端无需再次编译 Kernel。
外部工程自行 `aclInit -> SetDevice -> CreateStream -> Malloc/上传`，调用 `nl_*`，再读取结果及释放资源。
不要把测试程序的 `aclFinalize/ResetDevice` 原样塞进已有服务的一次请求中；它们属于进程/设备生命周期。

## 5. Python 应用方式

```bash
export NL_LIB="$PWD/install/lib/libnpu_lab.so"
export LD_LIBRARY_PATH="$PWD/install/lib:${LD_LIBRARY_PATH:-}"
python3 examples/python_client.py 0
```

脚本只用 Python 标准库：ctypes 加载 ACL 和本库、分配设备内存、上传数据、调用算子、下载校验。
它是普通 Python 的 FFI 调用，不是 PyTorch Tensor 接口，不提供自动求导、torch.compile 或图捕获支持。

## 6. 同步、资源与错误

- `nl_*` 为易理解而设计成同步 API，会等待传入 stream 的工作完成，可能同时等待该 stream 之前提交的工作。
- 借用调用者 stream/context，库内部不 `aclInit/aclFinalize/ResetDevice`。
- Add/融合/MatMul 不分配外部工作区；ReduceSum 分配工作区，在两阶段都完成后释放。
- ReduceSum 若同步失败，无法证明设备不再访问工作区，因此不立即回收该小块内存。应视为设备执行故障，按宿主工程策略停止任务并恢复/重建 context，而不是无限重试。
- 返回0表示正常同步完成，负数表示本库检查失败，正数是 ACL 状态。设备内存/stream 的合法性仍是调用契约。
- C++ 测试为独立进程，错误时退出；长期运行服务要根据 SDK 故障语义设计更完整恢复策略。
- 队列深度为1，MatMul 使用保守同步；这里不把“源码完整”包装成“性能最优”。

## 7. 为什么不是 OPP/ACLNN 包

这是完整的 **直接 Kernel 调用 + 自定义共享库** 路线，适合看清每层责任与跨工程链接。
若要标准框架集成，需要另一套构建/注册流程：

1. OpDef 描述输入、输出、dtype、format、属性与支持产品。
2. Shape/dtype 推导与 Host Tiling 回调，序列化设备侧读取的 Tiling 数据。
3. Kernel、算子元数据、编译配置与包生成。
4. 安装 OPP 包及生成的 ACLNN 头文件/库，配置算子查找路径。
5. C++ 通过该包实际生成的 `aclnnXxxGetWorkspaceSize` / `aclnnXxx` 调用。
6. PyTorch 还需要匹配 torch_npu 的 dispatcher/binding、stream/context 处理和需要时的 Autograd 注册。

这些产物依赖具体 SDK；本工程没有伪造 `aclnnNlAdd` 等生成文件。
只有确认你的实际版本与集成框架后，才适合补充可验证的 OPP 路线。

## 8. 验证层级

任何电脑可执行：

```bash
python3 tests/check_package.py
```

有普通 C++17 编译器但无 NPU，也可测试实际 Host 切分代码：

```bash
c++ -std=c++17 -Isrc/host tests/tiling_test.cpp -o tiling_test
./tiling_test
```

有目标设备后执行 C++ 和 Python 客户端。它们包含尾块、单元素、不同长度、矩阵布局与K累加校验、拒绝非法形状/别名的测试。
性能数据必须在数值通过之后测量；本包没有真实设备 benchmark 报告。
