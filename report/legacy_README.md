# EE451: OpenMP Parallel CPU Ray Tracer

A complete offline rendering application and controlled parallel-performance experiment.
The same C++17 path-tracing kernel runs serially, by scanline, or by image tile.
This is an **application implementation and evaluation** project, not a claim of a new rendering algorithm or a faster-than-state-of-the-art scheduler.

## Quick start

Requires a C++17 compiler with OpenMP, Make, and Python 3. The renderer and correctness tests have no third-party runtime dependencies other than OpenMP.
The supplied Makefile was tested with GCC 13.3.0 on Linux. On Windows, use a Linux/WSL environment or adapt the build to an OpenMP-enabled compiler. Apple Clang alone may require a separately installed OpenMP runtime.

```bash
make -j2
make test
./raytrace --scene many --mode tile-dynamic --threads 4 \
  --width 640 --height 360 --spp 64 --depth 10 --tile 16 --output render.ppm
```

PPM is a standard uncompressed image format. To convert to PNG with Pillow:

```bash
python3 -c "from PIL import Image; Image.open('render.ppm').save('render.png')"
```

For charts and the self-contained HTML report, install `requirements.txt` in your preferred Python environment:

```bash
python3 -m pip install -r requirements.txt
python3 benchmarks/run_benchmarks.py --width 400 --height 225 --spp 24 --repeats 5
python3 benchmarks/run_benchmarks.py --width 400 --height 225 --spp 24 \
  --repeats 5 --sweep --output results/sweep.csv
python3 benchmarks/run_extra.py
python3 benchmarks/analyze.py
```

Choose `--threads 1 2 4` if fewer than 8 CPUs are available. The main benchmark rejects a run if OpenMP does not supply the requested number of workers. Inspect both CPU affinity and container CPU quota; visible CPUs alone do not guarantee equivalent compute capacity. `run_extra.py --threads N` controls its cold-run and preview worker count.

## Implementation

- Three reproducible built-in scenes: `simple` (5 spheres), `many` (223 spheres), and `clustered` (110 spheres). All include a ground sphere.
- Pinhole camera, diffuse/rough-metal/dielectric materials, stochastic scattering, sky illumination, bounded path depth, gamma-2 display conversion.
- A median-split binary BVH, with up to four spheres per leaf, accelerates intersection in **every** version, including the serial reference. BVH construction is serial and measured as setup.
- Every pixel/sample has a deterministic SplitMix64 stream keyed by global seed, pixel index, and sample index. Streams do not depend on worker identity or scheduling. Each pixel sums samples in a fixed order.
- Each task owns a disjoint region of the image. Scene/BVH data are read-only during rendering, and no shared RNG or pixel lock is used. Pixels on tile boundaries are clipped correctly.
- Parallel versions run a single OpenMP region with a worksharing loop. The same pixel function is called by all modes; only the row/tile task mapping and schedule change.
- `serial` uses an ordinary loop (not a one-thread OpenMP loop). `row-static` and `tile-static` use contiguous static worksharing. `row-dynamic` and `tile-dynamic` use dynamic worksharing; `--chunk` specifies how many rows/tiles are claimed at once. The main experiment fixes tiles at 16×16 and dynamic chunk size at 1 before measuring; it does not select a winning tile size after the fact.

## CLI

Run `./raytrace --help` for all arguments. Standard output contains one JSON record per measured render. Standard error reports file-writing and total in-program time.

| Option | Meaning |
|---|---|
| `--scene simple\|many\|clustered` | Deterministic built-in geometry |
| `--mode serial\|row-static\|row-dynamic\|tile-static\|tile-dynamic` | Execution variant |
| `--width`, `--height` | Output resolution |
| `--spp` | Samples per pixel; identical across compared versions |
| `--depth` | Maximum path depth; identical across compared versions |
| `--threads` | Requested OpenMP workers; serial always uses one |
| `--tile` | Square tile side length in pixels |
| `--chunk` | Dynamic scheduling chunk measured in rows/tiles |
| `--seed` | Global deterministic sampling seed |
| `--warmup 0\|1` | Optional unmeasured complete render |
| `--repeats` | Measured rerenders of the already-built scene |
| `--output` | Optional binary PPM image |
| `--raw` | Optional native float64 RGB triples, for exact comparisons |
| `--diagnostics` | Per-thread CSV; enables instrumentation, excluded from main timing runs |

`render_s` includes the parallel-region launch, worksharing/synchronization, and all pixel computations, but excludes scene/BVH setup, per-call camera/task metadata and statistics-buffer initialization, image hashing, and file output. The timer starts immediately before the task loop or OpenMP region. `setup_s` includes scene/BVH construction and image allocation. `setup_plus_render_s` adds these two stages and is **not** full process end-to-end time. With repeated renders, adding setup represents a fresh-setup-equivalent cost, not a repeated actual setup.

