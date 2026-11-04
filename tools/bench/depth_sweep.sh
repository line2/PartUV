#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Nested-parallelism sweep: omp_set_nested(1) + "parallel sections" per level can spawn
# up to 2^depth threads.  Measure how much the over-subscription costs.
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
MESH=out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj
TREE=out/shusheng_120k_welded/shusheng_120k_welded/bin/shusheng_120k_welded.bin
mkdir -p /tmp/cfg5

for d in 10 4 2 1; do
  sed "s/^\( *\)parallelDepth: .*/\1parallelDepth: $d/" "$CFG" > /tmp/cfg5/depth_$d.yaml
done

run() {
  d=$1
  ./venv/bin/python $W/run_core.py "$MESH" "$TREE" "out/depth_$d" 1.25 /tmp/cfg5/depth_$d.yaml \
      > "$W/depth_$d.log" 2>&1
  echo "depth=$d rc=$? $(grep -E '^\[done\]' "$W/depth_$d.log" | sed 's/peak RSS //')"
  grep -cE "^PART:" "$W/depth_$d.log" | sed 's/^/    part-lines: /'
}

for d in 10 4 2 1; do run $d; done