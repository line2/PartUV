"""trimesh in / trimesh out front end for the PartUV pipeline.

The C++ core is happy with matrices, but it wants a config *path* and a PartField tree,
and it hands back ``UVParts`` objects.  This module hides that: give it a
:class:`trimesh.Trimesh` and get a :class:`trimesh.Trimesh` with per-vertex UV coordinates.

    import partuv, trimesh
    res = partuv.unwrap(trimesh.load("model.obj"), tree="model.bin")
    res.mesh          # trimesh.Trimesh with .visual.uv
    res.parts         # one trimesh per chart group
    res.stats         # timing / distortion

Notes that matter in practice:

* UVs come back **unpacked**: each chart is normalised to 1 UV unit = 1 model unit, so
  coordinates run outside [0, 1].  Pack them with Blender's ``pack_islands`` (or
  uvpackmaster) before baking.
* Only geometry + UV are produced.  Textures on the input mesh are dropped, not rebound.
* ``ConfigManager`` and the unwrap cache are process globals in C++, so calls are
  serialised through a lock; two threads cannot run with different configs concurrently.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from . import _core

__all__ = ["unwrap", "prepare", "UnwrapResult", "UnwrapStats", "PrepareResult", "DEFAULT_CONFIG"]

# C++ globals: one pipeline at a time.
_LOCK = threading.Lock()

_CFG_CACHE: dict[str, str] = {}


# --------------------------------------------------------------------------- config
def _default_config_path() -> Path:
    """Packaged default, falling back to the source tree layout during development."""
    here = Path(__file__).resolve().parent
    for cand in (here / "data" / "default_config.yaml",
                 here.parent / "config" / "config.yaml"):
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        "no default config found; pass config=<path or dict> explicitly")


DEFAULT_CONFIG = _default_config_path()


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_config(config) -> str:
    """None -> packaged default | dict -> merged yaml (cached) | path -> as given."""
    if config is None:
        return str(DEFAULT_CONFIG)
    if isinstance(config, (str, os.PathLike)):
        p = Path(config)
        if not p.is_file():
            raise FileNotFoundError(f"config file not found: {p}")
        return str(p)
    if isinstance(config, dict):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "passing config as a dict needs PyYAML: pip install pyyaml "
                "(or hand unwrap() a path to a yaml file)") from exc
        base = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}
        merged = _deep_merge(base, config)
        text = yaml.safe_dump(merged, sort_keys=False)
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        cached = _CFG_CACHE.get(key)
        if cached and os.path.isfile(cached):
            return cached
        path = os.path.join(tempfile.gettempdir(), f"partuv-config-{key}.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        _CFG_CACHE[key] = path
        return path
    raise TypeError(f"config must be None, a path or a dict, not {type(config)!r}")


# --------------------------------------------------------------------------- mesh io
def _as_matrices(mesh) -> tuple[np.ndarray, np.ndarray]:
    """Trimesh / Scene / (V, F) -> (float64 V, int32 F) the core can consume."""
    if isinstance(mesh, trimesh.Scene):
        if not mesh.geometry:
            raise ValueError("empty trimesh.Scene")
        # bake each geometry's transform, then merge
        verts, faces, offset = [], [], 0
        for name in mesh.graph.nodes_geometry:
            T, geom_name = mesh.graph[name]
            g = mesh.geometry[geom_name].copy()
            g.apply_transform(T)
            verts.append(np.asarray(g.vertices, dtype=np.float64))
            faces.append(np.asarray(g.faces, dtype=np.int64) + offset)
            offset += len(g.vertices)
        V = np.vstack(verts)
        F = np.vstack(faces)
    elif isinstance(mesh, trimesh.Trimesh):
        V = np.asarray(mesh.vertices, dtype=np.float64)
        F = np.asarray(mesh.faces, dtype=np.int64)
    elif isinstance(mesh, (tuple, list)) and len(mesh) == 2:
        V = np.asarray(mesh[0], dtype=np.float64)
        F = np.asarray(mesh[1], dtype=np.int64)
    else:
        raise TypeError(
            f"expected trimesh.Trimesh, trimesh.Scene or (V, F), got {type(mesh)!r}")

    if F.ndim != 2 or F.shape[1] != 3:
        raise TypeError(
            f"faces must be triangles, got shape {F.shape}; call mesh.triangulate() first")
    if V.ndim != 2 or V.shape[1] != 3:
        raise ValueError(f"vertices must be (N, 3), got {V.shape}")
    if F.size and (F.max() >= len(V) or F.min() < 0):
        raise ValueError("face indices out of range")
    if len(F) == 0:
        raise ValueError("mesh has no faces")

    # every vertex must be referenced: the core indexes V directly
    used = np.unique(F)
    if len(used) != len(V):
        remap = np.full(len(V), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        V = V[used]
        F = remap[F]

    return np.asfortranarray(V), np.ascontiguousarray(F, dtype=np.int32)


def _to_trimesh(V, F, UV) -> trimesh.Trimesh:
    """Per-vertex UV (len(UV) == len(V)) -> Trimesh, keeping indices untouched."""
    vis = trimesh.visual.texture.TextureVisuals(uv=np.asarray(UV, dtype=np.float64)[:, :2])
    return trimesh.Trimesh(vertices=np.asarray(V), faces=np.asarray(F),
                           visual=vis, process=False)


def _load_tree(tree) -> dict:
    if isinstance(tree, dict):
        return tree
    if isinstance(tree, (str, os.PathLike)):
        import struct
        with open(tree, "rb") as fh:
            n = struct.unpack("<i", fh.read(4))[0]
            arr = np.frombuffer(fh.read(12 * n), dtype="<i4").reshape(n, 3)
        return {int(i): {"left": int(l), "right": int(r)} for i, l, r in arr}
    raise TypeError(f"tree must be a dict, a .bin path or None, not {type(tree)!r}")


# --------------------------------------------------------------------------- results
@dataclass(frozen=True)
class UnwrapStats:
    seconds: float
    parts: int
    charts: int
    distortion: float
    threshold: float
    config_path: str


@dataclass
class UnwrapResult:
    mesh: trimesh.Trimesh
    parts: list = field(default_factory=list)
    hierarchy: dict = field(default_factory=dict)
    stats: UnwrapStats | None = None

    def export(self, out_dir) -> list:
        """Same layout as the CLI: final_components.obj, individual_parts/, hierarchy.json."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        written = []
        if self.parts:
            pdir = out / "individual_parts"
            pdir.mkdir(exist_ok=True)
            for i, part in enumerate(self.parts):
                p = pdir / f"part_{i}.obj"
                part.export(p, file_type="obj", include_normals=False)
                written.append(p)
        if self.hierarchy:
            hp = out / "hierarchy.json"
            hp.write_text(json.dumps(self.hierarchy), encoding="utf-8")
            written.append(hp)
        mp = out / "final_components.obj"
        self.mesh.export(mp, file_type="obj", include_normals=False)
        written.append(mp)
        return written


