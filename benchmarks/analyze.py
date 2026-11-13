#!/usr/bin/env python3
"""Analyze retained measurements and build a self-contained, offline HTML report."""
import base64
from collections import defaultdict
import csv
import html
import json
from pathlib import Path
import statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"report"
REPORT.mkdir(exist_ok=True)
SCENES=["simple","many","clustered"]
MODES=["row-static","row-dynamic","tile-static","tile-dynamic"]
COLORS=["#7c3aed","#e67700","#159895","#1565c0"]
def read(name):
    path=ROOT/"results"/name
    return list(csv.DictReader(path.open())) if path.exists() else []
raw=read("raw.csv")
assert raw,"run benchmarks first"
groups=defaultdict(list)
for r in raw:groups[(r["scene"],r["mode"],int(r["threads"]))].append(r)
for scene in SCENES:
    assert len({r["hash"] for r in raw if r["scene"]==scene})==1
summary=[]
for (scene,mode,n),rows in sorted(groups.items()):
    times=[float(r["render_s"]) for r in rows]
    serial=st.median(float(r["render_s"]) for r in groups[(scene,"serial",1)])
    median=st.median(times)
    summary.append(dict(scene=scene,mode=mode,threads=n,runs=len(times),median_s=median,min_s=min(times),max_s=max(times),
        speedup=serial/median,efficiency=serial/median/n,setup_plus_render_median_s=st.median(float(r["setup_plus_render_s"]) for r in rows)))
with (ROOT/"results/summary.csv").open("w",newline="") as f:
    writer=csv.DictWriter(f,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
lookup={(r["scene"],r["mode"],r["threads"]):r for r in summary}
threads=sorted({r["threads"] for r in summary if r["mode"]!="serial"})
maxthreads=max(threads)
plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,"axes.titleweight":"bold"})
fig,axes=plt.subplots(3,3,figsize=(14,11),layout="constrained")
for col,scene in enumerate(SCENES):
    serial=lookup[(scene,"serial",1)]["median_s"]
    for mode,color in zip(MODES,COLORS):
        rr=[lookup[(scene,mode,n)] for n in threads]
        med=[r["median_s"] for r in rr]
        axes[0,col].errorbar(threads,med,yerr=[[r["median_s"]-r["min_s"] for r in rr],[r["max_s"]-r["median_s"] for r in rr]],marker="o",capsize=3,label=mode,color=color)
        axes[1,col].plot(threads,[r["speedup"] for r in rr],"o-",color=color)
        axes[2,col].plot(threads,[100*r["efficiency"] for r in rr],"o-",color=color)
    axes[0,col].axhline(serial,color="#444444",ls=":",label="serial")
    axes[0,col].set_title(scene)
    axes[1,col].plot(threads,threads,"--",color="#aaaaaa",label="ideal")
    axes[2,col].axhline(100,ls="--",color="#aaaaaa")
    for row in range(3):axes[row,col].set_xticks(threads);axes[row,col].grid(alpha=.2);axes[row,col].set_xlabel("OpenMP workers")
axes[0,0].set_ylabel("Render time (s), median / min–max")
axes[1,0].set_ylabel("Speedup vs serial")
axes[2,0].set_ylabel("Parallel efficiency (%)")
axes[0,0].legend(fontsize=8)
fig.suptitle("CPU ray tracing: measured strong scaling\n400 × 225 | 24 samples/pixel | depth 10 | 5 runs/configuration",fontsize=15)
fig.savefig(REPORT/"scaling.png",dpi=160)
plt.close(fig)

