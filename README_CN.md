# 项目使用说明

## 项目定位

**基于 OpenMP 的多核 CPU 光线追踪渲染器。** 推荐作为“开发完整应用并进行并行加速”方向，主要贡献是完整实现、并行任务组织、可复现采样和实验分析，不声称发明新的光线追踪算法。

程序输入为内置场景与渲染参数，输出为真实计算得到的图片。已实现串行、按行静态/动态、按块静态/动态五个版本。所有版本共用 BVH、几何求交、材质和采样代码，因此比较不会通过降低图片质量或削弱串行基线放大加速。

## 先看哪些文件

1. `report/results.html`：完整实测报告，可直接用浏览器打开，无需网络。
2. `images/render_gallery.png`：程序实际输出的图片。
3. `results/summary.csv`：运行时间、加速比、效率的汇总。
4. `results/raw.csv`：全部主实验原始数据；`sweep.csv` 为参数实验，`cold.csv` 为完整进程计时。
5. `src/core.hpp`、`src/main.cpp`：核心算法与并行执行代码。

## 编译运行

需要支持 OpenMP 的 C++17 编译器、Make 和 Python 3。当前测试平台是 Linux + GCC；Windows 建议在 WSL 中使用同一套命令。程序本身不依赖 Python 图像库。

```bash
make -j2
make test
./raytrace --scene many --mode tile-dynamic --threads 4 --width 640 --height 360 --spp 64 --output render.ppm
```

`--threads` 是线程数；`--spp` 是每像素采样数，越高通常噪声越少但计算越久；`--depth` 是最大路径深度。`--tile 16` 表示每个图像块最多为 16×16 像素。

若安装了 Pillow，可以把 PPM 转成 PNG：

```bash
python3 -c "from PIL import Image; Image.open('render.ppm').save('render.png')"
```

## 重跑实验

```bash
python3 -m pip install -r requirements.txt
python3 benchmarks/run_benchmarks.py --width 400 --height 225 --spp 24 --repeats 5
python3 benchmarks/run_benchmarks.py --width 400 --height 225 --spp 24 --repeats 5 --sweep --output results/sweep.csv
python3 benchmarks/run_extra.py
python3 benchmarks/analyze.py
```

主脚本默认测 1、2、4、8 线程。机器不足8个可用CPU时，增加 `--threads 1 2 4` 等选项；额外实验脚本使用 `--threads 4`。重跑会覆盖对应结果文件，若想保留原结果，先复制整个项目目录。

## 如何解释结果

- **正确性：**同一可执行文件内，各版本使用与线程无关的随机序列；逐像素比较原始双精度数值，而非只看图片相似。
- **核心耗时：**包括计算、线程启动、调度和同步，不包括场景准备、图像哈希或输出文件。
- **准备＋计算：**额外加上场景/BVH构建和图像内存分配，仍不等于完整进程时间。
- **完整进程耗时：**`cold.csv` 单独测量，不做预热，包含进程启动、准备、一次渲染、校验哈希及图片输出；并不保证硬件缓存完全冷。
- **加速比：**串行耗时中位数除以并行耗时中位数。每种配置至少5次，报告中位数及最小/最大值，不把单次最好成绩当结论。
- **自己的贡献：**并行应用实现与实验分析。使用 OpenMP 和图像分块本身是已有技术；不能把它们写成全球首次提出的新算法。

本次结果来自一台虚拟化运行环境，源码和脚本可复现，但在你自己的电脑上获得的时间和加速比可能不同。正式提交前应在小组可用机器上至少编译、通过测试并完成一轮实验，确保你们能够运行和解释它。

## 代码阅读顺序与三人分工

1. `core.hpp`：向量/光线 → 球体求交 → BVH → 场景 → 材质与路径追踪 → 像素采样。
2. `main.cpp`：参数解析 → 行/块任务映射 → OpenMP循环 → 计时与图像输出。
3. `tests/`：解析几何和独立遍历对照、不同调度的逐字节图像比较。
4. `benchmarks/`：随机化实验顺序、收集JSON/CSV、绘图与生成报告。

可分为渲染与正确性、并行与调度、实验与分析三部分，各成员都应能讲清楚为什么同一像素不会被多个线程同时写入，以及随机采样如何避免随线程数改变。

代码与实验自动化由AI辅助完成。正式使用时按课程要求说明辅助工具使用情况，并由小组理解和复核。更详细的实现边界、测试限制和参考文献见英文 README。
