#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Real sweep: pass the config through (run_core.py now takes it as argv[5]).
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
MESH=out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj
TREE=out/shusheng_120k_welded/shusheng_120k_welded/bin/shusheng_120k_welded.bin
mkdir -p /tmp/cfg4

sed 's/^\( *\)pamo: true/\1pamo: false/' "$CFG"        > /tmp/cfg4/nopamo.yaml
sed 's/^\( *\)abf_iters: 5/\1abf_iters: 1/' "$CFG"     > /tmp/cfg4/abf1.yaml
sed 's/^\( *\)abf_iters: 5/\1abf_iters: 20/' "$CFG"    > /tmp/cfg4/abf20.yaml

for f in /tmp/cfg4/*.yaml; do echo "--- $f"; grep -nE "abf_iters|pamo:" "$f"; done

run() {
  name=$1; cfg=$2
  PARTUV_PROF=$W/prof2_$name.txt ./venv/bin/python $W/run_core.py "$MESH" "$TREE" "out/r2_$name" 1.25 "$cfg" \
      > "$W/r2_$name.log" 2>&1
  rc=$?
  echo "$name rc=$rc: $(grep -E '^\[done\]' "$W/r2_$name.log" | sed 's/peak RSS //')"
  grep -E "pamo.total|abf.angles|abf.lscm|overlap.cgal" "$W/prof2_$name.txt" 2>/dev/null \
    | awk '{printf "    %-12s %7.2fs\n", $1, $2}'
}

run abf1   /tmp/cfg4/abf1.yaml
run abf20  /tmp/cfg4/abf20.yaml
run nopamo /tmp/cfg4/nopamo.yaml