sweep=read("sweep.csv")
sweep_html=""
if sweep:
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout="constrained")
    for scene,color in zip(SCENES,COLORS):
        for ax,mode,param in [(axes[0],"tile-dynamic","tile"),(axes[1],"row-dynamic","chunk")]:
            g=defaultdict(list)
            for r in sweep:
                if r["scene"]==scene and r["mode"]==mode:g[int(r[param])].append(float(r["render_s"]))
            xs=sorted(g);ys=[st.median(g[x]) for x in xs]
            ax.errorbar(range(len(xs)),ys,yerr=[[st.median(g[x])-min(g[x]) for x in xs],[max(g[x])-st.median(g[x]) for x in xs]],marker="o",capsize=3,color=color,label=scene)
            ax.set_xticks(range(len(xs)),xs)
    axes[0].set_xlabel("Tile side length (pixels)");axes[1].set_xlabel("Dynamic chunk size (rows)")
    for ax in axes:ax.set_ylabel("Median render time (s), min–max");ax.grid(alpha=.2);ax.legend()
    fig.suptitle(f"Sensitivity at {maxthreads} workers — every tested setting retained")
    fig.savefig(REPORT/"sensitivity.png",dpi=160);plt.close(fig)

cold=read("cold.csv")
cold_summary=[]
for scene in SCENES:
    a=[float(r["process_wall_s"]) for r in cold if r["scene"]==scene and r["mode"]=="serial"]
    b=[float(r["process_wall_s"]) for r in cold if r["scene"]==scene and r["mode"]=="tile-dynamic"]
    if a and b:cold_summary.append(dict(scene=scene,serial_process_s=st.median(a),parallel_process_s=st.median(b),speedup=st.median(a)/st.median(b),runs=len(a)))
if cold_summary:
    with (ROOT/"results/cold_summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(cold_summary[0]));w.writeheader();w.writerows(cold_summary)

diagnostics=[]
for mode in MODES:
    rr=read(f"diagnostic_{mode}.csv")
    if rr:
        active=[float(r["active_s"]) for r in rr]
        finish=[float(r["finish_s"]) for r in rr]
        diagnostics.append(dict(mode=mode,active_max_mean=max(active)/(sum(active)/len(active)),last_minus_first_finish=max(finish)-min(finish)))

def img(path):
    return '<img src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()+'" alt="'+html.escape(path.stem)+'">'
def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rows)+'</tbody></table>'
main_rows=[]
for scene in SCENES:
    baseline=lookup[(scene,"serial",1)]
    for mode in MODES:
        r=lookup[(scene,mode,maxthreads)]
        main_rows.append([scene,mode,f'{baseline["median_s"]:.4f}',f'{r["median_s"]:.4f}',f'{r["min_s"]:.4f}–{r["max_s"]:.4f}',f'{r["speedup"]:.2f}×',f'{100*r["efficiency"]:.1f}%'])
main_table=table(["Scene",f"Mode ({maxthreads} workers)","Serial (s)","Parallel median (s)","Parallel min–max (s)","Speedup","Efficiency"],main_rows)
meta=json.loads((ROOT/"results/raw.metadata.json").read_text())
correct=json.loads((ROOT/"results/correctness.json").read_text())
comparisons=[]
for s in SCENES:
    tile=lookup[(s,"tile-dynamic",maxthreads)]
    row=lookup[(s,"row-dynamic",maxthreads)]
    change=100*(tile["median_s"]/row["median_s"]-1)
    comparisons.append(f"{s}: {change:+.1f}%")
