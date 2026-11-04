"""Clean summary of /tmp/igl_bench.json: drop sentinel distortions (>100 = INT_MAX marker)."""
import os
import json

import numpy as np

rows = json.load(open("/tmp/igl_bench.json"))
methods = ["abf", "igl_lscm", "igl_harmonic1", "igl_harmonic2", "igl_arap", "igl_slim"]

print(f"{'method':15s} {'ok':>3s} {'fail':>4s} {'ms/chart':>9s} {'ms/Mface':>9s} "
      f"{'dist med':>9s} {'dist p95':>9s} {'dist max':>9s} {'flip%':>6s}")
for m in methods:
    sel = [r for r in rows if r["method"] == m]
    ok = [r for r in sel if r["valid"]]
    good = [r for r in ok if 0.5 < r["distortion"] < 100]
    if not ok:
        print(f"{m:15s} {0:3d} {len(sel):4d}")
        continue
    ms = np.median([r["secs"] for r in ok]) * 1000
    faces = np.median([r["faces"] for r in ok])
    per_m = ms / faces * 1e6
    d = np.array([r["distortion"] for r in good]) if good else np.array([np.nan])
    flip = np.mean([r["flipped"] / max(r["faces"], 1) for r in ok]) * 100
    print(f"{m:15s} {len(ok):3d} {len(sel)-len(ok):4d} {ms:9.1f} {per_m:9.1f} "
          f"{np.median(d):9.3f} {np.percentile(d, 95):9.3f} {d.max():9.3f} {flip:6.2f}"
          + (f"   ({len(ok)-len(good)} sentinel)" if len(ok) != len(good) else ""))

print("\n--- head-to-head on charts where ARAP and ABF both succeeded ---")
by_chart = {}
for r in rows:
    by_chart.setdefault(r["chart"], {})[r["method"]] = r
pairs = [(c, v) for c, v in by_chart.items() if "abf" in v and "igl_arap" in v
         and v["abf"]["valid"] and v["igl_arap"]["valid"]
         and 0.5 < v["abf"]["distortion"] < 100]
print(f"charts: {len(pairs)}")
if pairs:
    a = np.array([v["abf"]["distortion"] for _, v in pairs])
    r_ = np.array([v["igl_arap"]["distortion"] for _, v in pairs])
    ta = np.array([v["abf"]["secs"] for _, v in pairs])
    tr = np.array([v["igl_arap"]["secs"] for _, v in pairs])
    print(f"  distortion  abf {np.median(a):.3f}  arap {np.median(r_):.3f}  "
          f"(arap better on {int((r_ < a).sum())}/{len(pairs)})")
    print(f"  time        abf {np.median(ta)*1000:.1f} ms  arap {np.median(tr)*1000:.1f} ms  "
          f"speedup {np.median(ta)/np.median(tr):.2f}x")
    print(f"  total time  abf {ta.sum():.2f} s  arap {tr.sum():.2f} s")