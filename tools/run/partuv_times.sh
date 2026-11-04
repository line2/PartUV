#!/usr/bin/env bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Summarize every recorded timing.json under ~/partuv_work/out
cd ${PARTUV_WORK:-$HOME/partuv_work} || exit 1
${PARTUV_WORK:-$HOME/partuv_work}/venv/bin/python - <<'PY'
import glob
import json

rows = []
for p in sorted(glob.glob('out/*/*/timing.json')):
    d = json.load(open(p))
    pre = d.get('preprocess_breakdown_s') or {}
    mesh = d.get('mesh_after_preprocess') or {}
    rows.append((
        p[4:-12],
        d.get('preprocess_s', 0.0),
        pre.get('pf', 0.0),
        d.get('unwrap_s', 0.0),
        d.get('save_s', 0.0),
        d.get('total_s', 0.0),
        d.get('individual_parts', 0),
        mesh.get('F', 0),
        d.get('gpu_peak_gb_unwrap', 0.0),
    ))

hdr = f"{'run':34s} {'pre':>6s} {'of which PF':>11s} {'unwrap':>7s} {'save':>5s} {'total':>7s} {'parts':>6s} {'faces':>8s} {'GPU GB':>7s}"
print(hdr)
print('-' * len(hdr))
for r in sorted(rows, key=lambda x: x[7]):
    print(f"{r[0]:34s} {r[1]:6.1f} {r[2]:11.1f} {r[3]:7.1f} {r[4]:5.1f} {r[5]:7.1f} {r[6]:6d} {r[7]:8d} {r[8]:7.2f}")
PY
echo
echo "=== wall clock of the OOM attempt (log mtime) ==="
ls -l --time-style=+%H:%M:%S shusheng.log 2>/dev/null
grep -c "created with charts" shusheng.log 2>/dev/null