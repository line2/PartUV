#!/usr/bin/env python3
"""Fine-grained audit of a UV layout (per-face / per-chart / global).

Metrics
  per face : 3D area, UV area, signed area, Jacobian singular values
             -> area ratio r_f, anisotropy s1/s2, flip (signed<0), degenerate
  per chart: faces, 3D area share, distortion (PartUV definition), density,
             anisotropy p95, folding fraction (1 - |sum signed| / sum |signed|)
  global   : islands, texel density spread, seam length, overlap proxies
"""
import argparse
import json
from collections import defaultdict

import numpy as np


def load_obj(path):
    V, VT, F, FT = [], [], [], []
    with open(path, "r", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                V.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                VT.append([float(x) for x in line.split()[1:3]])
            elif line.startswith("f "):
                toks = line.split()[1:]
                vi, ti = [], []
                for t in toks:
                    parts = t.split("/")
                    vi.append(int(parts[0]) - 1)
                    ti.append(int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1)
                for k in range(1, len(vi) - 1):      # triangulate polygons
                    F.append([vi[0], vi[k], vi[k + 1]])
                    FT.append([ti[0], ti[k], ti[k + 1]])
    return (np.asarray(V, np.float64), np.asarray(VT, np.float64),
            np.asarray(F, np.int64), np.asarray(FT, np.int64))


def face_frame(P):
    """Local 2D frame of each 3D triangle -> (X, Y) coords of its 3 vertices."""
    a, b, c = P[:, 0], P[:, 1], P[:, 2]
    e1 = b - a
    e2 = c - a
    x = np.linalg.norm(e1, axis=1)
    e1u = e1 / np.maximum(x, 1e-30)[:, None]
    u = np.einsum("ij,ij->i", e2, e1u)
    v = np.sqrt(np.maximum((np.einsum("ij,ij->i", e2, e2)) - u * u, 0.0))
    return x, u, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("obj")
    ap.add_argument("--out", required=True, help="output json")
    ap.add_argument("--tag", default="")
    ap.add_argument("--npz", default=None)
    args = ap.parse_args()

    V, VT, F, FT = load_obj(args.obj)
    nF = len(F)
    print(f"[load] V={len(V)} VT={len(VT)} F={nF}")

    P = V[F]                     # (nF,3,3)
    Q = VT[FT]                   # (nF,3,2)

    # ---- areas -----------------------------------------------------------------
    a3 = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    uv_a = 0.5 * ((Q[:, 1, 0] - Q[:, 0, 0]) * (Q[:, 2, 1] - Q[:, 0, 1]) -
                  (Q[:, 2, 0] - Q[:, 0, 0]) * (Q[:, 1, 1] - Q[:, 0, 1]))
    uv_abs = np.abs(uv_a)

    # ---- Jacobian singular values ---------------------------------------------
    x, u, v = face_frame(P)
    Auv = np.stack([np.stack([Q[:, 1, 0] - Q[:, 0, 0], Q[:, 1, 1] - Q[:, 0, 1]], axis=1),
                    np.stack([Q[:, 2, 0] - Q[:, 0, 0], Q[:, 2, 1] - Q[:, 0, 1]], axis=1)], axis=2)  # (nF,2,2)
    A3 = np.zeros((nF, 2, 2))
    A3[:, 0, 0] = x
    A3[:, 0, 1] = u
    A3[:, 1, 1] = v
    det3 = np.maximum(x * v, 1e-30)
    A3inv = np.zeros_like(A3)
    A3inv[:, 0, 0] = 1.0 / np.maximum(x, 1e-30)
    A3inv[:, 0, 1] = -u / det3
    A3inv[:, 1, 1] = 1.0 / np.maximum(v, 1e-30)
    J = Auv @ A3inv
    sv = np.linalg.svd(J, compute_uv=False)
    s1, s2 = sv[:, 0], np.maximum(sv[:, 1], 1e-12)
    aniso = s1 / s2

    total3 = a3.sum()
    total_uv = uv_abs.sum()
    sliver_tol = 1e-6 * max(float(np.median(a3)), 1e-30)
    ratio = uv_abs / np.maximum(a3, sliver_tol)
    rho = ratio / (total_uv / total3)
    d = np.where(rho >= 1.0, rho, 1.0 / np.maximum(rho, 1e-30))

    collapsed = (a3 > sliver_tol) & (uv_abs <= 0)
    valid = (a3 > sliver_tol) & (uv_abs > 0)
    flipped = (uv_a < 0)

    # ---- chart connectivity (union over shared UV edges) -----------------------
    parent = np.arange(nF)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    uv_edge = defaultdict(list)
    for f in range(nF):
        a, b, c = FT[f]
        for e in ((a, b), (b, c), (c, a)):
            key = (e[0], e[1]) if e[0] < e[1] else (e[1], e[0])
            uv_edge[key].append(f)
    for faces in uv_edge.values():
        f0 = faces[0]
        for g in faces[1:]:
            union(f0, g)

    roots = np.array([find(i) for i in range(nF)])
    uniq, chart = np.unique(roots, return_inverse=True)
    nC = len(uniq)
    print(f"[charts] {nC}")

    # ---- seam length: UV-island boundary edges, measured in 3D -----------------
    # (the preprocessed mesh has vertex splits along original cracks, so a UV edge
    #  used by a single face is exactly an island boundary)
    seam = 0.0
    seam_edges = 0
    for key, faces in uv_edge.items():
        if len(faces) == 1:
            f = faces[0]
            ta, tb = key
            # find the 3D endpoints carrying these two UV corners in this face
            va = vb = -1
            for k in range(3):
                if FT[f][k] == ta:
                    va = F[f][k]
                if FT[f][k] == tb:
                    vb = F[f][k]
            if va >= 0 and vb >= 0:
                seam += float(np.linalg.norm(V[va] - V[vb]))
                seam_edges += 1

    # ---- per-chart aggregation -------------------------------------------------
    order = np.argsort(chart)
    bounds = np.searchsorted(chart[order], np.arange(nC + 1))
    charts = []
    for k in range(nC):
        idx = order[bounds[k]:bounds[k + 1]]
        f3 = a3[idx].sum()
        fuv_signed = uv_a[idx].sum()
        fuv_abs = uv_abs[idx].sum()
        charts.append({
            "faces": int(len(idx)),
            "area3d": float(f3),
            "area3d_share": float(f3 / total3),
            "distortion": float(d[idx].mean()),
            "distortion_max": float(d[idx].max()),
            "density": float(np.sqrt(fuv_abs / max(f3, 1e-30))),
            "aniso_p95": float(np.percentile(aniso[idx], 95)),
            "aniso_max": float(aniso[idx].max()),
            "folding": float(1.0 - abs(fuv_signed) / max(fuv_abs, 1e-30)),
            "flipped_faces": int(flipped[idx].sum()),
            "over_threshold_faces": int((d[idx] > 1.25).sum()),
        })
    charts.sort(key=lambda c: -c["area3d"])

    sizes = np.array([c["faces"] for c in charts])
    cdist = np.array([c["distortion"] for c in charts])
    cdens = np.array([c["density"] for c in charts])

    summary = {
        "tag": args.tag,
        "obj": args.obj,
        "faces": int(nF),
        "verts": int(len(V)),
        "charts": int(nC),
        "uv_util": float(total_uv / max(np.ptp(VT[:, 0]) * np.ptp(VT[:, 1]), 1e-30)) if len(VT) else 0.0,
        "uv_area_sum": float(total_uv),
        "uv_bbox": [float(VT[:, 0].min()), float(VT[:, 1].min()),
                    float(VT[:, 0].max()), float(VT[:, 1].max())],
        # global畸变（PartUV 同款定义，但这里按面算全分布）
        "distortion_mean": float(d[valid].mean()),
        "distortion_p50": float(np.percentile(d[valid], 50)),
        "distortion_p95": float(np.percentile(d[valid], 95)),
        "distortion_p99": float(np.percentile(d[valid], 99)),
        "distortion_max": float(d[valid].max()),
        "faces_over_1_25": int((d[valid] > 1.25).sum()),
        "faces_over_1_5": int((d[valid] > 1.5).sum()),
        "faces_over_2_0": int((d[valid] > 2.0).sum()),
        "flipped_faces": int(flipped.sum()),
        "degenerate_faces": int((uv_abs < 1e-12).sum()),
        "aniso_p50": float(np.percentile(aniso[valid], 50)),
        "aniso_p95": float(np.percentile(aniso[valid], 95)),
        "aniso_p99": float(np.percentile(aniso[valid], 99)),
        "aniso_max": float(aniso[valid].max()),
        "aniso_over_2": int((aniso[valid] > 2.0).sum()),
        "aniso_over_4": int((aniso[valid] > 4.0).sum()),
        "seam_length_3d": float(seam),
        "seam_edges": int(seam_edges),
        "sliver_faces": int((a3 <= sliver_tol).sum()),
        "collapsed_uv_faces": int(collapsed.sum()),
        "seam_per_area": float(seam / np.sqrt(total3)),
        "chart_faces_min": int(sizes.min()), "chart_faces_p50": int(np.median(sizes)),
        "chart_faces_max": int(sizes.max()),
        "chart_distortion_p50": float(np.median(cdist)),
        "chart_distortion_max": float(cdist.max()),
        "charts_over_1_25": int((cdist > 1.25).sum()),
        "density_p05": float(np.percentile(cdens, 5)),
        "density_p95": float(np.percentile(cdens, 95)),
        "density_spread": float(np.percentile(cdens, 95) / np.percentile(cdens, 5)),
        "top_charts": charts[:8],
        "hist": {
            "chart_faces_log2": np.log2(np.maximum(sizes, 1)).astype(int).tolist(),
            "chart_distortion": cdist.round(3).tolist(),
        },
    }

    if args.npz:
        np.savez_compressed(args.npz, d=d[valid], aniso=aniso[valid], a3=a3[valid],
                            chart=chart[valid], sizes=sizes, cdist=cdist, cdens=cdens)

    with open(args.out, "w") as fh:
        json.dump(summary, fh, indent=2)

    print(f"[dist] mean {summary['distortion_mean']:.3f} p95 {summary['distortion_p95']:.3f} "
          f"p99 {summary['distortion_p99']:.3f} max {summary['distortion_max']:.3f}")
    print(f"[over] >1.25 {summary['faces_over_1_25']}  >1.5 {summary['faces_over_1_5']}  "
          f">2.0 {summary['faces_over_2_0']}  flipped {summary['flipped_faces']}  "
          f"degenerate {summary['degenerate_faces']}")
    print(f"[aniso] p50 {summary['aniso_p50']:.2f} p95 {summary['aniso_p95']:.2f} "
          f"max {summary['aniso_max']:.2f}")
    print(f"[charts] {nC}  faces min/med/max {summary['chart_faces_min']}/"
          f"{summary['chart_faces_p50']}/{summary['chart_faces_max']}  "
          f"dist>1.25: {summary['charts_over_1_25']}")
    print(f"[density] spread {summary['density_spread']:.2f}")
    print(f"[seam] {summary['seam_length_3d']:.1f} (3D units)")
    print(f"[write] {args.out}")


if __name__ == "__main__":
    main()





