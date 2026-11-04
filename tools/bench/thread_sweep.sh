#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Thread-count sweep (num_omp_threads) on the 120k mesh.
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
MESH=out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj
TREE=out/shusheng_120k_welded/shusheng_120k_welded/bin/shusheng_120k_welded.bin
mkdir -p /tmp/cfg6

echo "nproc=$(nproc)  model=$(lscpu | grep 'Model name' | cut -d: -f2)"

for t in 8 16 24; do
  sed "s/^\( *\)num_omp_threads: .*/\1num_omp_threads: $t/" "$CFG" > /tmp/cfg6/t_$t.yaml
  ./venv/bin/python $W/run_core.py "$MESH" "$TREE" "out/thr_$t" 1.25 /tmp/cfg6/t_$t.yaml \
      > "$W/thr_$t.log" 2>&1
  echo "threads=$t rc=$? $(grep -E '^\[done\]' "$W/thr_$t.log" | sed 's/peak RSS //')"
done