@dataclass
class PrepareResult:
    mesh: trimesh.Trimesh
    tree: dict
    times: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- api
def unwrap(mesh, *, tree=None, threshold: float = 1.25, config=None,
           with_parts: bool = True) -> UnwrapResult:
    """Flatten ``mesh`` into UV space.

    Parameters
    ----------
    mesh
        :class:`trimesh.Trimesh`, :class:`trimesh.Scene` (transforms are baked) or
        ``(V, F)`` arrays.  Must be triangulated.
    tree
        PartField hierarchy: the dict returned by :func:`prepare`, a ``.bin`` path, or
        ``None`` to run preprocessing (needs torch + CUDA).
    threshold
        Distortion threshold that drives chart splitting (default 1.25).
    config
        Path to a yaml, a dict of overrides on the packaged default, or ``None``.
    with_parts
        Also convert the per-part result (set ``False`` to skip the extra conversion).
    """
    V, F = _as_matrices(mesh)
    if tree is None:
        tree = prepare(mesh).tree
    tree_dict = _load_tree(tree)
    cfg = _resolve_config(config)

    t0 = time.perf_counter()
    with _LOCK:
        final_parts, individual_parts = _core.pipeline_numpy(
            V, F, tree_dict, cfg, float(threshold))
    dt = time.perf_counter() - t0

    comp = final_parts.to_components()
    out_mesh = _to_trimesh(comp.V, comp.F, comp.UV)

    parts = []
    if with_parts and individual_parts:
        parts = [_to_trimesh(c.V, c.F, c.UV)
                 for c in (p.to_components() for p in individual_parts)]

    stats = UnwrapStats(seconds=dt, parts=len(individual_parts),
                        charts=int(final_parts.num_components),
                        distortion=float(final_parts.distortion),
                        threshold=float(threshold), config_path=cfg)
    return UnwrapResult(mesh=out_mesh, parts=parts,
                        hierarchy=json.loads(final_parts.hierarchy_json), stats=stats)


def prepare(mesh, *, pf_model=None, sample_on_faces: int = 10,
            merge_epsilon: float = 1e-7, sample_batch_size: int = 100_000) -> PrepareResult:
    """Run the PartField preprocessing needed before :func:`unwrap`.

    Requires torch and a CUDA device (that is the upstream constraint, not ours).  Writes
    the mesh to a temporary OBJ because the PartField inference reads from a path.
    """
    # imported lazily: it pulls torch
    from .preprocess import preprocess as _preprocess

    V, F = _as_matrices(mesh)
    with tempfile.TemporaryDirectory(prefix="partuv-prepare-") as tmp:
        src = os.path.join(tmp, "input.obj")
        trimesh.Trimesh(vertices=V, faces=F, process=False).export(src, file_type="obj")
        fixed, _bin, tree_dict, times = _preprocess(
            src, pf_model=pf_model, output_path=os.path.join(tmp, "out"),
            save_tree_file=False, save_processed_mesh=False,
            merge_vertices_epsilon=merge_epsilon,
            sample_on_faces=sample_on_faces, sample_batch_size=sample_batch_size)
    fixed_mesh = trimesh.Trimesh(vertices=np.asarray(fixed.vertices),
                                 faces=np.asarray(fixed.faces), process=False)
    return PrepareResult(mesh=fixed_mesh, tree=tree_dict, times=times)