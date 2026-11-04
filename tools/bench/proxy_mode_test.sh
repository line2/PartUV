#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Compare proxy modes on the 500k model: per-chart 5% vs model-wide cell.
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
MESH=out/shusheng/model/model.obj
TREE=out/shusheng/model/bin/model.bin
mkdir -p /tmp/cfgm

sed 's/^\( *\)pamo_backend: .*/\1pamo_backend: "cluster"\n\1pamo_proxy_mode: "global"/' "$CFG" > /tmp/cfgm/global.yaml
grep -nE "pamo_backend|pamo_proxy_mode" /tmp/cfgm/global.yaml

run() {
  tag=$1 cfg=$2
  PARTUV_PROF=$W/prof_$tag.txt ./venv/bin/python $W/run_core.py "$MESH" "$TREE" "out/$tag" 1.25 "$cfg" \
      > "$W/$tag.log" 2>&1
  rc=$?
  md5=$(md5sum "out/$tag/final_components.obj" 2>/dev/null | cut -d' ' -f1)
  echo "$tag rc=$rc md5=${md5:0:12} $(grep -E '^\[done\]' "$W/$tag.log" | sed 's/peak RSS //')"
  grep -E "proxy.cluster|pamo.total|abf.total|overlap.cgal" "$W/prof_$tag.txt" 2>/dev/null \
    | awk '{printf "     %-14s %8.2fs %9s calls\n", $1, $2, $3}'
}

run proxy_relative "$CFG"
run proxy_global   /tmp/cfgm/global.yaml