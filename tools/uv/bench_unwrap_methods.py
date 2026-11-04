"""Compare ABF++ against the libigl parameterisations on real PartUV charts.

Charts come from the proxy dumps (real submeshes the pipeline flattened).  Each method
runs on the same chart, so time / distortion / folds are directly comparable.
"""
import glob
import json
import os
import sys
import time

import numpy as np

import partuv
from partuv import _core

CHART_DIR = os.path.join(os.environ.get("BAKE_WORK", "/mnt/c/Users/JdSc-local/Project/blend-baking"), "proxy_dump", "raw")
METHODS = ["abf", "igl_lscm", "igl_harmonic1", "igl_harmonic2", "igl_arap", "igl_slim"]
ITERS = 5


def load_obj(path):
    V, F = [], []
    with open(path, errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                V.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                F.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
    return np.asarray(V, dtype=np.float64), np.asarray(F, dtype=np.int32)


charts = []
for path in sorted(glob.glob(os.path.join(CHART_DIR, "*_chart.obj"))):
    V, F = load_obj(path)
    if 300 <= len(F) <= 60000:          # skip the whole-mesh and the 1-face dumps
        charts.append((os.path.basename(path).split("_")[0], V, F, path))

print(f"charts: {len(charts)}  faces: {[len(F) for _, _, F, _ in charts]}", flush=True)

rows = []
for name, V, F, path in charts:
    for method in METHODS:
        # run in a subprocess-free way but guard against crashes with a size check
        try:
            t0 = time.time()
            res = _core.bench_flatten(V, F, method, ITERS)
            wall = time.time() - t0
        except Exception as exc:                     # noqa: BLE001
            res = {"rc": -99, "seconds": -1, "distortion": -1, "flipped": -1,
                   "uv_valid": False, "err": str(exc)}
            wall = -1
        rows.append({
            "chart": name,
            "faces": int(len(F)),
            "method": method,
            "rc": int(res.get("rc", -99)),
            "secs": float(res.get("seconds", -1)),
            "distortion": float(res.get("distortion", -1)),
            "flipped": int(res.get("flipped", -1)),
            "valid": bool(res.get("uv_valid", False)),
        })
        r = rows[-1]
        print(f"  {name:>5} {len(F):6d}f {method:14s} rc={r['rc']:3d} "
              f"{r['secs']*1000:8.1f} ms  dist={r['distortion']:7.3f} "
              f"flip={r['flipped']}", flush=True)

out = "/tmp/igl_bench.json"
json.dump(rows, open(out, "w"), indent=1)
print(f"[bench] wrote {out}")

print("\n=== summary (mean over charts where the method succeeded) ===")
print(f"{'method':16s} {'ok':>4s} {'fail':>5s} {'ms/chart':>10s} {'dist mean':>10s} "
      f"{'dist p95':>9s} {'flip %':>7s}")
for method in METHODS:
    sel = [r for r in rows if r["method"] == method]
    ok = [r for r in sel if r["valid"]]
    fail = len(sel) - len(ok)
    if not ok:
        print(f"{method:16s} {0:4d} {fail:5d} {'-':>10s} {'-':>10s} {'-':>9s} {'-':>7s}")
        continue
    ms = np.mean([r["secs"] for r in ok]) * 1000
    d = np.array([r["distortion"] for r in ok])
    flip = np.mean([r["flipped"] / max(r["faces"], 1) for r in ok]) * 100
    print(f"{method:16s} {len(ok):4d} {fail:5d} {ms:10.1f} {d.mean():10.3f} "
          f"{np.percentile(d, 95):9.3f} {flip:7.1f}")