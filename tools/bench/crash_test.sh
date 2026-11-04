#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Controlled crash/determinism test. NO builds run during this script.
# usage: crash_test.sh <variant: cuda|cluster|off> <reps>
cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
CFG=${PARTUV_REPO:-$PARTUV_WORK/PartUV}/config/config.yaml
MESH=out/shusheng/model/model.obj
TREE=out/shusheng/model/bin/model.bin
VAR=$1
REPS=${2:-4}
mkdir -p /tmp/cfgx

case "$VAR" in
  cuda)    CFGP="$CFG" ;;
  off)     sed 's/^\( *\)pamo: true/\1pamo: false/' "$CFG" > /tmp/cfgx/off.yaml; CFGP=/tmp/cfgx/off.yaml ;;
  cluster) sed 's/^\( *\)pamo: true/\1pamo: true\n\1pamo_backend: "cluster"/' "$CFG" > /tmp/cfgx/cluster.yaml; CFGP=/tmp/cfgx/cluster.yaml ;;
  *) echo "unknown variant $VAR"; exit 2 ;;
esac

echo "=== variant=$VAR reps=$REPS config=$CFGP"
grep -nE "pamo:|pamo_backend|usePamoFaceThreshold" "$CFGP" | sed 's/^/    /'

for i in $(seq 1 "$REPS"); do
  OUT="out/crash_${VAR}_$i"
  rm -rf "$OUT"
  T0=$(date +%s)
  ./venv/bin/python $W/run_core.py "$MESH" "$TREE" "$OUT" 1.25 "$CFGP" > "$W/crash_${VAR}_$i.log" 2>&1
  RC=$?
  T1=$(date +%s)
  MD5=$(md5sum "$OUT/final_components.obj" 2>/dev/null | cut -d' ' -f1)
  DONE=$(grep -E '^\[done\]' "$W/crash_${VAR}_$i.log" | sed 's/peak RSS //;s/^\[done\] //')
  echo "  run $i: rc=$RC wall=$((T1-T0))s md5=${MD5:0:12} $DONE"
  [ $RC -ne 0 ] && tail -3 "$W/crash_${VAR}_$i.log" | sed 's/^/      /'
done