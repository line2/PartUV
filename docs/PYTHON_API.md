# Python API (trimesh in / trimesh out)

The C++ core takes matrices plus a config *path* and a PartField tree, and hands back
`UVParts` objects.  `partuv.api` wraps that: give it a `trimesh.Trimesh`, get a
`trimesh.Trimesh` with per-vertex UVs.

```python
import partuv, trimesh

mesh = trimesh.load("model.obj")
res  = partuv.unwrap(mesh, tree="model.bin", threshold=1.25)

res.mesh       # trimesh.Trimesh — same faces, new per-vertex UV
res.parts      # one trimesh per part (93 on the 500k test model)
res.hierarchy  # dict, the PartField node tree
res.stats      # seconds / parts / charts / distortion
```

## Where the tree comes from

`unwrap()` needs a part hierarchy.  Two ways:

```python
# 1. you already have it (a .bin from a previous run, or a dict)
res = partuv.unwrap(mesh, tree="model.bin")
res = partuv.unwrap(mesh, tree={"999606": {"left": 999601, "right": 999605}, ...})

# 2. let the package compute it — needs torch and a CUDA device
prep = partuv.prepare(mesh)          # partuv[preprocess] extra
res  = partuv.unwrap(prep.mesh, tree=prep.tree)
```

`prepare()` returns the repaired mesh too: PartField runs on a welded, manifold-fixed mesh,
and the tree indexes *that* mesh's faces.  Feeding the tree to `unwrap()` with a different
mesh silently produces wrong charts, so pass `prep.mesh`, not the original.

Without a tree and without a GPU, `unwrap()` raises with a message saying so.

## Config

| `config=` | meaning |
|---|---|
| `None` | the packaged `partuv/data/default_config.yaml` |
| `dict` | deep-merged over that default, materialised to a cached temp yaml |
| path | used verbatim |

```python
partuv.unwrap(mesh, tree="model.bin", config={"unwrap": {"method": "igl_arap"}})
```

Dict configs need PyYAML (a normal dependency).  Unknown keys are passed through to the
C++ loader, which ignores them.

## What comes back, and what does not

* **UVs are unpacked.** Each chart is scaled so 1 UV unit = 1 model unit, so coordinates
  run outside `[0, 1]` (measured: `u ∈ [-3.80, 33.76]`).  Pack them before baking —
  Blender `pack_islands(margin=…)` or uvpackmaster.  PartUV has never packed UVs itself.
* **Per-vertex UV.** Chart seams are represented by duplicated vertices, so
  `len(visual.uv) == len(vertices)` (249,876 → 273,235 on the test model) and one index
  works for both.
* **No texture.** Input materials/textures are dropped, not rebound to the new UVs.

## Concurrency

`ConfigManager` and the unwrap cache are process globals in C++, so `unwrap()` serialises
through a module lock.  Two threads may call it, but they cannot run with different
configs at the same time — the second one waits.

## Exporting the same layout as the CLI

```python
res.export("out/")     # final_components.obj, individual_parts/, hierarchy.json
```

## Cost on the reference model

welded 500k-face model, default config (`pamo_backend: "none"`), 8 threads:

| | time | parts | charts | distortion |
|---|---|---|---|---|
| `partuv.unwrap()` | 108–120 s | 93 | 248 | 1.2383 |

Same numbers as `tools/run/run_core.py`, which is the regression check used during
development.