scheduling_comparison="; ".join(comparisons)
dynamic_results=[lookup[(s,"tile-dynamic",maxthreads)] for s in SCENES]
speedmin=min(r["speedup"] for r in dynamic_results);speedmax=max(r["speedup"] for r in dynamic_results)
setup_ms=[1000*float(r["setup_s"]) for r in raw]
quota=meta.get("cpu_max") or "not recorded"
gallery=ROOT/"images/render_gallery.png"
gallery_html=img(gallery) if gallery.exists() else ""
if sweep:sweep_html=img(REPORT/"sensitivity.png")
cold_html=table(["Scene","Serial process (s)",f"Tile-dynamic {maxthreads} workers (s)","Process speedup"],[[r["scene"],f'{r["serial_process_s"]:.4f}',f'{r["parallel_process_s"]:.4f}',f'{r["speedup"]:.2f}×'] for r in cold_summary])
diagnostic_html=table(["Mode","Active time max/mean","Last–first worker finish (s)"],[[r["mode"],f'{r["active_max_mean"]:.3f}',f'{r["last_minus_first_finish"]:.4f}'] for r in diagnostics])
report=f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EE451 — Parallel Ray Tracer: Measured Results</title>
<style>body{{margin:0;background:#eef2f7;color:#19283c;font:16px/1.65 system-ui,sans-serif}}main{{max-width:1120px;margin:32px auto;padding:45px;background:white;border-radius:16px}}h1{{font-size:36px;line-height:1.2}}h2{{margin-top:38px;color:#1457a0}}h3{{margin-top:26px}}.eyebrow{{color:#1457a0;letter-spacing:2px;font-size:13px;font-weight:700}}.summary{{padding:22px;background:#eaf3ff;border-left:4px solid #1565c0;border-radius:4px}}table{{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow:auto}}th,td{{padding:10px 12px;border-bottom:1px solid #dde4ed;text-align:left;white-space:nowrap}}th{{background:#f1f5fa}}img{{width:100%;height:auto;margin:16px 0;border-radius:8px}}code,pre{{background:#f1f5fa}}pre{{padding:18px;overflow:auto;font-size:13px;white-space:pre-wrap}}.muted{{color:#5e6d80}}a{{color:#1457a0}}@media(max-width:700px){{main{{margin:0;padding:20px}}h1{{font-size:28px}}}}@media print{{body{{background:white}}main{{margin:0;padding:0}}img,table{{break-inside:avoid}}}}</style></head><body><main>
<div class="eyebrow">EE451 · IMPLEMENTATION &amp; MEASURED EVALUATION</div>
<h1>OpenMP Parallel CPU Ray Tracer</h1><p class="muted">Completed implementation, correctness checks, raw measurements, and reproducible analysis. This is an educational application project; no new rendering algorithm is claimed.</p>
<div class="summary"><b>实测结论：</b>在本次虚拟化 CPU 环境中，16×16 图像块动态调度使用 {maxthreads} 线程，相对同一核心算法的串行版本，在3个场景上取得 <b>{speedmin:.2f}–{speedmax:.2f} 倍</b>渲染加速。{correct['parallel_image_comparisons']} 组原始浮点图像比较完全一致。该结论支持本项目的可行性，但不保证其他电脑相同，也不表示自制调度优于成熟渲染器。</div>
<h2>1. What was implemented</h2><p>A C++17 offline path tracer with three procedural sphere scenes, diffuse/metal/glass materials, sky lighting, a pinhole camera, median-split BVH traversal, deterministic pixel/sample random streams, PPM output, and five execution modes. The serial renderer and all parallel variants share identical geometry, BVH, sampling, shading, sample order, and output quality.</p>
<p>Work is assigned by scanline or clipped square tile, with contiguous static or dynamic OpenMP scheduling. Each task owns disjoint pixels; scene data are read-only. Every version performs the same number of samples with the same maximum path depth. The serial baseline already uses the BVH, so reported scaling is not obtained by comparing against brute-force traversal.</p>
{gallery_html}<p class="muted">Actual renderer output. Preview settings: 640×360, 96 samples/pixel, depth 12. Timing experiments below use 400×225, 24 samples/pixel, depth 10; the previews are not their quality setting.</p>
<h2>2. Correctness evidence</h2><ul><li>Analytic geometry tests: sphere distance/normal, missed sphere, inside hit, axis-parallel box rays, empty scene.</li><li>30,000 random rays: BVH results matched independent linear traversal for hit/miss, nearest distance, and material.</li><li>{correct['parallel_image_comparisons']} image comparisons: raw float64 RGB bytes matched serial across modes, 1/2/4/8 workers, odd dimensions, narrow images, and tile sizes 1/16/128.</li><li>All {len(raw)} main benchmark render hashes agree within each scene. Six invalid argument cases rejected; seed-change and finite-pixel checks passed.</li><li>AddressSanitizer and UndefinedBehaviorSanitizer passed the geometry suite and a 4-thread render. Leak detection was disabled because the container prevented LeakSanitizer from inspecting process state. ThreadSanitizer was not run.</li></ul>
<h2>3. Measurement protocol</h2><p>Three scenes (5, 223, and 110 spheres), 400×225 pixels, 24 samples/pixel, depth 10, seed 451. Serial plus four parallel modes at 1, 2, 4, and 8 workers. Five complete rounds with randomized configuration order. One full unmeasured warmup precedes each measured render. The reported error bars are observed min–max ranges, not confidence intervals.</p>
<p><b>Timing boundaries:</b> render time includes OpenMP launch/worksharing/synchronization and pixel computation. The render timer starts immediately before the task loop/parallel region; per-call camera/task metadata and statistics-buffer initialization are outside that timer and are covered by fresh-process measurements. Scene/BVH creation and image allocation are measured separately; their median is {st.median(setup_ms):.3f} ms across main runs. Hashing and image writing are outside render time. Separate fresh-process measurements include those costs and PPM output, with no warmup.</p>
<p><b>Environment:</b> Intel Xeon Platinum 8573C as reported by the VM, GCC 13.3.0, Linux, 9 visible virtual CPUs, cgroup quota <code>{html.escape(quota.strip())}</code> (8 CPU-equivalents). Physical topology is not independently verified. Binding: <code>OMP_PROC_BIND=close; OMP_PLACES=cores; OMP_WAIT_POLICY=PASSIVE; OMP_DYNAMIC=FALSE</code>. Compiler flags: <code>-O3 -std=c++17 -fopenmp -Wall -Wextra -Wpedantic</code>. Virtualization, shared-host activity, frequency changes, and cache behavior can affect scaling; visible workers are not a guarantee of dedicated physical cores.</p>
<h2>4. Main results</h2>{main_table}
{img(REPORT/'scaling.png')}
<p>Speedup = median serial render time / median parallel render time. Parallel efficiency = speedup / workers. A parallel single-worker run is also retained to expose scheduling overhead. Small single-worker speedups above 1× are not parallel gains; timing variation and execution-path differences can produce them. Strong scaling holds scene size and image quality fixed. The primary 16×16 tile setting was fixed before the full benchmark.</p>
<p><b>Interpretation:</b> the measured acceleration shows that parallelizing the dominant rendering computation is useful in this environment. Scheduling results should be compared within each scene and with their observed ranges. Static and dynamic schedules are established methods; favorable tile results do not demonstrate a novel or universally superior scheduler. These measurements alone cannot isolate frequency scaling, cache effects, or host contention as a causal explanation for departures from ideal scaling.</p>
<p><b>Tile versus row dynamic scheduling:</b> relative median render-time change for tile-dynamic versus row-dynamic at {maxthreads} workers: {scheduling_comparison}. Positive means tiles took longer. The two dynamic approaches are close in these measurements; this is evidence for parallel rendering, not a demonstrated breakthrough over standard dynamic scheduling.</p>
<h2>5. Fresh-process end-to-end check</h2>{cold_html}<p>Five runs per scene/mode, no warmup, including process launch, setup, one render, hash computation, and PPM file output to local temporary storage. This is a separate experiment from the warmed render timing. Filesystem/OS caches may remain warm. The benchmark runner's main <code>process_wall_s</code> includes an extra warmup render and must not be used for single-render end-to-end speedup.</p>
<h2>6. Sensitivity and workload diagnostics</h2>{sweep_html}<p>At {maxthreads} workers, tile side lengths 4/8/16/32/64 and dynamic row chunks 1/4/16/64 were tested, five times each, with serial controls. All results are retained. Fine tasks can add scheduling overhead; large chunks can restrict parallelism or leave a long tail. In this 225-row workload, a row chunk of 64 creates only four chunks, so at most four workers can receive work even when eight are requested. A tile side of 64 creates only 28 tiles, versus 375 tiles at side 16. Any best setting here is an observed setting on these workloads, not a general optimum.</p>
{diagnostic_html}<p>Separate instrumented clustered-scene runs. Active time sums per-task durations. Finish times are relative to render start; last–first finish measures the spread of final task completion, not pure barrier wait. Instrumentation and scheduling perturb timing; these diagnostics are excluded from the principal benchmark. Task counts alone do not measure computational work.</p>
<h2>7. Project suitability and limitations</h2><p><b>适合的定位：</b>开发完整并行渲染应用，并研究任务粒度与调度对性能的影响。贡献可以明确落在程序实现、线程安全且可复现的采样、任务映射、正确性测试和公平实验上。无需声称发明光线追踪，也无需超过专业渲染器。</p><p>All scenes are synthetic sphere scenes with sky illumination; there are no mesh/texture imports, explicit area-light sampling, denoising, GUI, GPU kernels, or MPI. Fixed-depth truncation and simple materials limit physical realism. Exact agreement between versions validates consistency, not unbiasedness or agreement with a production renderer. Only one virtualized environment and one main image size/quality setting were measured. Larger scenes, a physical workstation, resolution/sample-count sweeps, and additional profiling are sensible extensions; they are not claimed as completed.</p>
<h2>8. Reproduce</h2><pre>make -j2
make test
ASAN_OPTIONS=detect_leaks=0 make sanitize
python3 benchmarks/run_benchmarks.py --width 400 --height 225 --spp 24 --repeats 5
python3 benchmarks/run_benchmarks.py --width 400 --height 225 --spp 24 --repeats 5 --sweep --output results/sweep.csv
python3 benchmarks/run_extra.py
python3 benchmarks/analyze.py</pre><p>See README.md for dependencies, timing definitions, CLI options, platform guidance, and source structure. Raw results, environment snapshots, test evidence, all measured configurations, and actual preview images are in the supplied project package. Rebuild rather than using machine-specific binaries. The implementation and automation were prepared with AI assistance; team members should understand and review them before submission.</p>
<h2>References</h2><ol><li><a href="https://raytracing.github.io/books/RayTracingInOneWeekend.html">Ray Tracing in One Weekend</a> — rendering concepts.</li><li><a href="https://raytracing.github.io/books/RayTracingTheNextWeek.html">Ray Tracing: The Next Week</a> — BVH concepts.</li><li><a href="https://pbr-book.org/3ed-2018/Introduction/Parallelization_of_pbrt">PBRT: Parallelization</a> — independent samples and thread-local state.</li><li><a href="https://pbr-book.org/3ed-2018/Introduction/pbrt_System_Overview">PBRT: System Overview</a> — image-tile rendering.</li></ol>
<details><summary>Captured CPU and compiler details</summary><pre>{html.escape(meta['cpu']+chr(10)+meta['compiler'])}</pre></details>
<p class="muted">Measurement start (UTC): {html.escape(meta['utc'])}. Results are computed directly from retained CSVs; no expected or fabricated timing values are used.</p></main></body></html>'''
(REPORT/"results.html").write_text(report)
key={"main_measured_runs":len(raw),"sweep_measured_runs":len(sweep),"cold_measured_runs":len(cold),"threads":maxthreads,"tile_dynamic_speedups":{s:lookup[(s,"tile-dynamic",maxthreads)]["speedup"] for s in SCENES},"cold":cold_summary,"correctness_comparisons":correct["parallel_image_comparisons"]}
(ROOT/"results/key_results.json").write_text(json.dumps(key,indent=2))
print(json.dumps(key,indent=2))
