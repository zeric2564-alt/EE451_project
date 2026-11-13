#!/usr/bin/env python3
"""Randomized complete rounds, one full warmup per measured process."""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--width", type=int, default=400)
p.add_argument("--height", type=int, default=225)
p.add_argument("--spp", type=int, default=32)
p.add_argument("--depth", type=int, default=10)
p.add_argument("--repeats", type=int, default=5)
p.add_argument("--threads", type=int, nargs="+", default=[1,2,4,8])
p.add_argument("--scenes", nargs="+", default=["simple","many","clustered"])
p.add_argument("--sweep", action="store_true")
p.add_argument("--output", default="results/raw.csv")
args = p.parse_args()
env = dict(os.environ, OMP_DYNAMIC="FALSE", OMP_PROC_BIND="close", OMP_PLACES="cores", OMP_WAIT_POLICY="PASSIVE")
def capture(command):
    try: return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as e: return str(e)
def read(path):
    try: return Path(path).read_text()
    except OSError: return None
metadata = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), platform=platform.platform(),
    cpu=capture(["lscpu"]), compiler=capture(["g++","--version"]), affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else None,
    cpu_max=read("/sys/fs/cgroup/cpu.max"), cpu_stat_before=read("/sys/fs/cgroup/cpu.stat"),
    environment={k:env[k] for k in env if k.startswith("OMP_")}, arguments=vars(args),
    build_flags="-O3 -std=c++17 -fopenmp -Wall -Wextra -Wpedantic", warmup="one complete render per process; measured rerender uses warm scene/cache")
out = ROOT / args.output
out.parent.mkdir(parents=True, exist_ok=True)
meta_path = out.with_suffix(".metadata.json")
meta_path.write_text(json.dumps(metadata,indent=2))
configs = []
for scene in args.scenes:
    configs.append((scene,"serial",1,16,1))
    if args.sweep:
        for tile in [4,8,16,32,64]:
            configs.append((scene,"tile-dynamic",max(args.threads),tile,1))
        for chunk in [1,4,16,64]:
            configs.append((scene,"row-dynamic",max(args.threads),16,chunk))
    else:
        for n in args.threads:
            for mode in ["row-static","row-dynamic","tile-static","tile-dynamic"]:
                configs.append((scene,mode,n,16,1))
hashes = {}
rng = random.Random(451)
started=time.monotonic()
with out.open("w", newline="") as f:
    writer=None
    for round_id in range(args.repeats):
        order=configs.copy();rng.shuffle(order)
        for scene,mode,n,tile,chunk in order:
            command=[str(ROOT/"raytrace"),"--scene",scene,"--mode",mode,"--threads",str(n),"--tile",str(tile),"--chunk",str(chunk),
                "--width",str(args.width),"--height",str(args.height),"--spp",str(args.spp),"--depth",str(args.depth),"--warmup","1"]
            before=time.monotonic()
            proc=subprocess.run(command,env=env,capture_output=True,text=True,check=True)
            row=json.loads(proc.stdout);row["process_wall_s"]=time.monotonic()-before
            row["round"]=round_id;row["timestamp_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
            assert row["actual_threads"] == n, "requested thread count not honored"
            if scene in hashes: assert hashes[scene]==row["hash"], "benchmark correctness mismatch"
            hashes[scene]=row["hash"]
            if writer is None: writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader()
            writer.writerow(row);f.flush()
        print(f"round {round_id+1}/{args.repeats}: {len(configs)} configurations; elapsed {time.monotonic()-started:.1f}s",flush=True)
metadata["cpu_stat_after"]=read("/sys/fs/cgroup/cpu.stat")
metadata["elapsed_s"]=time.monotonic()-started
metadata["all_hashes_match"]=True
meta_path.write_text(json.dumps(metadata,indent=2))
print(out)
