#!/usr/bin/env python3
"""Transfer the original model's UVs onto a PartUV result (per-vertex), for texture baking.

PartUV normalized the mesh, so the target is restored to model coordinates first using the
same transform PartField applied ((v-c)*0.9/max_extent+0.5).

Correspondence: nearest source face centroid (KD-tree, k candidates), exact closest point on
those triangles, barycentric interpolation of the source UVs.
"""
import argparse
import json

import numpy as np
import trimesh
from scipy.spatial import cKDTree

MESH_SCALE = 0.9


def closest_on_tris(p, a, b, c):
    """Exact closest point on triangles (a,b,c) to points p, with barycentric weights.

    The closest point is either the planar projection (when it lands inside) or the closest
    point on one of the three edges, so we evaluate all four candidates and keep the nearest.
    """
    def seg(p, s0, s1):
        d = s1 - s0
        dd = np.einsum("ij,ij->i", d, d)
        t = np.einsum("ij,ij->i", p - s0, d) / np.maximum(dd, 1e-20)
        t = np.clip(t, 0.0, 1.0)
        return s0 + t[:, None] * d, t

    p_ab, t_ab = seg(p, a, b)
    p_bc, t_bc = seg(p, b, c)
    p_ca, t_ca = seg(p, c, a)

    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    safe = np.abs(denom) > 1e-20
    denom = np.where(safe, denom, 1.0)
    v = np.where(safe, vb / denom, 0.0)
    w = np.where(safe, vc / denom, 0.0)
    u = 1.0 - v - w
    p_in = u[:, None] * a + v[:, None] * b + w[:, None] * c

    cands = np.stack([p_in, p_ab, p_bc, p_ca], axis=1)          # (n, 4, 3)
    dists = np.linalg.norm(cands - p[:, None, :], axis=2)       # (n, 4)
    choice = dists.argmin(axis=1)

    n = len(p)
    idx = np.arange(n)
    best_pt = cands[idx, choice]
    bary_in = np.stack([u, v, w], axis=1)
    bary_ab = np.stack([1 - t_ab, t_ab, np.zeros(n)], axis=1)
    bary_bc = np.stack([np.zeros(n), 1 - t_bc, t_bc], axis=1)
    bary_ca = np.stack([t_ca, np.zeros(n), 1 - t_ca], axis=1)
    bary = np.stack([bary_in, bary_ab, bary_bc, bary_ca], axis=1)[idx, choice]
    return best_pt, bary, dists[idx, choice]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", required=True, help="output .npz with target per-vertex UV")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--no-transform", action="store_true",
                    help="target is already in model space (run_core.py path)")
    ap.add_argument("--shrink", type=float, default=0.12,
                    help="pull source-UV samples toward the source triangle centroid")
    args = ap.parse_args()

    src = trimesh.load(args.source, process=False, force="mesh")
    sv = np.asarray(src.vertices, dtype=np.float64)
    sf = np.asarray(src.faces, dtype=np.int64)
    suv = np.asarray(src.visual.uv, dtype=np.float64)
    print(f"[src] V={len(sv)} F={len(sf)} uv={suv.shape}")

    ref = trimesh.load(args.ref, process=False, force="mesh")
    rv = np.asarray(ref.vertices, dtype=np.float64)
    center = (rv.min(0) + rv.max(0)) * 0.5
    extent = float((rv.max(0) - rv.min(0)).max())
    scale = MESH_SCALE / extent
    print(f"[ref] center={center.round(4)} extent={extent:.4f} scale={scale:.6f}")

    tgt = trimesh.load(args.target, process=False, force="mesh")
    tv = np.asarray(tgt.vertices, dtype=np.float64)
    if not args.no_transform:
        tv = (tv - 0.5) / scale + center
    print(f"[tgt] V={len(tv)} F={len(tgt.faces)} restored bbox {tv.min(0).round(3)} .. {tv.max(0).round(3)}")

    centroids = sv[sf].mean(axis=1)
    tree = cKDTree(centroids)
    k = min(args.k, len(centroids))
    _, idx = tree.query(tv, k=k, workers=-1)
    idx = np.atleast_2d(idx)
    print(f"[knn] queried {len(tv)} verts, k={k}")

    best_d = np.full(len(tv), np.inf)
    best_uv = np.zeros((len(tv), 2))
    best_face = np.zeros(len(tv), dtype=np.int64)
    for j in range(k):
        f = sf[idx[:, j]]
        a, b, c = sv[f[:, 0]], sv[f[:, 1]], sv[f[:, 2]]
        p, bary, d = closest_on_tris(tv, a, b, c)
        ua, ub, uc = suv[f[:, 0]], suv[f[:, 1]], suv[f[:, 2]]
        uv = bary[:, 0:1] * ua + bary[:, 1:2] * ub + bary[:, 2:3] * uc
        better = d < best_d
        best_d[better] = d[better]
        best_uv[better] = uv[better]
        best_face[better] = idx[better, j]

    # Pull samples toward the source texel block's centre: sampling exactly on a source UV
    # island border hits the black gutter and leaves dark seam lines after rebaking.
    if args.shrink > 0:
        tri_uv = suv[sf[best_face]]
        centroid = tri_uv.mean(axis=1)
        best_uv = best_uv + args.shrink * (centroid - best_uv)

    missing = ~np.isfinite(best_d)
    if missing.any():
        # fall back to the nearest source vertex's UV for points that fell outside every
        # candidate triangle (thin/large source triangles)
        vtree = cKDTree(sv)
        _, vidx = vtree.query(tv[missing], k=1, workers=-1)
        best_uv[missing] = suv[vidx]
        print(f"[fallback] {int(missing.sum())} verts snapped to nearest source vertex UV")
    print(f"[uv] range {best_uv.min(0).round(3)} .. {best_uv.max(0).round(3)}")

    np.savez(args.out, uv=best_uv.astype(np.float64))
    with open(args.out + ".json", "w") as fh:
        json.dump({"median_dist": float(np.median(best_d[~missing])),
                   "p99_dist": float(np.percentile(best_d[~missing], 99)),
                   "unmatched": int(missing.sum()),
                   "center": center.tolist(), "extent": extent, "scale": scale}, fh, indent=2)
    print(f"[done] wrote {args.out}")


if __name__ == "__main__":
    main()