# Proposal acceptance map

Source of requirements: `EE451_Proposal.pdf` (four pages). The original sphere-only implementation was incomplete against this proposal. New data are isolated in `results/proposal/`; original results remain historical.

| Requirement | Implementation | Evidence |
|---|---|---|
| C++17, shared-memory CPU, OpenMP | `src/main.cpp`, `Makefile` | compiler and linked runtime in `main.metadata.json` |
| Serial, row-static/dynamic, tile-static/dynamic | one shared pixel kernel, disjoint output ownership | main.csv: 255 measurements, all hashes agree |
| Spheres, triangles, diffuse/metal/dielectric, BVH | `src/core.hpp` | analytic tests, 52,000 BVH/linear ray comparisons |
| Deterministic sample IDs | SplitMix64 keyed by seed, pixel, sample | raw float64 equivalence over all scenes/modes/workers |
| Scene A: procedural room and area light | `--scene room`; emissive ceiling rectangle, dark environment | `room.png`, room measurements |
| Scene B: uneven reflective/refractive workload | `--scene uneven` | regional work CSV and heatmaps |
| Scene C: required reconstructed Stanford Bunny | `--scene bunny`, all 69,451 triangles | packaged OBJ, source/checksums, runtime count in CSV |
| Reproducible Bunny variant, original control retained | `--scene bunny-mixed` | separate regional and thread diagnostics |
| PNG and timing/statistics CSV | native PNG encoder; `--timing`, `--regions`, `--diagnostics` | PNG decoding/equality and CSV tests |
| Hardware/cores/RAM/compiler/runtime/quota/affinity | hardware.json and per-stage metadata | Apple M3, 8 cores, 16 GiB; OS-managed affinity |
| 1, 2, 4, 8 workers | main experiment on confirmed 8-core host | actual worker count checked in every run |
| Tiles 8, 16, 32, 64 | both static and dynamic tile sensitivity | tiles.csv: 120 measurements |
| 512² and 1024²; 32/64/128 spp on selected runs | main plus five selected quality configurations | quality.csv: 50 measurements |
| Warmup and five repetitions, interleaving | randomized rounds, full warmup per process | raw per-round CSV, medians/min/max |
| Render-only latency, speedup, efficiency | primary timer covers parallel loop and synchronization | summary.csv and scaling plots |
| Separate loading, BVH, rendering, PNG, end-to-end | staged timers and fresh-process experiment | cold.csv: 30 measurements |
| Fixed 32×32 measurement regions | thread-private counters independent of task tiles | per-scene region CSVs; cross-schedule equality test |
| Rays, path-depth sum, BVH visits, triangle tests | counters only enabled with `--regions` | regional_summary.csv, four heatmaps per scene |
| P90/P10 conditional ratio and zero handling | `regional_ratio()` in report generator | recorded ratio rule and raw distributions |
| Per-thread busy time, tasks, LI | task timers, LI=max(B)/mean(B)-1 | thread CSVs and thread_summary.csv |
| Negative results, controls and limitations | computed static/dynamic comparisons; overlap disclosure | report sections 4–10 |
| Reproducible package, report, presentation | Makefile, scripts, asset instructions | report/proposal/report.html, presentation.html |
| Minimal web demonstration | loopback Python server and browser UI | create job → poll → PNG + timings + download |

## Milestone deliverables

- Day 7 content: hardware record, serial renderer, geometry tests and `first_timing.csv`.
- Day 14 content: four parallel modes, exact image comparisons, scaling results.
- Day 21 content: complete Bunny, uneven scene, sensitivity, region heatmaps and per-thread diagnostics.
- Day 30 content: repeated measurements, final report, reproducible scripts, local web demo and offline presentation.

These map the final package to planned milestones; they do not assert that historical course submissions occurred on those dates.

## Scope and limits

The web app is a local demonstration, not a cloud rendering service. The presentation is a self-contained HTML slide deck with arrow-key navigation and print styling. Optional external assets, advanced shading, GPU/MPI, full PBRT scene import and alternative acceleration backends are outside the proposal's required scope. The area light is sampled through random walks; explicit direct-light sampling was not promised. Finite-depth truncation, noise and flat triangle normals are documented. Five measurements are not a statistical guarantee. See `results/proposal/validation.json` for actual checks and sanitizer availability, rather than the old Linux sanitizer log.
