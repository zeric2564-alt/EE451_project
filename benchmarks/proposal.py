#!/usr/bin/env python3
"""Resumable, randomized proposal experiments. Each measurement has a full warmup."""
import argparse, csv, datetime, hashlib, json, os, platform, random, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/proposal'
SCENES=['room','uneven','bunny']
MODES=['row-static','row-dynamic','tile-static','tile-dynamic']
p=argparse.ArgumentParser()
p.add_argument('--stage',choices=['main','tiles','quality','cold','diagnostics','all'],default='all')
p.add_argument('--threads',nargs='+',type=int,default=[1,2,4,8])
p.add_argument('--repeats',type=int,default=5)
a=p.parse_args()
if a.repeats<5: p.error('proposal requires at least five repetitions')
if any(n<1 or n>(os.cpu_count() or 1) for n in a.threads):p.error('unsupported thread count')
env=dict(os.environ,OMP_DYNAMIC='FALSE',OMP_PROC_BIND='FALSE' if platform.system()=='Darwin' else 'close',OMP_WAIT_POLICY='PASSIVE')
if platform.system()!='Darwin':env['OMP_PLACES']='cores'
else:env.pop('OMP_PLACES',None)
OUT.mkdir(parents=True,exist_ok=True)
def capture(cmd):
    try:return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT).strip()
    except (OSError,subprocess.CalledProcessError) as e:return str(e)
def read(path):
    try:return Path(path).read_text()
    except OSError:return None
metadata=dict(start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),platform=platform.platform(),logical_cpus=os.cpu_count(),
    cpu=capture(['sysctl','-n','machdep.cpu.brand_string','hw.physicalcpu','hw.logicalcpu','hw.memsize']) if platform.system()=='Darwin' else capture(['lscpu']),
    compiler=capture(['/opt/homebrew/bin/g++-16','--version'] if platform.system()=='Darwin' else ['g++','--version']),
    runtime=capture(['otool','-L',str(ROOT/'raytrace')]) if platform.system()=='Darwin' else capture(['ldd',str(ROOT/'raytrace')]),
    affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else 'OS-managed; binding unsupported by libgomp on macOS',
    cpu_quota=read('/sys/fs/cgroup/cpu.max'),environment={k:v for k,v in env.items() if k.startswith('OMP_')},
    flags='-O3 -std=c++17 -fopenmp -Wall -Wextra -Wpedantic',binary_sha256=hashlib.sha256((ROOT/'raytrace').read_bytes()).hexdigest(),
    sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'src').glob('*')},arguments=vars(a))
# A separate command can capture hardware outside a restricted sandbox.
if (OUT/'hardware.json').exists():metadata['confirmed_hardware']=json.loads((OUT/'hardware.json').read_text())
stages=['main','tiles','quality','cold','diagnostics'] if a.stage=='all' else [a.stage]
for stage in stages:
    path=OUT/(stage+'.csv')
    meta_path=OUT/(stage+'.metadata.json')
    if meta_path.exists():
        previous=json.loads(meta_path.read_text())
        if previous['binary_sha256']!=metadata['binary_sha256']:raise SystemExit('Binary changed: use a separate results directory or archive old measurements.')
    else:meta_path.write_text(json.dumps(metadata,indent=2))
    configs=[]
    for scene in SCENES:
        if stage=='main':configs += [(scene,m,n,512,32,16) for m,n in [('serial',1)]+[(m,n) for n in a.threads for m in MODES]]
        elif stage=='tiles':configs += [(scene,m,max(a.threads),512,32,t) for m in ['tile-static','tile-dynamic'] for t in [8,16,32,64]]
        elif stage=='quality':
            selected={'room':[(512,64),(1024,64)],'uneven':[(512,128)],'bunny':[(1024,32),(1024,128)]}
            configs += [(scene,m,n,w,s,16) for w,s in selected[scene] for m,n in [('serial',1),('tile-dynamic',max(a.threads))]]
        elif stage=='cold':configs += [(scene,m,n,512,32,16) for m,n in [('serial',1),('tile-dynamic',max(a.threads))]]
        else:configs += [(scene,m,max(a.threads),512,32,16) for m in MODES]
    if stage=='diagnostics':configs += [('bunny-mixed',m,max(a.threads),512,32,16) for m in MODES]
    fields=['scene','mode','threads','width','spp','tile','round']
    def key(r):return tuple(str(r[k]) for k in fields)
    old=list(csv.DictReader(path.open())) if path.exists() else []
    done={key(r) for r in old};hashes={(r['scene'],int(r['width']),int(r['spp'])):r['hash'] for r in old}
    order=[]
    rng=random.Random(451)
    for rep in range(1 if stage=='diagnostics' else a.repeats):
        block=[dict(zip(fields,(*c,rep))) for c in configs];rng.shuffle(block);order.extend(block)
    started=time.monotonic()
    with path.open('a',newline='') as f:
        writer=None
        for i,c in enumerate(order):
            if key(c) in done:continue
            cmd=[str(ROOT/'raytrace'),'--scene',c['scene'],'--mode',c['mode'],'--threads',str(c['threads']),'--width',str(c['width']),'--height',str(c['width']),'--spp',str(c['spp']),'--tile',str(c['tile']),'--depth','10','--warmup','0' if stage=='cold' else '1']
            if stage=='cold':cmd+=['--output',str(OUT/f"{c['scene']}.png")]
            if stage=='diagnostics':cmd+=['--regions',str(OUT/f"regions_{c['scene']}_{c['mode']}.csv"),'--diagnostics',str(OUT/f"threads_{c['scene']}_{c['mode']}.csv")]
            before=time.monotonic();proc=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,check=True)
            r=json.loads(proc.stdout);r.update(round=c['round'],process_wall_s=time.monotonic()-before,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            assert r['actual_threads']==c['threads']
            hkey=(r['scene'],r['width'],r['spp'])
            if hkey in hashes:assert hashes[hkey]==r['hash'],'image mismatch'
            hashes[hkey]=r['hash']
            if writer is None:
                writer=csv.DictWriter(f,fieldnames=list(r))
                if not old:writer.writeheader()
            writer.writerow(r);f.flush()
            print(f"{stage} {i+1}/{len(order)} {c['scene']} {c['mode']} {c['threads']}t {c['width']}px {c['spp']}spp: {r['render_s']:.3f}s; elapsed {time.monotonic()-started:.0f}s",flush=True)
    meta=json.loads(meta_path.read_text());meta.update(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),rows=len(list(csv.DictReader(path.open()))));meta_path.write_text(json.dumps(meta,indent=2))
