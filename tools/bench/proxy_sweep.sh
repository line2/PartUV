#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Compare proxy backends: cuda (PAMO) vs cluster (cheap vertex clustering).
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
M120=out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj
T120=out/shusheng_120k_welded/shusheng_120k_welded/bin/shusheng_120k_welded.bin
M500=out/shusheng/model/model.obj
T500=out/shusheng/model/bin/model.bin
mkdir -p /tmp/cfgp

sed 's/^\( *\)pamo: true/\1pamo: true\n\1pamo_backend: "cluster"/' "$CFG" > /tmp/cfgp/cluster.yaml
grep -nE "pamo:|pamo_backend" /tmp/cfgp/cluster.yaml

run() {
  tag=$1 mesh=$2 tree=$3 cfg=$4
  PARTUV_PROF=$W/prof_${tag}.txt ./venv/bin/python $W/run_core.py "$mesh" "$tree" "out/$tag" 1.25 "$cfg" \
      > "$W/$tag.log" 2>&1
  echo "$tag rc=$? $(grep -E '^\[done\]' "$W/$tag.log" | sed 's/peak RSS //')"
  grep -E "proxy.cluster|pamo.total|abf.total|overlap.cgal" "$W/prof_${tag}.txt" 2>/dev/null \
    | awk '{printf "     %-14s %7.2fs %8s calls\n", $1, $2, $3}'
}

run cluster_120k "$M120" "$T120" /tmp/cfgp/cluster.yaml
run cluster_500k "$M500" "$T500" /tmp/cfgp/cluster.yaml