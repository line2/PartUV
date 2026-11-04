# tools/ — PartUV harness

Scripts used to build, run, profile, verify and texture-bake PartUV during the
performance work documented in [`docs/PERFORMANCE.md`](../docs/PERFORMANCE.md).

They were written ad hoc against two 500k-face models and then made
path-portable; treat them as **reference recipes**, not a polished CLI.

## Environment

| variable | default | used for |
|---|---|---|
| `PARTUV_WORK` | `$HOME/partuv_work` | parent dir holding the repo, the venv and `out/` |
| `PARTUV_REPO` | `$PARTUV_WORK/PartUV` | this checkout |
| `BAKE_WORK` | *(required by bake scripts)* | scratch dir for OBJ/PNG hand-off between WSL and Windows |
| `BLENDER_BIN` | *(required by bake scripts)* | Blender executable |
| `PARTUV_PROF` | unset | set to a path to dump the in-process profile |

Python scripts expect the venv that `partuv` is installed into, e.g.
`$PARTUV_WORK/venv/bin/python`.

## Layout

```
build/    cmake_build.sh install_mod.sh fetch_deps.sh build_yamlcpp.sh
run/      run_core.py partuv_run.py partuv_baseline.py partuv_weld.py ...
bench/    crash_test.sh proxy_sweep.sh cluster_thr_sweep.sh thread_sweep.sh ...
profile/  parse_prof.py
uv/       partuv_uv_audit.py uv_compare.py uv_plot/pack metrics
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
> `.so` a running process has mapped, which shows up as a bogus crash.

### run/

| script | what it does |
|---|---|
| `run_core.py` | the fast path: loads mesh + tree, calls `pipeline_numpy`, prints `[done] time / RSS / parts / distortion`. Args: `mesh tree.bin out_dir threshold [config]` |
| `partuv_run.py` | full pipeline including PartField preprocessing |
| `partuv_baseline.py` | minimal single-run baseline for A/B timings |
| `partuv_weld.py` / `partuv_decimate.py` | mesh preparation helpers |

```bash
$PARTUV_WORK/venv/bin/python tools/run/run_core.py \
    $PARTUV_WORK/out/model/model.obj \
    $PARTUV_WORK/out/model/bin/model.bin \
    $PARTUV_WORK/out/run1 1.25
```

### bench/

Sweeps that were used to pick the defaults now in `config/config.yaml`:
proxy backend (`proxy_sweep.sh`, `proxy_mode_test.sh`), proxy face threshold
(`cluster_thr_sweep.sh`), OpenMP thread count (`thread_sweep.sh`), depth
(`depth_sweep.sh`), and a crash/regression loop that records rc + wall + md5 +
part count per run (`crash_test.sh`).

`crash_test.sh` is the one that answered “is this deterministic”: N runs of the
same binary must give the same md5.

### profile/

`parse_prof.py` turns a `PARTUV_PROF` dump into a sorted table:

```
block                total_s   calls    ms/call     work
abf.angles            115.232   18135     6.3541        0
overlap.cgal           52.360   21619     2.4219 19861131
```

Nested scopes are meaningful: `node.helper` contains `abf.total`, which contains
`abf.angles` / `abf.lscm` / `abf.build`.

### uv/

Quality checks for the generated atlas: per-face density distortion (`p50/p95/p99`,
share of faces above 1.25), flipped faces, chart count (`uv_compare.py`), chart
plots (`partuv_uvplot.py`), packing metrics (`partuv_pack_metrics.py`), and the
packing-margin ↔ coverage sweep (`pack_coverage_trials.py`, runs in Blender).

### bake/

Texture transfer from the original textured asset onto PartUV's layout.

```bash
# 1. pack the UV islands (PartUV emits an unpacked layout -- see PERFORMANCE.md)
blender -b --factory-startup --python tools/bake/pack_uv_obj.py -- 0.004

# 2. bake BaseColor / Roughness / Metallic
tools/bake/bake_partuv_result.sh target_packed.obj source_textured.obj out_dir 4096
```

`texture_transfer/` is the addon package behind `blender_texture_transfer.py`;
`partuv_transfer_uv.py` + `partuv_bake_color.py` are the earlier KD-tree/EMIT
route, kept for reference (it produces correct colour but leaves seam lines where
the packaging addon does not).

## Caveats

* Paths inside `out/` are examples from the original runs; most scripts take the
  real paths as arguments.
* `partuv_run.py` needs the PartField checkpoint and a CUDA device; `run_core.py`
  does not (it reuses a precomputed `tree.bin`).
* Scripts under `bench/` rewrite `config/config.yaml`; `make_default.sh` restores it.