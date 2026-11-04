#!/usr/bin/env python3
"""Compare UV quality between two pipeline outputs (or audit a single one).

usage: uv_compare.py <a.obj> [b.obj]

Metric (same definition as the earlier audit):
  rho_f = (A_uv_f / A_3d_f) / (sum A_uv / sum A_3d)
  d_f   = max(rho_f, 1/rho_f)                 # 1.0 == perfectly uniform density
Reports p50/p95/p99/max, the share of faces above the 1.25 threshold,
flipped-UV-face count and chart count (islands of the UV-edge graph).
"""
import sys

import numpy as np
import trimesh


def load(path):
    m = trimesh.load(path, process=False, force="mesh")
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    uv = None
    if hasattr(m.visual, "uv") and m.visual.uv is not None:
        uv = np.asarray(m.visual.uv, dtype=np.float64)
    return V, F, uv


def face_areas(pts, F):
    a = pts[F[:, 0]]
    b = pts[F[:, 1]]
    c = pts[F[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1), (a, b, c)


def stats(name, V, F, uv):
    A3, _ = face_areas(V, F)
    A2, _ = face_areas(uv, F)

    ok = (A3 > 0) & (A2 > 0)
    rho = np.full(len(F), np.nan)
    rho[ok] = (A2[ok] / A3[ok]) / (A2[ok].sum() / A3[ok].sum())
    d = np.maximum(rho, 1.0 / rho)

    # flipped UV faces: signed UV area vs winding
    a, b, c = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    signed = 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                    - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    flipped = int((signed < 0).sum())

    # chart count: union-find over UV-space edges
    key = {}
    parent = list(range(len(uv)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    used = {}
    for f in F:
        for i in range(3):
            v0, v1 = int(f[i]), int(f[(i + 1) % 3])
            used.setdefault((min(v0, v1), max(v0, v1)), 0)
            used[(min(v0, v1), max(v0, v1))] += 1
    for (v0, v1) in used:
        union(v0, v1)
    charts = len({find(i) for i in range(len(uv))})

    q = np.nanpercentile(d, [50, 95, 99])
    print(f"--- {name}")
    print(f"    faces {len(F):>7}  verts {len(V):>7}  charts {charts:>6}")
    print(f"    d  p50 {q[0]:.3f}   p95 {q[1]:.3f}   p99 {q[2]:.3f}   max {np.nanmax(d):.3f}")
    print(f"    faces with d>1.25: {100.0 * np.nanmean(d > 1.25):5.2f}%   "
          f"area share: {100.0 * A3[ok][d[ok] > 1.25].sum() / A3[ok].sum():5.2f}%")
    print(f"    flipped UV faces: {flipped}")
    return d


def main():
    a = sys.argv[1]
    V, F, uv = load(a)
    if uv is None:
        print(f"{a}: no UVs found")
        return
    da = stats(a, V, F, uv)

    if len(sys.argv) > 2:
        b = sys.argv[2]
        V2, F2, uv2 = load(b)
        if uv2 is None:
            print(f"{b}: no UVs found")
            return
        db = stats(b, V2, F2, uv2)
        n = min(len(da), len(db))
        if len(da) == len(db):
            print(f"\nper-face delta (b - a): p50 {np.nanmedian(db - da):+.4f}  "
                  f"p95 {np.nanpercentile(db - da, 95):+.4f}")


if __name__ == "__main__":
    main()