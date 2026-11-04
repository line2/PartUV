#!/usr/bin/env python3
"""Render a UV layout PNG + report basic UV stats from an OBJ with UVs."""
import argparse
import json
import os

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection


def uv_islands(mesh):
    """Connected components in UV space (faces joined when they share matching UVs on an edge)."""
    uv = np.asarray(mesh.visual.uv, dtype=np.float64)
    faces = np.asarray(mesh.faces)
    # map (vertex, rounded uv) -> id
    key = np.round(uv, 6)
    order = np.lexsort((key[:, 1], key[:, 0]))
    uniq, inv = np.unique(key[order], axis=0, return_inverse=True)
    # map back to original loop order
    uv_id = np.empty(len(uv), dtype=np.int64)
    uv_id[order] = inv
    # edge -> set of uv_id pairs
    edges = {}
    for tri in faces:
        for i in range(3):
            a, b = tri[i], tri[(i + 1) % 3]
            edges.setdefault((a, b), set()).add(int(uv_id[a]))
            edges.setdefault((b, a), set()).add(int(uv_id[b]))
    parent = list(range(len(uniq)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), ids in edges.items():
        ids = list(ids)
        for i in range(1, len(ids)):
            ra, rb = find(ids[0]), find(ids[i])
            if ra != rb:
                parent[ra] = rb
    roots = {find(i) for i in range(len(uniq))}
    return len(roots), uv_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    mesh = trimesh.load(args.obj, process=False, force="mesh")
    uv = np.asarray(mesh.visual.uv, dtype=np.float64)
    faces = np.asarray(mesh.faces)
    n_islands, uv_id = uv_islands(mesh)
    face_uv = uv[faces]
    tri_area = 0.5 * np.abs(
        (face_uv[:, 1, 0] - face_uv[:, 0, 0]) * (face_uv[:, 2, 1] - face_uv[:, 0, 1])
        - (face_uv[:, 2, 0] - face_uv[:, 0, 0]) * (face_uv[:, 1, 1] - face_uv[:, 0, 1])
    )
    stats = {
        "obj": os.path.abspath(args.obj),
        "faces": int(len(faces)),
        "uv_islands": int(n_islands),
        "uv_area_sum": float(tri_area.sum()),
        "uv_bbox": [float(uv[:, 0].min()), float(uv[:, 1].min()),
                    float(uv[:, 0].max()), float(uv[:, 1].max())],
        "uv_bbox_fill": float((uv[:, 0].max() - uv[:, 0].min()) * (uv[:, 1].max() - uv[:, 1].min())),
    }
    print(json.dumps(stats, indent=2))

    segs = np.concatenate([
        np.stack([face_uv[:, 0], face_uv[:, 1]], axis=1),
        np.stack([face_uv[:, 1], face_uv[:, 2]], axis=1),
        np.stack([face_uv[:, 2], face_uv[:, 0]], axis=1),
    ])
    fig, ax = plt.subplots(figsize=(10, 10), dpi=args.dpi)
    ax.set_facecolor("black")
    lc = LineCollection(segs, linewidths=0.12, colors="white", alpha=0.55, rasterized=True)
    ax.add_collection(lc)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    title = args.title or os.path.basename(args.obj)
    ax.set_title(f"{title}   islands={n_islands}  uv_area={tri_area.sum():.4f}", color="white", fontsize=10)
    fig.patch.set_facecolor("black")
    out = args.out if args.out.lower().endswith(".png") else os.path.join(args.out, "uv_layout.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    fig.savefig(out, facecolor="black", bbox_inches="tight")
    print("wrote", out)
    stats_path = os.path.splitext(out)[0] + "_stats.json"
    with open(stats_path, "w") as fh:
        json.dump(stats, fh, indent=2)


if __name__ == "__main__":
    main()