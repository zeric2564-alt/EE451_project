#!/usr/bin/env python3
"""Cold end-to-end runs, separate thread diagnostics, and real render previews."""
import argparse
import csv
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument("--threads",type=int,default=8)
args=parser.parse_args()
env=dict(os.environ, OMP_DYNAMIC="FALSE",OMP_PROC_BIND="close",OMP_PLACES="cores",OMP_WAIT_POLICY="PASSIVE")
def run(scene,mode,threads,more):
    cmd=[str(ROOT/"raytrace"),"--scene",scene,"--mode",mode,"--threads",str(threads)]+more
    before=time.monotonic()
    r=subprocess.run(cmd,env=env,text=True,capture_output=True,check=True)
    wall=time.monotonic()-before
    row=json.loads(r.stdout)
    row["process_wall_s"]=wall
    assert row["actual_threads"]==threads
    return row
rows=[]
hashes={}
rng=random.Random(451)
with tempfile.TemporaryDirectory() as tmp:
    for rep in range(5):
        configs=[(s,m,n) for s in ["simple","many","clustered"] for m,n in [("serial",1),("tile-dynamic",args.threads)]]
        rng.shuffle(configs)
        for s,m,n in configs:
            r=run(s,m,n,["--width","400","--height","225","--spp","24","--output",str(Path(tmp)/"render.ppm")])
            if s in hashes: assert hashes[s]==r["hash"], "cold image mismatch"
            hashes[s]=r["hash"]
            r["round"]=rep;rows.append(r)
        print(f"cold round {rep+1}/5",flush=True)
    with (ROOT/"results/cold.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    previews=[]
    for scene in ["simple","many","clustered"]:
        path=Path(tmp)/"preview.ppm"
        r=run(scene,"tile-dynamic",args.threads,["--width","640","--height","360","--spp","96","--depth","12","--output",str(path)])
        Image.open(path).save(ROOT/f"images/{scene}.png")
        previews.append(r)
        print(f"preview {scene}: {r['render_s']:.3f}s",flush=True)
    (ROOT/"results/previews.json").write_text(json.dumps(previews,indent=2))
for mode in ["row-static","row-dynamic","tile-static","tile-dynamic"]:
    run("clustered",mode,args.threads,["--width","400","--height","225","--spp","24","--warmup","1","--diagnostics",str(ROOT/f"results/diagnostic_{mode}.csv")])
canvas=Image.new("RGB",(1320,820),"#101827")
d=ImageDraw.Draw(canvas)
try:
    title=ImageFont.truetype("DejaVuSans.ttf",30)
    small=ImageFont.truetype("DejaVuSans.ttf",18)
except OSError: title=small=ImageFont.load_default()
d.text((20,15),"CPU PATH TRACER / ACTUAL RENDERED OUTPUT",fill="white",font=title)
for scene,x,y in [("simple",20,70),("many",680,70),("clustered",20,450)]:
    canvas.paste(Image.open(ROOT/f"images/{scene}.png"),(x,y))
    d.text((x+10,y+8),scene.upper(),fill="#112033",font=small)
d.text((700,490),"C++17 + OpenMP",fill="white",font=title)
d.text((700,550),"640 x 360 | 96 samples / pixel",fill="#b6c5dc",font=small)
d.text((700,585),"Diffuse, metal, glass | BVH",fill="#b6c5dc",font=small)
d.text((700,620),"Identical sampling across thread schedules",fill="#b6c5dc",font=small)
d.text((700,665),"Preview quality differs from benchmark settings.",fill="#b6c5dc",font=small)
canvas.save(ROOT/"images/render_gallery.png")
print("extra measurements and preview gallery complete")
