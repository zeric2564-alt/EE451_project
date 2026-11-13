# 按仓库 proposal 的完善记录

验收依据：仓库 `EE451_Proposal.pdf`。保留 room、uneven、完整 Stanford Bunny 三个必需场景，以及 bunny-mixed 对照；球体/三角形、共享 BVH、确定性采样、五种执行模式和固定 32×32 区域诊断继续共用原有算法。

## 本次修复

- **构建可用性**：Mac 支持 Apple Clang + libomp 和 Homebrew GCC；构建时记录实际编译器、选项与二进制哈希。
- **实验复现**：增加独立输出目录、低成本 smoke 模式、可用线程自动选择、至少五次重复、目录锁；续跑校验机器、源码、模型、二进制、运行库、OpenMP 环境和实验设置，拒绝重复/残缺/不一致记录。
- **证据保存**：新测试默认写入 `results/current`，避免覆盖原始 M3 实验的正确性记录。
- **报告生成**：支持指定数据目录、报告目录和实际线程/重复次数；读取数据自身的硬件与编译器信息；拒绝把 smoke 数据生成正式性能报告。
- **计时与演示**：增加 `task_prepare_s`，明确任务准备开销；网页根据可用 CPU 提供线程选项，并展示场景加载、BVH 与 PNG 时间；改进子进程错误信息。
- **回归保障**：增加实验覆盖/续跑完整性测试、网页并发任务拒绝测试和 Linux GitHub Actions 工作流。

## 本次实测

- 52,000 条 BVH 与暴力求交对照通过。
- 131 组 serial/parallel 原始 float64 像素逐字节一致。
- 3 项渲染集成、5 项指标、3 项 HTTP、5 项实验流程测试通过。
- AddressSanitizer/UBSan：几何测试与四线程 Bunny 渲染通过。
- 完整 smoke 流程：main 255、tiles 120、quality 50、cold 30、diagnostics 16，共 471 条记录；重新执行后没有重复追加。
- 原始完整数据重新分析成功：255/120/50/30/16 条记录，图像哈希、实际线程数与每配置五次测量均通过检查。
- 重新生成的离线报告含 10 张图，演示稿含 10 页、8 张图，所有嵌入 PNG 均成功解码。
- 浏览器实际完成 512×512、32 spp、四线程 Bunny 渲染；显示 69,451 个三角形、PNG 下载及分阶段计时。

详细证据见 `results/current/validation.json`、日志和 `web-demo.png`。GitHub Actions 工作流已添加，本次没有声称已在 GitHub 远端运行。

## 数据边界

`results/proposal` 和 `report/proposal` 保留原始 M3/GCC 研究；原始 CSV 对应的源码哈希与仓库基线提交 `77af667` 一致。本次的 `report/reproduced` 是这些数据的重新分析，不是新机器上的完整性能重测。

`results/current/smoke` 明确只验证实验流程，分辨率与采样量低于正式研究，不应用于最终性能结论。当前二进制的正确性、集成与内存检查另行记录。正式重测命令：

```sh
make -B
python3 benchmarks/proposal.py --stage all --output results/new-machine
.venv/bin/python benchmarks/report_proposal.py --data results/new-machine --output report/new-machine
```

Mac 构建需要 `brew install libomp` 或 `brew install gcc`。也可通过 `OMP_PREFIX` 指向已有 LLVM OpenMP 安装。完整实验需要持续运行，不应与其他渲染或基准测试同时进行。

## 本地演示与交付

在仓库目录运行 `python3 web/server.py`，打开 `http://127.0.0.1:8000`。当前工作目录已构建可执行文件；源代码压缩包不包含平台相关二进制或虚拟环境，换机器后需重新构建。

AI 辅助实现与自动化继续按项目声明注明，课程成员应审阅并理解代码。
