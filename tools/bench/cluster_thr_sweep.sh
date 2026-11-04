#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# With the cheap proxy, PAMO's face-count gate can be lowered: sweep it.
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
M120=out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj
T120=out/shusheng_120k_welded/shusheng_120k_welded/bin/shusheng_120k_welded.bin
mkdir -p /tmp/cfgq

for t in 4000 1000 300; do
  sed "s/^\( *\)pamo: true/\1pamo: true\n\1pamo_backend: \"cluster\"/; s/^\( *\)usePamoFaceThreshold: .*/\1usePamoFaceThreshold: $t/" \
      "$CFG" > /tmp/cfgq/c_$t.yaml
  ./venv/bin/python $W/run_core.py "$M120" "$T120" "out/cl_$t" 1.25 /tmp/cfgq/c_$t.yaml \
      > "$W/cl_$t.log" 2>&1
  echo "cluster thr=$t rc=$? $(grep -E '^\[done\]' "$W/cl_$t.log" | sed 's/peak RSS //')"
done