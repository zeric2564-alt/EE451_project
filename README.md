# EE451 · Multicore CPU Path Tracing

Implementation of **EE451_Proposal.pdf**, including the required 69,451-triangle Stanford Bunny, room area light, uneven-material scene, five execution modes, independent spatial diagnostics, controlled experiments, final report and local web demo.

- [Proposal requirement map](PROPOSAL_CHECKLIST.md)
- [Final report](report/proposal/report.html) — self-contained HTML, actual retained measurements
- [Presentation](report/proposal/presentation.html) — offline HTML slides, arrow keys to navigate
- [Raw results and hardware](results/proposal/)
- [中文说明](README_CN.md)

## Build and run

C++17, OpenMP and Make are required. Linux: GCC with libgomp. macOS: Homebrew GCC (`brew install gcc` if missing); the Makefile selects a Homebrew `g++-*`, because Apple's `g++` is Clang without bundled OpenMP. Override with `make CXX=/path/to/compiler` when needed. Run commands from the repository root.

```sh
make -j2
make test
./raytrace --scene bunny --mode tile-dynamic --threads 8 \
  --width 512 --height 512 --spp 32 --depth 10 \
  --output bunny.png --timing timing.csv
python3 web/server.py
# Open http://127.0.0.1:8000
```

The CLI and web server use only standard libraries plus OpenMP. The packaged Bunny OBJ needs no download. See [asset provenance and conversion](assets/README.md). Rebuild the executable on your machine; binaries are not tracked.

For analysis and PNG integration tests:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tests/test_proposal.py
.venv/bin/python tests/test_web.py
```

## Rendering and diagnostics

Scenes: `room`, `uneven`, `bunny`, and supplementary `bunny-mixed`. Legacy `simple`, `many`, `clustered` scenes remain available. All modes share the same sphere/triangle intersection, median-split BVH, deterministic sampling and diffuse/metal/glass/emissive material rules. Triangle shading uses flat geometric normals. Scene generation and BVH construction are serial. The room uses emissive triangles with random-walk light gathering and no sky; it can be noisy without explicit next-event sampling.

Modes: `serial`, `row-static`, `row-dynamic`, `tile-static`, `tile-dynamic`. Static uses contiguous worksharing. Dynamic uses `--chunk` rows/tiles per claim (default 1). `--tile` is the scheduling tile side. All sample streams are keyed by global `--seed`, pixel and sample index; workers write disjoint pixels.

```sh
./raytrace --scene bunny --mode tile-dynamic --threads 8 \
  --width 512 --height 512 --spp 32 --tile 16 \
  --regions regions.csv --diagnostics threads.csv
```

`--regions` enables worker-private counters aggregated into fixed **32×32 measurement regions**, irrespective of scheduling tile size. Metrics: traced ray segments, successful surface-interaction depth sum, visited BVH nodes (including rejected boxes) and triangle intersection attempts. `--diagnostics` records per-worker task counts, pixels, summed task duration and last-task finish time. These instrumented runs are separate from performance measurements. The report calculates LI=max(busy)/mean(busy)-1 and conditional P90/P10, max/mean or no-ratio for zero regional data.

`--raw image.f64` writes native float64 RGB for exact comparisons. `--output image.png` writes RGB8 PNG; other extensions retain legacy binary PPM behavior. PNG uses standards-compliant uncompressed DEFLATE, so output cost is specific to this encoder. `--mesh file.obj` selects a triangulated OBJ input for the Bunny scenes; positive/negative vertex references and slash-separated face tokens are supported. Polygon faces are fan-triangulated. `--help` lists all arguments.

## Timing boundaries

- `loading_s`: scene generation / OBJ parsing and normalization.
- `bvh_s`: serial BVH construction; `setup_s` also includes image allocation.
- `render_s`: pixel loop / OpenMP region, including launch and synchronization. Per-render camera metadata, counter allocation and post-render counter reduction are outside it.
- `png_s`: RGB conversion, encoding and PNG write. `output_s` also covers any raw/PPM output.
- `end_to_end_s`: cumulative in-program time since startup, including warmup and previous repeats if requested, but excluding final JSON/CSV printing and process launch/exit.
- Python `process_wall_s`: full child-process elapsed time. In warmed experiments it includes **two renders**; only `cold.csv` measures a single fresh-process frame including PNG output.

`--repeats` prints one JSON/CSV row per render and overwrites image/diagnostic paths with the last frame. Expensive counters are disabled unless explicitly requested.

## Reproduce the study

```sh
python3 benchmarks/proposal.py --stage all
.venv/bin/python benchmarks/report_proposal.py
```

The runner is resumable and skips already-recorded configuration/round keys. It refuses to append after the executable hash changes. To perform a fresh reproduction, first move `results/proposal` to a named archive, recreate that directory, and record your hardware in `hardware.json`; do not mix machines or binaries in one dataset. Metadata records the actual compiler/runtime, environment and hashes. The report supplied here represents the recorded Apple M3 run. Its default full-study validation expects 1/2/4/8 workers and the documented configuration counts; adapt analysis if intentionally running a reduced study on smaller hardware.

Stages run **sequentially**, never concurrent timing workloads:

| Stage | Configurations and retained measurements |
|---|---|
| main | Three scenes; serial + four modes × 1/2/4/8 workers; five rounds = 255 |
| tiles | Three scenes; static/dynamic × 8/16/32/64 tile sides; five rounds = 120 |
| quality | Five selected scene/resolution/spp combinations; serial and 8-worker tile-dynamic; five rounds = 50 |
| cold | Three scenes; serial and 8-worker tile-dynamic; no warmup; five rounds = 30 |
| diagnostics | Three scenes plus mixed Bunny; four modes; independent region and worker profiles = 16 |

Main and tile experiments use 512² / 32 spp / depth 10. Quality selections: room 512²/64 and 1024²/64; uneven 512²/128; Bunny 1024²/32 and 1024²/128. They cover the proposal's selected workload settings without claiming a full quality-grid study. Every timed configuration gets a full warmup and five measured samples except intentionally un-warmed cold measurements. Configuration order is randomized within each round with seed 451. All hash comparisons use matching scene, dimensions, spp, depth and seed.

Native M3 results are affected by heterogeneous cores, OS-managed affinity and desktop activity. Speedup is measured against this same BVH-equipped serial renderer, not a production rendering library. Five observations and min–max ranges do not establish statistical significance. See the report for cases where dynamic scheduling loses.

## Verification and historical results

`make test` runs analytic geometry, 52,000 BVH/linear comparisons and exact raw-image comparisons. `tests/test_proposal.py` checks schedule-independent region counts, PNG decoding/PPM equivalence, timing CSV and malformed meshes. `tests/test_web.py` checks the real HTTP job lifecycle and input rejection. Actual outcomes are retained in `results/proposal/validation.json` and logs.

`make sanitize` requests AddressSanitizer/UBSan where the selected compiler supports them. Do not reuse the old Linux sanitizer log as proof about the new code or your platform.

The original `results/*.csv`, `report/results.html`, `images/` and old benchmark scripts concern the earlier sphere-only experiment. They are preserved for provenance and are **not the final proposal results**. Original README content is archived under `report/legacy_README*.md`. The old SHA256SUMS file is likewise historical; `scripts/package.py` produces a new checked handoff archive.

AI assistance was used for implementation and automation. Team members should understand and review the code and follow course attribution requirements. See the final report and assets README for references and dataset terms.
