#!/usr/bin/env python3
"""Generate ONLY the owned npu-source-* appendix from the companion source files.

Preserves manual chapters and metadata. Produces a content-addressed source ZIP.
Does not publish, compile, install SDKs, or run device code.
"""
from __future__ import annotations
import hashlib
from html import escape
import json
from pathlib import Path
import sys
import zipfile

import archive

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "examples" / "npu-operator-lab"
TOPIC = ROOT / "topics" / "npu-architecture-operator-development.json"
FILES = [
    "README.md", "NOTICE.md", "CMakeLists.txt", "cmake/NpuLabConfig.cmake.in",
    "include/npu_lab.h", "src/host/tiling.h", "src/host/npu_ops.cpp",
    "src/kernel/launchers.h", "src/kernel/elementwise_impl.h", "src/kernel/add.asc",
    "src/kernel/add_relu.asc", "src/kernel/reduce_sum.asc", "src/kernel/matmul.asc",
    "examples/cpp_client/CMakeLists.txt", "examples/cpp_client/main.cpp",
    "examples/python_client.py", "tests/tiling_test.cpp", "tests/check_package.py",
]
BASE = "https://raw.githubusercontent.com/mirror-cann/asc-devkit/82b89a15f26329511fc7fbc807d5132a1f9b4ba7/"
REFS = [
    ("ASC-DevKit 镜像固定引用：动态库支持产品与 CANN 9.0 起的构建路线",
     "examples/01_simd_cpp_api/02_features/04_compile/02_dynamic_library_compile/README.md"),
    ("ASC-DevKit 镜像固定引用：ASC 动态库 CMake",
     "examples/01_simd_cpp_api/02_features/04_compile/02_dynamic_library_compile/CMakeLists.txt"),
    ("ASC-DevKit 镜像固定引用：TPipe/TQue Add 示例",
     "examples/01_simd_cpp_api/00_introduction/01_add/add_tpipe_tque/add_tpipe_tque.asc"),
    ("ASC-DevKit 镜像固定引用：ReduceSum 接口声明",
     "include/basic_api/kernel_operator_vec_reduce_intf.h"),
    ("ASC-DevKit 镜像固定引用：DataCopyPad 接口声明",
     "include/basic_api/kernel_operator_data_copy_intf.h"),
    ("ASC-DevKit 镜像固定引用：Mmad 与 Fixpipe 路径示例",
     "examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/mmad/mmad.asc"),
]


def code(text: str) -> str:
    return "<pre><code>" + escape(text, quote=False) + "</code></pre>"


