# EE451 proposal 完整实现

请以 [逐项验收清单](PROPOSAL_CHECKLIST.md) 和 [新实验报告](report/proposal/report.html) 为准。仓库原有报告只覆盖球体场景，保留为历史记录。

本次补齐：三角形求交、混合 BVH、全部 69,451 面的 Stanford Bunny、房间面积光源、不均匀反射/折射场景、原生 PNG、分阶段计时、固定 32×32 区域计数、工作量热图、线程负载不平衡分析、要求的实验配置和本地网页演示。

```sh
make -j2
make test
./raytrace --scene bunny --mode tile-dynamic --threads 8 --width 512 --height 512 --spp 32 --output bunny.png
python3 web/server.py
```

浏览器打开 `http://127.0.0.1:8000`，选择场景、调度方式、线程、分辨率和采样量，提交后查看 PNG 和实际耗时。

- [最终报告](report/proposal/report.html)：独立 HTML，包含全部图表和数据解释。
- [答辩演示稿](report/proposal/presentation.html)：离线 HTML 幻灯片，左右方向键翻页。
- `results/proposal/`：本机原始 CSV、硬件记录、正确性证据、图片与分析汇总。
- `assets/`：官方 Bunny 转换后的 OBJ、来源说明和校验值。

分析依赖和完整复现：

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tests/test_proposal.py
.venv/bin/python tests/test_web.py
python3 benchmarks/proposal.py --stage all
.venv/bin/python benchmarks/report_proposal.py
```

实验支持断点续跑；已有结果会跳过，二进制变化会拒绝混入旧数据。重新测量前先归档 `results/proposal/` 并重新记录硬件，详见英文 README。

主实验 255 次、tile 实验 120 次、选定高质量配置 50 次、无预热端到端实验 30 次，另有 16 次诊断。主实验为 512×512、32 spp；选定配置覆盖 1024×1024 和 64/128 spp。所有计时配置均有五次测量；主计时不启用昂贵计数器。

本机为 Apple M3、8 核、16 GiB。不同性能核心和系统调度影响扩展性；这里的加速比不代表专业渲染器对比。面积光源采用随机路径采样，有限深度、低 spp 噪声和平面三角形法线属于已记录限制。历史日期里程碑只做交付物映射，不声称已发生课程提交。
