# tools/ — PartUV harness

Scripts used to build, run, profile, verify and texture-bake PartUV during the
performance and UV-quality work documented in
[`docs/PERFORMANCE.md`](../docs/PERFORMANCE.md) and
[`docs/UV_QUALITY.md`](../docs/UV_QUALITY.md).

They were written ad hoc against two 500k-face models and then made
path-portable; treat them as **reference recipes**, not a polished CLI.

## Environment

| variable | default | used for |
|---|---|---|
| `PARTUV_WORK` | `$HOME/partuv_work` | parent dir holding the repo, the venv and `out/` |
| `PARTUV_REPO` | `$PARTUV_WORK/PartUV` | this checkout |
| `BAKE_WORK` | *(required by bake/uv scripts)* | scratch dir for OBJ/PNG hand-off between WSL and Windows |
| `BLENDER_BIN` | *(required by bake scripts)* | Blender executable |
| `PARTUV_PROF` | unset | set to a path to dump the in-process profile |
| `PARTUV_UNWRAP_CACHE` | on | `0` disables the unwrap memo |
| `PARTUV_PROXY_DUMP` | unset | directory for proxy OBJ dumps (with `PARTUV_PROXY_DUMP_MAX`) |

Python scripts expect the venv that `partuv` is installed into, e.g.
`$PARTUV_WORK/venv/bin/python`.

## Layout

```
build/    cmake_build.sh install_mod.sh fetch_deps.sh build_yamlcpp.sh
run/      run_core.py partuv_run.py partuv_baseline.py partuv_weld.py ...
bench/    crash_test.sh proxy_sweep.sh cluster_thr_sweep.sh thread_sweep.sh ...
profile/  parse_prof.py
uv/       density audit, chart plots, packing metrics, proxy quality, parameterisation bench
bake/     pack_uv_obj.py bake_partuv_result.sh + texture_transfer/ addon
```

### build/

| script | what it does |
|---|---|
| `cmake_build.sh` | out-of-tree cmake into `pybuild/`, log to `cmake_build.log` |
| `install_mod.sh` | copies the built `_core*.so` into site-packages |
| `fetch_deps.sh` | pulls the vendored deps (eigen / libigl / json / stb) |
| `build_yamlcpp.sh` | builds yaml-cpp into `$HOME/.local` (needed once) |

> Do **not** run a benchmark while `install_mod.sh` is copying: it overwrites the
> `.so` a running process has mapped.

### run/

| script | what it does |
|---|---|
| `run_core.py` | the fast path: loads mesh + tree, calls `pipeline_numpy`, prints `[done] time / RSS / parts / distortion`. Args: `mesh tree.bin out_dir threshold [config]` |
| `partuv_run.py` | full pipeline including PartField preprocessing |
| `partuv_baseline.py` | minimal single-run baseline for A/B timings |

### bench/ and profile/

Sweeps used to pick the defaults in `config/config.yaml` (proxy backend, proxy face
threshold, OpenMP thread count, recursion depth), a crash/determinism loop
(`crash_test.sh` — N runs must give the same md5), and `parse_prof.py` which turns a
`PARTUV_PROF` dump into a sorted table.

### uv/

| script | what it does |
|---|---|
| `partuv_uv_audit.py` | per-face/per-chart distortion, density, folds, seams |
| `uv_compare.py` | chart-level comparison between two results |
| `proxy_quality.py` | triangle quality + area fidelity of dumped proxies vs their charts |
| `pack_coverage_trials.py` / `pack_margin_curve.py` | coverage vs UV margin (runs in Blender) |
| `bench_unwrap_methods.py` | ABF++ vs `igl_lscm` / `igl_harmonic*` / `igl_arap` / `igl_slim` on real charts, via `_core.bench_flatten` |
| `summarize_bench.py` | clean summary table from that benchmark's JSON |
| `make_summary_chart.py` | the three-panel figure in `docs/img/` |

### bake/

```bash
# 1. pack the UV islands (PartUV emits an unpacked layout -- see docs/UV_QUALITY.md)
blender -b --factory-startup --python tools/bake/pack_to_obj.py -- \
    'C:\in.obj' 'C:\out.obj' 4 4096

# 2. bake BaseColor / Roughness / Metallic, then render three views
blender -b --factory-startup --python tools/bake/bake_and_render.py -- \
    'C:\out.obj' 'C:\source.obj' 'C:\bake_dir' 4096
```

`pack_stats.py` reports islands + coverage for one OBJ; `pack_margin_curve.py` sweeps
several margins in one session; `render_views.py` / `render_face.py` render a baked OBJ.

## Caveats

* **Blender is a Windows binary here**: it cannot open `\\wsl.localhost\...` paths, so
  OBJ/script paths passed to it must be `C:\` paths staged on the Windows side.
* `partuv_run.py` needs the PartField checkpoint and a CUDA device; `run_core.py`
  does not (it reuses a precomputed `tree.bin`).
* Scripts under `bench/` rewrite `config/config.yaml`; `make_default.sh` restores it.
* Paths inside `out/` are examples from the original runs; most scripts take the
  real paths as arguments.