def build():
    payload = {name: (LAB / name).read_text(encoding="utf-8") for name in FILES}
    record = {name: hashlib.sha256(text.encode("utf-8")).hexdigest()
              for name, text in payload.items()}
    version = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]
    bundle = ROOT / "downloads" / f"npu-operator-lab-{version}.zip"
    included = []

    def source(name):
        included.append(name)
        text = payload[name]
        return ("<details><summary>完整文件：" + escape(name) + " · " +
                str(len(text.splitlines())) + " 行</summary>" + code(text) + "</details>")

    sections = []

    def add(sid, title, html):
        sections.append({"id": "npu-source-" + sid, "title": title, "html": html})

    add("map", "15. 源码实战入口：完整目录、职责与交付物",
        "<blockquote><strong>本节开始不再只给伪代码：提供四个案例的完整实现、构建文件、消费端和测试。</strong>"
        "完整源码不等于已经通过目标编译与设备测试；本机没有 CANN 编译器和 NPU。</blockquote>"
        "<p><strong>明确选择的教学基线：</strong>Linux、Atlas A2/A3 对应 dav-2201、CANN ≥ 9.0.0 的新 ASC 构建方式，"
        "CMake ≥ 3.20。这是为提供一致源码而作的选择，不是用户确认的当前环境。</p>"
        "<p><strong>本地工程：</strong><code>D:/workspace/dialogue-html/examples/npu-operator-lab</code><br>"
        "<strong>本次源码包：</strong><code>" + escape(bundle.as_posix()) + "</code></p>"
        "<p>下列折叠块内嵌完整文件，离线 HTML 中也能阅读。压缩包额外包含文件校验清单；包名随源码内容变化，旧包不覆盖。</p>" +
        code("npu-operator-lab/\n"
             "  include/npu_lab.h             Public C ABI\n"
             "  src/host/tiling.h             Host tiling plan\n"
             "  src/host/npu_ops.cpp          Validation / launch / lifetime\n"
             "  src/kernel/launchers.h       Internal host interface\n"
             "  src/kernel/elementwise_impl.h\n"
             "  src/kernel/add.asc\n"
             "  src/kernel/add_relu.asc\n"
             "  src/kernel/reduce_sum.asc\n"
             "  src/kernel/matmul.asc\n"
             "  CMakeLists.txt\n"
             "  cmake/NpuLabConfig.cmake.in\n"
             "  examples/cpp_client/{CMakeLists.txt,main.cpp}\n"
             "  examples/python_client.py\n"
             "  tests/{tiling_test.cpp,check_package.py}\n"
             "  README.md / NOTICE.md") +
        "<table><caption>图 12｜从业务工程调用到设备执行</caption><tbody>"
        "<tr><th>外部 C++ / Python</th><td>准备同一 context 的设备输入、输出与 stream</td></tr>"
        "<tr><th>↓ 公开 C ABI</th><td><code>nl_add_f32</code> 等符号，头文件描述类型和所有权</td></tr>"
        "<tr><th>共享库 Host 逻辑</th><td>验证参数 → 决定 Tiling → 管理必要的 workspace</td></tr>"
        "<tr><th>↓ ASC Host 启动函数</th><td>执行 <code>&lt;&lt;&lt;blocks, 0, stream&gt;&gt;&gt;</code> 启动语法</td></tr>"
        "<tr><th>设备 Kernel</th><td>Vector 或 Cube 执行搬入、计算、搬出</td></tr>"
        "<tr><th>↑ 同步后返回</th><td>调用者读取结果；本库不接管全局 ACL 生命周期</td></tr></tbody></table>"
        "<table><thead><tr><th>目录／文件</th><th>谁使用</th><th>作用</th></tr></thead><tbody>"
        "<tr><td>include/</td><td>业务工程与本库</td><td>稳定的 C 接口；不暴露设备模板、内部队列或 SDK half 类型。</td></tr>"
        "<tr><td>src/host/</td><td>Host CPU</td><td>约束、切分、启动与工作区生命周期；不是 OPP 的注册回调。</td></tr>"
        "<tr><td>src/kernel/*.asc</td><td>ASC 编译器</td><td>同时包含设备入口和 Host 启动封装；普通 C++ 不解析其启动语法。</td></tr>"
        "<tr><td>CMake / cmake/</td><td>构建与安装</td><td>输出 .so、公开头文件与可供 find_package 使用的配置。</td></tr>"
        "<tr><td>examples/</td><td>真正的外部消费端</td><td>只依赖安装包，不依赖 src/；包含资源管理和结果校验。</td></tr>"
        "<tr><td>tests/</td><td>开发与验收</td><td>区分 CPU 结构/模型测试与设备运行验证。</td></tr></tbody></table>")

    add("build", "16. 构建与安装：源码怎样变成可交付的库",
        "<p>本路线采用<strong>直接 Kernel 调用 + 自定义 C ABI 动态库</strong>。它是完整的一条接入路径，"
        "不需要伪造 <code>aclnnXxx</code> 生成文件，也不把安装动态库误称为注册了 PyTorch 算子。</p>"
        "<h3>在目标 Linux NPU 环境执行</h3>" + code(
            "# 示例路径；使用你的实际 CANN 安装位置\n"
            "source /usr/local/Ascend/cann/set_env.sh\n"
            "cmake -S . -B build \\\n"
            "  -DCMAKE_ASC_ARCHITECTURES=dav-2201 \\\n"
            "  -DCMAKE_BUILD_TYPE=Release \\\n"
            "  -DCMAKE_INSTALL_PREFIX=\"$PWD/install\"\n"
            "cmake --build build --parallel\n"
            "ctest --test-dir build --output-on-failure\n"
            "cmake --install build") +
        "<p>命令是待执行步骤，不是已完成的上机日志。目标机器必须提供 ASC 包、SDK 头文件／运行库及兼容驱动。"
        "安装到工程自己的目录，不需要 root。切换 SDK 或架构应使用新的构建目录。</p>" +
        source("CMakeLists.txt") + source("cmake/NpuLabConfig.cmake.in") +
        "<table><thead><tr><th>安装产物</th><th>用途</th></tr></thead><tbody>"
        "<tr><td>include/npu_lab.h</td><td>业务侧编译所需的 ABI 声明。</td></tr>"
        "<tr><td>lib/libnpu_lab.so 与版本链接</td><td>设备代码与 Host 启动封装所在的共享库。</td></tr>"
        "<tr><td>lib/cmake/NpuLab/</td><td>让独立工程找到导入目标 <code>NpuLab::npu_lab</code>。</td></tr></tbody></table>"
        "<p><strong>生产端</strong>编译 .asc 需要 ASC 编译器；<strong>消费端</strong>链接已编译库时不用再次编译 Kernel，"
        "但仍需要兼容的运行环境；C++ 客户端自己调用 ACL 时还需 ACL 头文件。</p>")

    add("add", "17. Case 1 · Add：把单算子的完整骨架逐层拆开",
        "<p><strong>契约：</strong>连续等长 FP32，无广播、无输入输出别名；0 ≤ N ≤ 2²⁴。"
        "N=0 不启动 Kernel。正常调用同步等待给定 stream，返回后才能按成功路径使用输出。</p>"
        "<table><caption>按这个顺序读源码，就能沿调用链走完整个 Add</caption><thead>"
        "<tr><th>顺序</th><th>文件</th><th>重点</th></tr></thead><tbody>"
        "<tr><td>①</td><td>npu_lab.h</td><td>参数不是 Host 数组，而是设备地址；stream 与内存由谁拥有。</td></tr>"
        "<tr><td>②</td><td>tiling.h</td><td>256 元素一块，最多8个任务；按 tile 索引均分，避免任务边界落在块内。</td></tr>"
        "<tr><td>③</td><td>npu_ops.cpp</td><td>验证范围/别名 → 生成计划 → 调启动函数 → 同步；该文件也包含其余案例的完整 Host 包装。</td></tr>"
        "<tr><td>④</td><td>launchers.h + add.asc</td><td>分隔普通 C++ 与 ASC 编译边界；一个函数排队启动设备 Kernel。</td></tr>"
        "<tr><td>⑤</td><td>elementwise_impl.h</td><td>分配队列，CopyIn → Add → CopyOut，处理有效尾块与缓冲生命周期。</td></tr></tbody></table>" +
        source("include/npu_lab.h") + source("src/host/tiling.h") +
        source("src/host/npu_ops.cpp") + source("src/kernel/launchers.h") +
        source("src/kernel/elementwise_impl.h") + source("src/kernel/add.asc") +
        "<h3>带着 N=1000 跟一次</h3><p>4 个 tile、4 个任务，前三个各处理256个元素，最后一个处理232个。"
        "最后任务的读取与写出长度均为 <code>232 × sizeof(float)</code> 字节。DataCopyPad 的参数以字节计；"
        "Vector Add 的 count 以元素计。局部存储仍按256个元素分配，不向 GM 越界读写。</p>"
        "<p>源码使用队列深度1，先建立清楚的所有权和依赖，不宣称已经实现高效双缓冲。"
        "本例可接受未填满块的长度，但这不意味着所有其他架构或搬运 API 都有同样的尾块能力。</p>")

    add("fused", "18. Case 2 · Add+ReLU：共享骨架，完整实现融合",
        "<p><strong>不是只给一行修改建议。</strong>这里提供完整入口与启动封装，并与上一节的完整 "
        "<code>ElementwiseKernel</code> 组合成实际构建目标。模板参数为 true 时，Add 之后执行同一 UB 输出上的 Maxs(0)。</p>" +
        source("src/kernel/add_relu.asc") +
        "<p>完整依赖：<a href=\"#npu-source-add\">第17章的公开头文件、Tiling、Host 包装、内部声明与共用 Kernel</a>，"
        "加上本文件；根 CMake 已列出所有文件。没有省略的外部业务辅助函数。</p>"
        "<p>两次 Vector 操作之间放置同流水线屏障，输出只写回一次。共享实现消除了重复搬运代码，但不掩盖融合操作。"
        "该案例沿用 FP32 契约；前文 FP16 流量表用于说明方法，不是本源代码的数据类型。</p>")

    add("reduce", "19. Case 3 · ReduceSum：完整两阶段源码与工作区",
        "<p><strong>输入 FP32[N]，输出 FP32[1]，N 必须大于零。</strong>第一阶段每个任务遍历自己的 tile，"
        "通过 ReduceSum 得到块内和，再用 Vector Add 累入该任务的局部累加器。第二阶段汇总所有任务的部分和。</p>"
        "<table><caption>图 13｜私有槽位避免并发覆盖，第二次启动实现全局汇合</caption><tbody>"
        "<tr><th>任务0</th><td>[sum0, 0, 0, 0, 0, 0, 0, 0]</td></tr>"
        "<tr><th>任务1</th><td>[sum1, 0, 0, 0, 0, 0, 0, 0]</td></tr>"
        "<tr><th>更多任务</th><td>每个任务独占32字节，最多8个任务。</td></tr>"
        "<tr><th>同 stream 第二个 Kernel</th><td>读这些部分和及已初始化的零 → ReduceSum → 仅写出一个 FP32。</td></tr>"
        "<tr><th>Host</th><td>同步完成后释放工作区；不是排队提交后立即释放。</td></tr></tbody></table>" +
        source("src/kernel/reduce_sum.asc") +
        "<p>Host 的两次启动与 aclrtMalloc / 同步 / aclrtFree 均已在第17章 "
        "<code>nl_reduce_sum_f32</code> 中完整给出。两个 Kernel 在同一 stream 上排序，"
        "这里不假设 Kernel 内存在全设备屏障。</p>"
        "<p>若运行时同步报错，无法证明设备不再使用工作区，示例不会立即回收该小块 scratch；"
        "宿主需进入故障恢复而非无限重试。正常路径无此遗留分配。</p>")

    add("matmul", "20. Case 4 · MatMul：完整 Cube 路径，而非调用伪函数",
        "<p><strong>明确缩小支持域：</strong>A、B 是连续行主序 FP16，输出与累加为 FP32；"
        "M、N、K 都是16的正倍数且不大于256。没有广播、batch、bias、数学转置或非对齐尾块。"
        "Host 对不支持的形状明确返回错误，不会静默算错。</p>"
        "<p>每个任务循环领取16×16输出块，沿K每16个元素累加。第一批设置零初值，后续批保留L0C部分和。"
        "A/B 经 ND→NZ 搬到L1，再准备 L0A/L0B 布局，执行 Mmad，最后 Fixpipe 写回完整矩阵对应位置。</p>" +
        source("src/kernel/matmul.asc") +
        "<h3>读源码时特别看四处</h3><ol>"
        "<li>A 的 <code>srcDValue = k</code>，B 的 <code>srcDValue = n</code>：采用各自完整矩阵的行跨度，不是都填16。</li>"
        "<li>A1 与 B1 共用的 L1 地址空间必须错开；不同 L0 存储中的地址0不是相互覆盖。</li>"
        "<li>B 的局部布局转换不是把业务运算改成 A×Bᵀ；公开接口仍是 A×B。</li>"
        "<li>下一轮覆盖操作数或 L0C 前必须等前一个读者结束，保守事件同步在代码中显式展示。</li></ol>"
        "<p>这是一份便于检查的数据路径实现，不是高性能 GEMM。缓存复用、流水重叠、跨核策略和精度边界仍需实测。"
        "CPU 索引模型不能验证硬件上的 NZ/Zz/Zn 格式和事件语义；这部分必须上机验收。</p>")

    add("consumer", "21. 其他工程怎样真正用起来：C++ 与 Python 完整消费端",
        "<h3>独立 C++ 工程</h3><p><code>examples/cpp_client</code> 有自己的 CMake，"
        "只通过安装目录寻找导出目标。它不包含算子 src/，也不自行编译 .asc。</p>" +
        code("cmake -S examples/cpp_client -B client-build \\\n"
             "  -DCMAKE_PREFIX_PATH=\"$PWD/install\"\n"
             "cmake --build client-build --parallel\n"
             "export LD_LIBRARY_PATH=\"$PWD/install/lib:${LD_LIBRARY_PATH:-}\"\n"
             "./client-build/npu_lab_client 0") +
        source("examples/cpp_client/CMakeLists.txt") + source("examples/cpp_client/main.cpp") +
        "<h3>普通 Python 工程：ctypes，不依赖 NumPy/PyTorch</h3>" +
        code("export NL_LIB=\"$PWD/install/lib/libnpu_lab.so\"\n"
             "export LD_LIBRARY_PATH=\"$PWD/install/lib:${LD_LIBRARY_PATH:-}\"\n"
             "python3 examples/python_client.py 0") + source("examples/python_client.py") +
        "<p>两个消费端都包括初始化、设备选择、stream、内存分配、上传、四个算子调用、下载校验与清理。"
        "对于已有服务，应该复用服务自己的 context/stream，不要每次调用都照抄测试程序的初始化和 ResetDevice。</p>"
        "<h3>直接共享库，与标准 OPP/ACLNN 框架不是一回事</h3>"
        "<table><thead><tr><th>路线</th><th>本次交付</th><th>额外工作</th></tr></thead><tbody>"
        "<tr><td>自定义 C ABI .so</td><td>完整源码、构建安装与C++/Python消费者</td><td>在所选目标环境编译和验证。</td></tr>"
        "<tr><td>OPP / ACLNN 包</td><td>只说明区别，不伪造生成产物</td><td>OpDef、推导、注册回调、序列化Tiling、算子元数据与包构建；再使用包实际生成的 GetWorkspaceSize/执行接口。</td></tr>"
        "<tr><td>PyTorch / torch_npu</td><td>ctypes 脚本不属于此路线</td><td>dispatcher/binding、Tensor契约、当前stream、设备守卫及需要时的Autograd/编译适配。</td></tr></tbody></table>"
        "<p>这里的同步 C ABI 不支持图捕获，亦不自动提供梯度。不能把 ctypes 接口接收普通 Host 数组的习惯，"
        "误用到这里要求设备地址的参数上。</p>")

    add("tests", "22. 验证状态、全部测试源码与工程说明",
        "<table><thead><tr><th>检查层级</th><th>当前状态</th></tr></thead><tbody>"
        "<tr><td>Python 包结构、语法、任务切分与矩阵索引模型</td><td>已在本机运行；属于 CPU 模型检查，不执行 NPU 代码。</td></tr>"
        "<tr><td>实际 Host Tiling 的 C++ 测试</td><td>提供完整测试源文件；本机未编译。</td></tr>"
        "<tr><td>ASC / 目标链接与安装</td><td>本机无 CANN 编译器，未执行。</td></tr>"
        "<tr><td>NPU 数值、布局、同步与性能</td><td>本机无目标设备，未执行；C++/Python 消费端是待上机的验收程序。</td></tr></tbody></table>" +
        code("# 无 SDK 时可执行的检查\npython3 tests/check_package.py\n\n"
             "# 有普通 C++17 编译器时，直接测试真实 Host Tiling 头文件\n"
             "c++ -std=c++17 -Isrc/host tests/tiling_test.cpp -o tiling_test\n./tiling_test") +
        source("tests/tiling_test.cpp") + source("tests/check_package.py") +
        "<p>客户端覆盖单元素、非块对齐、不同长度、非方阵与K循环，并拒绝非法矩阵形状和输出别名。"
        "当前用例不是所有浮点边界的穷举验证，特殊值、极端动态范围与长序列误差还应按业务契约补充。</p>" +
        source("README.md") + source("NOTICE.md") +
        "<p><strong>源码与文档维护：</strong>本章组由 <code>scripts/build_npu_lab.py</code> 从对应工程文件生成。"
        "修改源码后重新生成、校验并发布；脚本仅维护 npu-source-* 章节，保留前面的原理内容和历史版本。</p>")

    if sorted(included) != sorted(FILES):
        raise RuntimeError("Every delivered source file must be embedded exactly once")
    with archive.locked(ROOT):
        data = archive.read_json(TOPIC)
        manual = [s for s in data["sections"] if not s["id"].startswith("npu-source-")]
        data["sections"] = manual + sections
        existing = {r["url"] for r in data["references"]}
        for label, relative in REFS:
            url = BASE + relative
            if url not in existing:
                data["references"].append({"label": label, "url": url})
        archive.validate(data, TOPIC.stem)
        bundle.parent.mkdir(parents=True, exist_ok=True)
        if not bundle.exists():
            # Content-addressed name: no old delivery is overwritten.
            with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as z:
                entries = dict(payload)
                entries["SOURCE_MANIFEST.json"] = json.dumps(
                    {"sourceId": version, "sha256": record}, ensure_ascii=False, indent=2) + "\n"
                for name, text in entries.items():
                    info = zipfile.ZipInfo("npu-operator-lab/" + name, (2020, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    z.writestr(info, text.encode("utf-8"))
        archive.atomic_write(TOPIC, archive.json_text(data))
    print(f"Embedded {len(FILES)} complete files in {len(sections)} source chapters.")
    print(f"Source package: {bundle}")
    print("Draft updated; run archive.py check and publish explicitly.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    build()