The main runner uses one full warmup per process and one measured render. `process_wall_s` there includes warmup and subprocess overhead and must **not** be used as one-render end-to-end time. `cold.csv`, produced by `run_extra.py`, separately measures fresh-process wall time without warmup, including image output and process overhead.

## Correctness and validation

`tests/test_core.cpp` checks analytic sphere hits/misses/inside hits, axis-parallel bounding-box rays, empty scenes, and 30,000 random BVH intersections against independent linear sphere traversal.

`tests/run_correctness.py` compares actual float64 output bytes across all four parallel modes, supported thread counts, odd image dimensions, tile sizes 1/16/128, and narrow images. It checks finite nonnegative pixels, argument rejection, and that different seeds produce different images. This proves deterministic equivalence for tested inputs, not physical accuracy against an external production renderer.

```bash
make sanitize
```

On restricted containers where LeakSanitizer cannot inspect `/proc`, use `ASAN_OPTIONS=detect_leaks=0 make sanitize`. That disables leak detection only; address and undefined-behavior checking remain active. This environment required that setting. A thread race sanitizer was not run; disjoint output ownership and schedule-invariant byte comparisons support, but do not formally prove, race freedom.

## Experimental design

- Main comparison: 3 scenes × (serial + 4 parallel modes × 4 thread counts) × 5 rounds = 255 measured renders; each has a full warmup.
- Resolution 400×225, 24 samples/pixel, maximum depth 10, global seed 451.
- Configuration order is shuffled within each complete round with seed 451. All image hashes must agree within each scene.
- Same executable and `-O3 -std=c++17 -fopenmp`, without `-ffast-math` or architecture-specific flags.
- Environment: `OMP_DYNAMIC=FALSE`, `OMP_PROC_BIND=close`, `OMP_PLACES=cores`, `OMP_WAIT_POLICY=PASSIVE`.
- Report medians and min–max spread; speedup = median serial render time / median parallel render time; efficiency = speedup / actual workers. Spread is not a confidence interval.
- Separate tile/chunk sensitivity experiment; all configurations are retained, with no claim that the best observed choice generalizes.
- Thread diagnostics are separate instrumented renders; `active_s` sums task processing times, while `finish_s` is relative to rendering start and includes waiting/scheduling effects. These are not the same metric. Diagnose scheduling patterns cautiously.
- Cold process measurements include image output to temporary local storage; filesystem caching and virtualization still affect them. They are not cold-hardware-cache measurements.

## Files and reproduction

```text
src/core.hpp               Geometry, BVH, sampling, scenes, shading
src/main.cpp               CLI, task mapping, OpenMP, timing, output
tests/                    Analytic and image-equivalence tests
benchmarks/               Measurement, sensitivity, diagnostics, analysis
results/raw.csv           Every main measured configuration
results/sweep.csv         Every sensitivity measurement
results/cold.csv          No-warmup fresh-process measurements
results/*.metadata.json   Environment, arguments, quota, timestamps
results/correctness.json  Exact pixel-comparison results
results/sanitizers.log    Actual sanitizer run output
results/summary.csv       Aggregated medians, spread, speedup, efficiency
images/                   Actual rendered PNG examples
report/                   Self-contained HTML report and charts
```

The project archive excludes platform-specific binaries; rebuild with `make`. Scene generation requires no downloads. Examples are actual program output, not generated illustrations. Raw CSVs are the authority for all reported timings.

## Scope and limits

This is a small educational offline path tracer: no GUI, external mesh loader, textures, explicit area-light sampling, denoiser, GPU path, or MPI. Fixed-depth truncation and the simple material model limit rendering realism. Parallel speedup over this fair serial implementation does not imply a new algorithm or superiority over professional renderers. Results from one virtualized machine are evidence of feasibility, not a guarantee for a user's computer or a course grade.

For a three-person team: one member can own rendering/BVH/correctness, one task mapping/OpenMP, and one experiments/analysis; all should review and understand the full project. Code and experiment automation here were produced with AI assistance; follow course attribution and permitted-use rules.

## References

Implementation written for this project; standard rendering and parallelization ideas are established:

1. Peter Shirley, Trevor David Black, Steve Hollasch, *Ray Tracing in One Weekend*. https://raytracing.github.io/books/RayTracingInOneWeekend.html
2. Same authors, *Ray Tracing: The Next Week* (BVH concepts). https://raytracing.github.io/books/RayTracingTheNextWeek.html
3. Pharr et al., *Physically Based Rendering*, Parallelization of pbrt. https://pbr-book.org/3ed-2018/Introduction/Parallelization_of_pbrt
4. Pharr et al., *Physically Based Rendering*, System Overview (image tiles). https://pbr-book.org/3ed-2018/Introduction/pbrt_System_Overview

These references explain the concepts; no claim of original invention is made.
