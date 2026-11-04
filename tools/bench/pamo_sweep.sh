#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Compare pamo face-threshold settings (no rebuild needed).
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
mkdir -p /tmp/cfg2
for t in 1000 3000 8000; do
  sed "s/^\( *\)usePamoFaceThreshold: .*/\1usePamoFaceThreshold: $t/" "$CFG" > /tmp/cfg2/pamo_$t.yaml
  grep -n "usePamoFaceThreshold" /tmp/cfg2/pamo_$t.yaml
  OUT=out/pamo_$t
  PARTUV_PROF=$W/prof_pamo_$t.txt ./venv/bin/python $W/run_core.py \
      out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj \
      out/shusheng_120k_welded/shusheng_120k_welded/bin/shusheng_120k_welded.bin \
      "$OUT" 1.25 > "$W/pamo_$t.log" 2>&1
  echo "  $(grep -E '^\[done\]' "$W/pamo_$t.log")"
  grep -E "pamo.total|abf.total|overlap.cgal" "$W/prof_pamo_$t.txt" 2>/dev/null | awk '{printf "    %-14s %8.2fs %8s calls\n", $1, $2, $3}'
done