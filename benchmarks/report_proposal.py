#!/usr/bin/env python3
"""Generate every result and claim from the proposal CSV files, with no fixed timings."""
from pathlib import Path
from collections import defaultdict
import argparse, base64, csv, html, json, statistics as st
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data',type=Path,default=ROOT/'results/proposal')
parser.add_argument('--output',type=Path,default=ROOT/'report/proposal')
args=parser.parse_args();DATA=args.data.resolve();OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
run_meta=DATA/'run.metadata.json'
metadata=json.loads(run_meta.read_text())['identity'] if run_meta.exists() else json.loads((DATA/'main.metadata.json').read_text())
if metadata.get('preset')=='smoke':parser.error('Smoke runs validate the pipeline; they are not a full proposal performance study.')

SCENES=['room','uneven','bunny'];MODES=['row-static','row-dynamic','tile-static','tile-dynamic']
def read(name):return list(csv.DictReader((DATA/(name+'.csv')).open()))
def write(name,rows):
    with (DATA/(name+'.csv')).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def median(rows,field):return st.median(float(r[field]) for r in rows)
def group(rows,keys):
    d=defaultdict(list)
    for r in rows:d[tuple(r[k] for k in keys)].append(r)
    return d
def table(headers,rows):return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(str(v))+'</th>' for v in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rows)+'</table></div>'
def image(path,alt):return '<img alt="'+html.escape(alt)+'" src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()+'">'
def paragraph(text):return '<p>'+text+'</p>'
from metrics import percentile, regional_ratio
main=read('main');tiles=read('tiles');quality=read('quality');cold=read('cold');diagnostics=read('diagnostics')
THREADS=sorted(metadata.get('threads',metadata.get('arguments',{}).get('threads',[])))
REPEATS=metadata.get('repeats',metadata.get('arguments',{}).get('repeats',0))
if not THREADS:raise ValueError('Expected thread counts missing from dataset metadata')
MAX_THREADS=max(THREADS)
if REPEATS<5:raise ValueError('At least five complete rounds required')
from proposal import configurations, check_rows
for stage,dataset in zip(['main','tiles','quality','cold','diagnostics'],[main,tiles,quality,cold,diagnostics]):
    planned=[dict(c,round=i) for i in range(1 if stage=='diagnostics' else REPEATS) for c in configurations(stage,THREADS)]
    done,_=check_rows(dataset,planned)
    if len(done)!=len(planned):raise ValueError('Incomplete '+stage+' experiment set')
for key,rows in group(main+tiles+quality+cold+diagnostics,['scene','width','height','spp','depth','seed']).items():
    assert len({r['hash'] for r in rows})==1,(key,'hash mismatch')
    assert all(int(r['actual_threads'])==int(r['threads']) for r in rows)
g=group(main,['scene','mode','threads']);summary=[]
for (scene,mode,n),rows in sorted(g.items()):
    times=[float(r['render_s']) for r in rows];base=median(g[(scene,'serial','1')],'render_s');m=st.median(times)
    summary.append(dict(scene=scene,mode=mode,threads=int(n),runs=len(times),median_s=m,min_s=min(times),max_s=max(times),speedup=base/m,efficiency=base/m/int(n)))
write('summary',summary);lookup={(r['scene'],r['mode'],r['threads']):r for r in summary}
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(3,3,figsize=(14,11),layout='constrained')
for col,scene in enumerate(SCENES):
    for mode in MODES:
        rows=[lookup[(scene,mode,n)] for n in THREADS]
        axes[0,col].errorbar(THREADS,[r['median_s'] for r in rows],yerr=[[r['median_s']-r['min_s'] for r in rows],[r['max_s']-r['median_s'] for r in rows]],marker='o',capsize=3,label=mode)
        axes[1,col].plot(THREADS,[r['speedup'] for r in rows],'o-',label=mode)
        axes[2,col].plot(THREADS,[100*r['efficiency'] for r in rows],'o-')
    axes[0,col].axhline(lookup[(scene,'serial',1)]['median_s'],color='#444',ls=':',label='serial')
    axes[0,col].set_title(scene);axes[1,col].plot(THREADS,THREADS,'--',color='#aaa')
    for row in range(3):axes[row,col].set_xticks(THREADS);axes[row,col].set_xlabel('Workers');axes[row,col].grid(alpha=.2)
