#!/usr/bin/env python3
"""Compare actual float64 pixel bytes, not just display images or checksums."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import math

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', default='results/proposal/correctness.json')
options = parser.parse_args()
env = dict(os.environ, OMP_DYNAMIC="FALSE", OMP_PROC_BIND="close", OMP_PLACES="cores")
if os.uname().sysname == "Darwin":
    env["OMP_PROC_BIND"] = "FALSE"
    env.pop("OMP_PLACES", None)
available = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
threads = [n for n in [1, 2, 4, 8] if n <= available]
cases = 0
records = []
with tempfile.TemporaryDirectory() as folder:
    target = Path(folder) / "pixels.f64"
    for scene in ["room", "uneven", "bunny", "bunny-mixed"]:
        base = [str(ROOT / "raytrace"), "--scene", scene, "--width", "67", "--height", "39", "--spp", "5", "--depth", "9", "--raw", str(target)]
        def run(mode, n, tile=16):
            p = subprocess.run(base + ["--mode", mode, "--threads", str(n), "--tile", str(tile)], capture_output=True, text=True, env=env, check=True)
            row = json.loads(p.stdout)
            assert row["actual_threads"] == (1 if mode == "serial" else n)
            return target.read_bytes(), row
        expected, serial = run("serial", 1)
        values = struct.unpack("=" + "d"*(len(expected)//8), expected)
        assert len(values) == 67*39*3 and all(math.isfinite(v) and v >= 0 for v in values)
        assert max(values) > 0 and max(values)-min(values) > .1
        for mode in ["row-static", "row-dynamic", "tile-static", "tile-dynamic"]:
            for n in threads:
                for tile in ([1, 16, 128] if mode.startswith("tile") else [16]):
                    actual, row = run(mode, n, tile)
                    assert actual == expected, f"Pixel mismatch: {scene} {mode} {n} {tile}"
                    cases += 1
                    records.append(dict(scene=scene, mode=mode, threads=n, tile=tile, hash=row["hash"], exact_float64_match=True))
    # One pixel, uneven boundaries, more threads than tasks.
    for w, h in [(1, 1), (1, 17), (19, 1)]:
        args = [str(ROOT / "raytrace"), "--width", str(w), "--height", str(h), "--spp", "2", "--raw", str(target)]
        subprocess.run(args, capture_output=True, check=True, env=env)
        expected = target.read_bytes()
        subprocess.run(args + ["--mode", "tile-dynamic", "--threads", str(max(threads)), "--tile", "16"], capture_output=True, check=True, env=env)
        assert target.read_bytes() == expected
        cases += 1
    for invalid in [["--width", "0"], ["--threads", "-1"], ["--mode", "bad"], ["--scene", "bad"], ["--tile"], ["--spp", "3abc"]]:
        p = subprocess.run([str(ROOT / "raytrace")] + invalid, capture_output=True, env=env)
        assert p.returncode != 0
    # Distinct seeds must actually affect stochastic sampling.
    a = subprocess.run([str(ROOT / "raytrace"), "--width", "20", "--height", "10", "--spp", "2", "--seed", "1"], capture_output=True, text=True, check=True)
    b = subprocess.run([str(ROOT / "raytrace"), "--width", "20", "--height", "10", "--spp", "2", "--seed", "2"], capture_output=True, text=True, check=True)
    assert json.loads(a.stdout)["hash"] != json.loads(b.stdout)["hash"]
result = dict(passed=True, parallel_image_comparisons=cases, invalid_cli_cases=6, checked_threads=threads, records=records)
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / options.output).parent.mkdir(parents=True, exist_ok=True)
(ROOT / options.output).write_text(json.dumps(result, indent=2))
print(f"PASS: {cases} exact float64 image comparisons; 6 invalid CLI cases; independent seeds")
