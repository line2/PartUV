"""Triangle-quality comparison: dumped chart vs the proxy built from it."""
import glob
import os
import sys

import numpy as np


def load_obj(path):
    V, F = [], []
    with open(path, errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                V.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                F.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
    return np.asarray(V), np.asarray(F)


def stats(V, F):
    a = V[F[:, 0]]
    b = V[F[:, 1]]
    c = V[F[:, 2]]
    e = np.stack([np.linalg.norm(b - c, axis=1),
                  np.linalg.norm(c - a, axis=1),
                  np.linalg.norm(a - b, axis=1)], axis=1)
    # angle opposite each edge, via the cosine rule
    ang = np.empty_like(e)
    for i in range(3):
        opp = e[:, i]
        s1 = e[:, (i + 1) % 3]
        s2 = e[:, (i + 2) % 3]
        cos = (s1 ** 2 + s2 ** 2 - opp ** 2) / np.maximum(2 * s1 * s2, 1e-30)
        ang[:, i] = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
    minang = ang.min(axis=1)
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    return {
        "faces": len(F),
        "min_angle_p50": float(np.median(minang)),
        "min_angle_p05": float(np.percentile(minang, 5)),
        "below_10deg": float((minang < 10).mean()),
        "below_5deg": float((minang < 5).mean()),
        "area": float(area.sum()),
        "sliver_ratio": float((e.max(axis=1) / np.maximum(e.min(axis=1), 1e-30)).max()),
    }


root = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(os.environ.get("BAKE_WORK", "/mnt/c/Users/JdSc-local/Project/blend-baking"), "proxy_dump", "raw")

for chart in sorted(glob.glob(os.path.join(root, "*_chart.obj")))[:6]:
    pid = os.path.basename(chart).split("_")[0]
    proxy = os.path.join(root, f"{pid}_proxy.obj")
    if not os.path.exists(proxy):
        continue
    Vc, Fc = load_obj(chart)
    Vp, Fp = load_obj(proxy)
    sc = stats(Vc, Fc)
    sp = stats(Vp, Fp)
    print(f"=== {pid}: chart {sc['faces']} faces -> proxy {sp['faces']} faces ===")
    print(f"  min-angle   chart p50 {sc['min_angle_p50']:5.1f}  p05 {sc['min_angle_p05']:5.1f}"
          f"   |  proxy p50 {sp['min_angle_p50']:5.1f}  p05 {sp['min_angle_p05']:5.1f}")
    print(f"  <10 deg     chart {sc['below_10deg']*100:5.1f}%   |  proxy {sp['below_10deg']*100:5.1f}%")
    print(f"  <5  deg     chart {sc['below_5deg']*100:5.1f}%   |  proxy {sp['below_5deg']*100:5.1f}%")
    print(f"  area        chart {sc['area']:10.3f}  proxy {sp['area']:10.3f}"
          f"   (ratio {sp['area']/max(sc['area'],1e-9):.3f})")