axes[0,0].set_ylabel('Render seconds: median, min-max');axes[1,0].set_ylabel('Speedup');axes[2,0].set_ylabel('Efficiency (%)');axes[0,0].legend(fontsize=8)
fig.suptitle(f'512 × 512, 32 samples/pixel, depth 10 · {REPEATS} measured runs per configuration');fig.savefig(OUT/'scaling.png',dpi=150);plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
for ax,scene in zip(axes,SCENES):
    for mode in ['tile-static','tile-dynamic']:
        rows=[[float(r['render_s']) for r in tiles if r['scene']==scene and r['mode']==mode and int(r['tile'])==t] for t in [8,16,32,64]]
        ax.errorbar([8,16,32,64],[st.median(v) for v in rows],yerr=[[st.median(v)-min(v) for v in rows],[max(v)-st.median(v) for v in rows]],marker='o',capsize=3,label=mode)
    ax.set_title(scene);ax.set_xlabel('Tile side (pixels)');ax.set_ylabel('Render seconds');ax.set_xticks([8,16,32,64]);ax.legend(fontsize=8);ax.grid(alpha=.2)
fig.suptitle(f'Tile-size sensitivity · {MAX_THREADS} workers · median and min-max');fig.savefig(OUT/'tiles.png',dpi=150);plt.close(fig)
regional=[];loads=[]
for scene in SCENES+['bunny-mixed']:
    # Confirm every counter agrees across schedules, not merely its aggregate.
    region_sets=[read(f'regions_{scene}_{mode}') for mode in MODES]
    assert all(r==region_sets[0] for r in region_sets)
    regions=region_sets[0]
    fig,axes=plt.subplots(1,4,figsize=(15,3.8),layout='constrained')
    for ax,metric in zip(axes,['rays','path_depth','node_visits','triangle_tests']):
        values=[int(r[metric]) for r in regions];kind,ratio=regional_ratio(values)
        regional.append(dict(scene=scene,metric=metric,regions=len(values),total=sum(values),p10=percentile(values,.1),p90=percentile(values,.9),mean=st.mean(values),maximum=max(values),ratio_kind=kind,ratio=ratio))
        matrix=[[0]*16 for _ in range(16)]
        for r in regions:matrix[int(r['y'])//32][int(r['x'])//32]=int(r[metric])
        im=ax.imshow(matrix,cmap='magma');ax.set_title(metric.replace('_',' '));ax.set_xlabel('32-pixel region x');ax.set_ylabel('32-pixel region y');fig.colorbar(im,ax=ax,shrink=.75)
    fig.suptitle(scene+' · independent 32 × 32 regions, 512 × 512 / 32 spp');fig.savefig(OUT/f'heatmap_{scene}.png',dpi=150);plt.close(fig)
    for mode in MODES:
        rr=read(f'threads_{scene}_{mode}');busy=[float(r['active_s']) for r in rr];mean=st.mean(busy)
        loads.append(dict(scene=scene,mode=mode,workers=len(rr),busy_mean_s=mean,busy_max_s=max(busy),LI=max(busy)/mean-1 if mean else None,tasks=sum(int(r['tasks']) for r in rr),pixels=sum(int(r['pixels']) for r in rr)))
write('regional_summary',regional);write('thread_summary',loads)
fig,axes=plt.subplots(1,4,figsize=(14,4),layout='constrained')
for ax,scene in zip(axes,SCENES+['bunny-mixed']):
    rows=[r for r in loads if r['scene']==scene];ax.bar(range(4),[r['LI'] for r in rows],color=['#546c8c','#30978a','#967ab1','#d19145']);ax.set_xticks(range(4),[r['mode'] for r in rows],rotation=35,ha='right');ax.set_title(scene);ax.set_ylabel('LI = max(B) / mean(B) - 1')
fig.suptitle('Separate diagnostic runs · busy time includes task computation only');fig.savefig(OUT/'load.png',dpi=150);plt.close(fig)
quality_summary=[]
for (scene,w,spp),rows in group(quality,['scene','width','spp']).items():
    a=[r for r in rows if r['mode']=='serial'];b=[r for r in rows if r['mode']=='tile-dynamic']
    quality_summary.append(dict(scene=scene,width=int(w),spp=int(spp),serial_s=median(a,'render_s'),parallel_s=median(b,'render_s'),speedup=median(a,'render_s')/median(b,'render_s'),serial_min_s=min(float(r['render_s']) for r in a),serial_max_s=max(float(r['render_s']) for r in a),parallel_min_s=min(float(r['render_s']) for r in b),parallel_max_s=max(float(r['render_s']) for r in b)))
write('quality_summary',quality_summary)
cold_summary=[]
for (scene,mode),rows in group(cold,['scene','mode']).items():
    cold_summary.append(dict(scene=scene,mode=mode,**{k:median(rows,k) for k in ['loading_s','bvh_s','render_s','png_s','end_to_end_s','process_wall_s']}))
write('cold_summary',cold_summary)
negative=[];overlap=[];comparisons=[]
for scene in SCENES:
    for decomposition in ['row','tile']:
        for n in THREADS:
            a=lookup[(scene,decomposition+'-static',n)];b=lookup[(scene,decomposition+'-dynamic',n)];change=100*(b['median_s']/a['median_s']-1)
            comparisons.append(dict(scene=scene,decomposition=decomposition,threads=n,dynamic_change_percent=change,range_overlap=max(a['min_s'],b['min_s'])<=min(a['max_s'],b['max_s'])))
            if change>0:negative.append((scene,decomposition,n,change))
            if max(a['min_s'],b['min_s'])<=min(a['max_s'],b['max_s']):overlap.append((scene,decomposition,n))
write('schedule_comparisons',comparisons)
correct=json.loads((DATA/'correctness.json').read_text()) if (DATA/'correctness.json').exists() else {'parallel_image_comparisons':0}
validation=json.loads((DATA/'validation.json').read_text()) if (DATA/'validation.json').exists() else {'note':'No separate validation record provided for this dataset; runtime hashes and workers were checked.'}
hw=metadata.get('confirmed_hardware',{})
cpu_label=str(hw.get('cpu') or metadata.get('cpu') or metadata.get('platform','unknown'))
if cpu_label.startswith('unavailable:') or cpu_label.startswith('Command '):cpu_label=metadata.get('platform','CPU details unavailable')
environment_text='Recorded host: '+cpu_label+'. Logical CPUs: '+str(metadata.get('logical_cpus','unknown'))+'. Compiler: '+str(metadata.get('build',{}).get('compiler_version',metadata.get('compiler','unknown')))+'. OpenMP environment: '+str(metadata.get('environment',{}))+'. Affinity: '+str(metadata.get('affinity','unknown'))+'. CPU quota: '+str(metadata.get('cpu_quota','unavailable'))+'. Full runtime and build records appear below.'

key=dict(main_runs=len(main),tile_runs=len(tiles),quality_runs=len(quality),cold_runs=len(cold),diagnostic_runs=len(diagnostics),exact_image_comparisons=correct['parallel_image_comparisons'],tile_dynamic_speedup={s:lookup[(s,'tile-dynamic',MAX_THREADS)]['speedup'] for s in SCENES},dynamic_slower_cases=len(negative),overlapping_range_cases=len(overlap))
(DATA/'key_results.json').write_text(json.dumps(key,indent=2))
parts=[]
parts += ['<h1>Multicore CPU Path Tracing</h1><p class="subtitle">USC EE451 · Proposal implementation and measured scheduling study</p>',paragraph('Team: yuzhaoma; YUXUAN LU; zhenyan zhou. This report evaluates one shared C++17 path tracer on an Apple M3 CPU. The serial and four OpenMP modes share the geometry, BVH, camera, sample IDs and material kernel.')]
parts += ['<h2>1. Results at a glance</h2>',table(['Scene','Tile-dynamic, 8 workers','Speedup','Efficiency'],[[s,f"{lookup[(s,'tile-dynamic',MAX_THREADS)]['median_s']:.3f} s",f"{key['tile_dynamic_speedup'][s]:.2f}×",f"{lookup[(s,'tile-dynamic',MAX_THREADS)]['efficiency']*100:.1f}%"] for s in SCENES]),paragraph(f"Separate correctness record: {correct['parallel_image_comparisons']} raw float64 image comparisons. Runtime output hashes agree across matched configurations. The study retains {len(main)} main, {len(tiles)} tile-size, {len(quality)} selected-quality and {len(cold)} cold-process measurements. Every configuration has five measured repetitions. Dynamic scheduling had a slower median in {len(negative)} of 24 matched scene/decomposition/thread comparisons; {len(overlap)} pairs had overlapping observed ranges. No universal scheduler winner is claimed.")]
parts += ['<h2>2. Scenes and rendering algorithm</h2>',paragraph('Scene A (room): a procedural room with diffuse wall triangles, two spheres and an emissive rectangular ceiling area light. There is no sky illumination in the room; diffuse paths gather the area light by random-walk sampling. Scene B (uneven): deterministic reflective/refractive spheres concentrated on one side, with simpler geometry elsewhere. Scene C (bunny): all 69,451 reconstructed Stanford Bunny triangles, normalized to height 3, offset to x = -1.1, over a ground sphere. The additional bunny-mixed diagnostic changes mesh materials spatially and adds a glass sphere; the original Bunny remains the control.'),paragraph('Two-sided Möller–Trumbore triangle tests and sphere tests feed the same median-split BVH (up to four primitives per leaf). Diffuse, rough metal and dielectric scattering use deterministic pixel/sample-indexed SplitMix64 streams. Per-pixel sample accumulation order is fixed. A pinhole camera and gamma-2 display conversion produce RGB8 PNG. The native PNG writer uses lossless uncompressed DEFLATE blocks; output timing therefore measures this implementation, not an optimized PNG encoder.')]
for s in SCENES:parts += ['<h3>'+s+'</h3>',image(DATA/(s+'.png'),s+' actual renderer output, 512 square, 32 spp')]
parts += [paragraph('Bunny data and reconstruction: <a href="https://graphics.stanford.edu/data/3Dscanrep/">Stanford Computer Graphics Laboratory</a>. The packaged OBJ preserves the official reconstructed PLY’s 35,947 vertices and 69,451 faces; source/archive/output SHA-256 and conversion instructions are in assets/. Free research redistribution is permitted with attribution; commercial use requires permission. The source model has five bottom holes, so this is not a watertight mesh benchmark.')]
parts += ['<h2>3. Parallel structure and correctness</h2>',paragraph('The serial loop and row-static, row-dynamic, tile-static and tile-dynamic modes call the identical pixel function. Each task owns disjoint pixels; workers read immutable scene data. Dynamic chunks contain one row or tile. Static assignment is contiguous. Tile boundaries are clipped. Region profiling uses worker-private arrays followed by a deterministic integer reduction; no atomic counters enter the primary timing runs.'),paragraph('Analytic tests cover sphere hits, triangle hit/miss/backface/parallel/degenerate cases, bounding boxes and empty scenes. 52,000 randomized rays compare BVH with linear primitive traversal, including the full Bunny and mixed-material mesh. Image comparisons cover the three required scenes plus the mixed Bunny, all four parallel modes, 1/2/4/8 workers, odd dimensions, narrow images and tile sizes 1/16/128. Additional integration tests decode PNG and compare it with PPM, validate CSV timing, reject malformed OBJ data and verify region counters and raw pixels are identical across schedules. These establish implementation consistency, not accuracy against PBRT or unbiased finite-depth rendering.')]
parts += ['<h2>4. Hardware and controlled methodology</h2>',paragraph(html.escape(environment_text)),paragraph('Main: 512×512, 32 spp, depth 10, seed 451, tiles 16×16, five randomized complete rounds. Serial plus four modes at 1/2/4/8 workers gives 255 observations. Each process performs one full unmeasured warmup before one measured render. Tile experiment: both static and dynamic, 8/16/32/64 tiles at eight workers, same three scenes and five rounds. Selected quality runs cover 512 and 1024 square at 32/64/128 spp; this is a selected subset, not the full Cartesian product. Compiler flags are recorded in the environment metadata below. The runner checks actual workers and output hashes.'),paragraph('Render time includes task processing, OpenMP launch, worksharing and synchronization. Scene loading/generation and BVH construction are separate. Camera/task metadata and counter allocation precede the render timer. Hashing, output encoding and file writing follow it. end_to_end_s is cumulative in-process time since startup and includes warmup when enabled; process_wall_s in warmed runs also includes warmup and process launch. Only cold.csv (warmup disabled, one render per process) is used for single-frame end-to-end analysis. Diagnostic output is excluded from principal timing. Min–max is observed spread, not a confidence interval.')]
parts += ['<h2>5. Strong scaling</h2>',image(OUT/'scaling.png','Rendering latency, speedup and efficiency'),table(['Scene','Mode','Workers','Median s','Min–max s','Speedup','Efficiency'],[[r['scene'],r['mode'],r['threads'],f"{r['median_s']:.4f}",f"{r['min_s']:.4f}–{r['max_s']:.4f}",f"{r['speedup']:.2f}",f"{r['efficiency']*100:.1f}%"] for r in summary]),paragraph('S(p) = median serial time / median parallel time. E(p) = S(p) / actual workers. Serial already uses the same BVH, so parallel gains are not conflated with acceleration-structure changes. Single-worker differences reflect loop/scheduling overhead and timing variation, not multicore speedup.')]
parts += ['<h2>6. Tile sensitivity and negative results</h2>',image(OUT/'tiles.png','Tile sensitivity'),paragraph('Fine tiles expose more parallel work but increase scheduling calls. Coarse tiles reduce overhead but may leave expensive regions on one worker. The primary 16-pixel tile was specified independently of this sweep. No best observed tile is presented as a general optimum.'),table(['Scene','Decomposition','Workers','Dynamic slower (%)'],[[s,d,n,f'{v:.2f}'] for s,d,n,v in negative]),paragraph(f'The table retains every case where dynamic had a slower median. {len(overlap)} of 24 static/dynamic pairs overlap in their min–max ranges; these data do not establish statistical significance. Cache effects, OS scheduling, heterogeneous cores and background activity are plausible influences, not measured causal explanations.')]
parts += ['<h2>7. Spatial workload and thread imbalance</h2>',paragraph('Diagnostic measurements use fixed 32×32 regions, independently of the rendering scheduler. rays counts every traced path segment; path_depth sums successful surface interactions (including emissive hits) over samples; node_visits counts entered BVH nodes, including nodes rejected by their box; triangle_tests counts primitive triangle intersection attempts. Traversal work includes unsuccessful tests. Values are raw regional totals at fixed pixel/sample count. Ratios use linearly interpolated quantiles: P90/P10 if P10 > 0, otherwise max/mean when mean > 0; all-zero metrics have no ratio.')]
for s in SCENES+['bunny-mixed']:parts += [image(OUT/f'heatmap_{s}.png',s+' workload heatmaps')]
parts += [table(['Scene','Metric','P10','P90','Ratio rule','Ratio'],[[r['scene'],r['metric'],f"{r['p10']:.0f}",f"{r['p90']:.0f}",r['ratio_kind'],'—' if r['ratio'] is None else f"{r['ratio']:.3f}"] for r in regional]),image(OUT/'load.png','Thread imbalance'),table(['Scene','Mode','Mean busy s','Max busy s','LI'],[[r['scene'],r['mode'],f"{r['busy_mean_s']:.4f}",f"{r['busy_max_s']:.4f}",f"{r['LI']:.4f}"] for r in loads]),paragraph('LI = max(Bi)/mean(Bi) − 1, using the sum of each worker’s task durations. Idle workers remain in the mean. Diagnostic busy time includes profiling overhead and does not replace wall time. Each workload profile is one diagnostic run, so thread imbalance comparisons are descriptive; counters are exactly invariant across schedules. Spatial variation alone does not establish that dynamic scheduling will win. The mixed-material Bunny provides a reproducible secondary diagnostic, not a replacement for the required control.')]
parts += ['<h2>8. Selected resolution / sample workloads</h2>',table(['Scene','Resolution','SPP','Serial median s','8-worker median s','Speedup'],[[r['scene'],str(r['width'])+'²',r['spp'],f"{r['serial_s']:.3f}",f"{r['parallel_s']:.3f}",f"{r['speedup']:.2f}"] for r in quality_summary]),paragraph('All selected workloads have five repetitions with full warmups. These selected comparisons test larger image/sample costs; they do not replace a full scaling study at every quality. Min/max values remain in quality_summary.csv and all observations in quality.csv.')]
parts += ['<h2>9. Separate loading, BVH, PNG and end-to-end costs</h2>',table(['Scene','Mode','Load s','BVH s','Render s','PNG s','In-process s','Process wall s'],[[r['scene'],r['mode']]+[f"{r[k]:.4f}" for k in ['loading_s','bvh_s','render_s','png_s','end_to_end_s','process_wall_s']] for r in cold_summary]),paragraph('These are separate five-run fresh-process experiments, without warmup, including PNG output to local storage. Process wall time excludes web network delay and includes process launch. OS and filesystem caches may remain warm; these are not cold-hardware-cache measurements. Independently computed component medians need not sum to the median total.')]
parts += ['<h2>10. Web demo, reproducibility and limitations</h2>',paragraph('Run python3 web/server.py and open http://127.0.0.1:8000. The local interface selects scene, scheduling, worker count, resolution, samples and tile size, then launches one bounded native task, polls its state, displays the PNG and actual timings, and provides a download. It is a demonstration, outside the renderer timing, with no cloud dependency.'),'<pre>make -j2\nmake test\n.venv/bin/python tests/test_proposal.py\npython3 benchmarks/proposal.py --stage all --output results/current/experiment\n.venv/bin/python benchmarks/report_proposal.py --data results/current/experiment --output report/current\npython3 web/server.py</pre>',paragraph('The renderer uses finite-depth random walks with no explicit next-event light sampling, denoising, textures or full PBRT import. The area-lit room can be noisy at modest spp. Flat triangle normals expose mesh facets. A single desktop and five samples per configuration limit generalization. No novelty over Embree/PBRT or superiority to production renderers is claimed. No thread race sanitizer result is claimed. See validation.json for actual sanitizer and integration-test outcomes. The repository’s original sphere-only report and measurements are historical and do not support this proposal study.'),paragraph('Implementation and experiment automation were prepared with AI assistance. The team should review the code and follow the course’s attribution requirements. Milestone coverage is mapped in PROPOSAL_CHECKLIST.md; this package does not claim historical Day 7/14/21/30 submissions took place.')]
parts += ['<h2>References</h2>','<ol><li><a href="https://raytracing.github.io/books/RayTracingInOneWeekend.html">Ray Tracing in One Weekend</a>: educational path-tracing and material concepts.</li><li><a href="https://raytracing.github.io/books/RayTracingTheNextWeek.html">The Next Week</a>: bounding volume hierarchies.</li><li><a href="https://www.embree.org/">Intel Embree</a>; Wald et al., Embree: A Kernel Framework for Efficient CPU Ray Tracing, ACM TOG 2014.</li><li><a href="https://pbr-book.org/">Physically Based Rendering</a>: rendering and parallelization background.</li><li><a href="https://graphics.stanford.edu/data/3Dscanrep/">Stanford 3D Scanning Repository</a>: Bunny data and redistribution conditions.</li></ol>', '<details><summary>Recorded environment and validation</summary><pre>'+html.escape(json.dumps(metadata,indent=2))+'</pre><pre>'+html.escape(json.dumps(validation,indent=2))+'</pre></details>']
style='body{font:16px/1.65 system-ui,sans-serif;background:#edf1f5;color:#1c2c3b;margin:0}main{max-width:1150px;margin:30px auto;background:white;padding:42px}h1{font-size:40px;line-height:1.2}h2{margin-top:42px;color:#18526c}.subtitle{color:#607684}img{max-width:100%;display:block;margin:20px auto}h3+img{max-width:480px}.scroll{overflow:auto}table{border-collapse:collapse;font-size:13px;width:100%}th,td{padding:9px;text-align:left;border-bottom:1px solid #dae1e6;white-space:nowrap}th{background:#eef3f7}pre{white-space:pre-wrap;background:#f1f4f6;padding:20px;font-size:12px}a{color:#126478}@media(max-width:700px){main{padding:20px;margin:0}h1{font-size:30px}}@media print{body{background:white}main{margin:0;padding:0}img,table{break-inside:avoid}}'
def labels(text):
    return (text.replace('an Apple M3 CPU',html.escape(cpu_label)).replace('an Apple M3',html.escape(cpu_label))
        .replace('8 workers',str(MAX_THREADS)+' workers').replace('8-worker',str(MAX_THREADS)+'-worker')
        .replace('eight workers',str(MAX_THREADS)+' workers').replace('1/2/4/8','/'.join(map(str,THREADS)))
        .replace('255 observations',str(len(main))+' observations').replace('of 24','of '+str(len(comparisons)))
        .replace('/24','/'+str(len(comparisons))).replace('five measured',str(REPEATS)+' measured')
        .replace('five repetitions',str(REPEATS)+' repetitions').replace('five randomized',str(REPEATS)+' randomized')
        .replace('Five randomized',str(REPEATS)+' randomized').replace('five rounds',str(REPEATS)+' rounds').replace('five-run',str(REPEATS)+'-run')
        .replace('five samples',str(REPEATS)+' samples').replace('Five samples',str(REPEATS)+' samples')
        .replace('five observations',str(REPEATS)+' observations'))
parts=[labels(part) for part in parts]
(OUT/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EE451 proposal study</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')
print(json.dumps(key,indent=2))
# Offline presentation: native HTML text/tables, responsive figures, arrow-key navigation.
slide_data=[
('Multicore CPU Path Tracing', '<p class="lead">Task decomposition and scheduling on an Apple M3</p>'+paragraph('USC EE451<br>yuzhaoma · YUXUAN LU · zhenyan zhou')+image(DATA/'bunny.png','Stanford Bunny rendered by the application')),
('The scheduling question', paragraph('Does dynamic scheduling reduce the cost of uneven image regions enough to offset its overhead?')+'<ul><li>Compare rows with tiles using the same rendering kernel.</li><li>Compare static with dynamic assignment at fixed output quality.</li><li>Measure variation and retain negative results.</li></ul>'),
('One renderer, five execution modes', '<ol><li>Load scene and build a shared, read-only BVH.</li><li>Assign disjoint rows or tiles to OpenMP workers.</li><li>Trace deterministic pixel/sample-indexed paths.</li><li>Write PNG and collect separate timings.</li></ol>'+paragraph('Serial is an ordinary loop. All versions use identical geometry, materials, BVH and sample order.')),
('Three required scenes', '<div class="three">'+''.join('<div>'+image(DATA/(s+'.png'),s)+'<p>'+s+'</p></div>' for s in SCENES)+'</div>'+paragraph('Room with an area light · concentrated reflective/refractive spheres · 69,451-triangle Stanford Bunny. Data credit: Stanford Computer Graphics Laboratory.')),
('Correctness and measurement controls', '<ul><li>52,000 BVH-versus-linear ray comparisons.</li><li>'+str(correct['parallel_image_comparisons'])+' exact float64 image comparisons.</li><li>Five randomized rounds, each with a full warmup.</li><li>512², 32 spp, depth 10; 1/2/4/8 workers.</li><li>Expensive diagnostic counters disabled in timed runs.</li></ul>'+paragraph(html.escape(cpu_label)+' · '+str(metadata.get('logical_cpus','unknown'))+' logical CPUs. See the report for the recorded compiler/runtime and affinity.')),
('Strong scaling at fixed quality',image(OUT/'scaling.png','Scaling charts')),
('Tile size and scheduling tradeoffs',image(OUT/'tiles.png','Tile sensitivity')+paragraph(f'Dynamic had a slower median in {len(negative)}/24 matched comparisons; {len(overlap)} pairs had overlapping min–max ranges. Observed spread is not a confidence interval.')),
('Work is spatially uneven',image(OUT/'heatmap_bunny.png','Bunny spatial work')+image(OUT/'load.png','Busy time imbalance')+paragraph('32×32 measurement regions are independent of task tiles. LI = max busy time / mean busy time − 1. Diagnostics are separate from timing.')),
('Higher quality and end-to-end latency',table(['Scene','Resolution','SPP','Serial s','8-worker s'],[[r['scene'],str(r['width'])+'²',r['spp'],f"{r['serial_s']:.2f}",f"{r['parallel_s']:.2f}"] for r in quality_summary])+paragraph('Separate cold-process runs include loading, BVH construction, rendering and PNG output. Warmed process times contain two renders and are not single-frame end-to-end latency.')),
('Demonstration and conclusions', '<pre>make\npython3 web/server.py\n# open http://127.0.0.1:8000</pre>'+paragraph('The application implements the proposal’s renderer, mesh, scheduling and diagnostics. Speedups depend on scene, task size and worker count. This study does not establish a universally best schedule or superiority over production renderers.')+paragraph('Limits: one heterogeneous desktop; five observations per configuration; finite-depth paths; no explicit light sampling; flat mesh normals. Reproduce from results/proposal and benchmarks/proposal.py.'))]
slide_style='body{margin:0;background:#102332;color:#eef4f7;font:24px/1.5 system-ui}section{display:none;max-width:1250px;min-height:90vh;margin:auto;padding:48px 60px}section.active{display:block}h1{font-size:42px;margin:0 0 28px;line-height:1.15;color:#bce7c4}p{margin:20px 0}.lead{font-size:32px}img{max-width:100%;max-height:64vh;object-fit:contain;display:block;margin:auto}section:first-child img{max-height:40vh;margin-left:0}section:nth-child(8) img{max-height:29vh}.three{display:flex;gap:20px}.three>div{flex:1;text-align:center}.three img{max-width:100%}li{margin:16px 0}table{font-size:21px;border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #536471}pre{font-size:24px;padding:20px;background:#193647}nav{position:fixed;bottom:0;left:0;right:0;background:#0a1823;display:flex;align-items:center;justify-content:center;gap:24px;padding:10px;font-size:14px}button{background:none;border:1px solid #849ba8;color:white;border-radius:4px;padding:7px 20px;cursor:pointer}@media(max-width:750px){body{font-size:18px}section{padding:26px 20px 80px}h1{font-size:32px}.three{display:block}.three img{max-height:20vh}table{font-size:13px}pre{font-size:16px}}@media print{body{background:white;color:#142735}section,section.active{display:block;break-after:page;height:100vh;padding:20px}h1{color:#18526c}nav{display:none}img{max-height:60vh}}'
slides=''.join('<section'+(' class="active"' if i==0 else '')+'><h1>'+title+'</h1>'+body+'</section>' for i,(title,body) in enumerate(slide_data))
slides=labels(slides)
(OUT/'presentation.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EE451 presentation</title><style>'+slide_style+'</style>'+slides+'<nav><button id="prev">← Previous</button><span id="page"></span><button id="next">Next →</button></nav><script>let index=0;const slides=[...document.querySelectorAll("section")];function show(n){index=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>s.classList.toggle("active",i===index));document.getElementById("page").textContent=(index+1)+" / "+slides.length;window.scrollTo(0,0)}document.getElementById("prev").onclick=()=>show(index-1);document.getElementById("next").onclick=()=>show(index+1);document.onkeydown=e=>{if(e.key==="ArrowRight"||e.key===" "){e.preventDefault();show(index+1)}if(e.key==="ArrowLeft")show(index-1)};show(0);</script></html>')
