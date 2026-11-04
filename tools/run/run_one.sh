#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# usage: run_one.sh <name> <threshold> <config-path>
name=$1; thr=$2; cfg=$3
cd ${PARTUV_WORK:-$HOME/partuv_work}
RES=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}/abl_results.txt
LOG="${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}/abl_${name}.log"
t0=$(date +%s)
./venv/bin/python ${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}/partuv_run.py \
    --mesh out/shusheng_120k_welded/shusheng_120k_welded/shusheng_120k_welded.obj \
    --out "out/abl_${name}" \
    --threshold "$thr" \
    --config "$cfg" \
    --sample-batch 20000 \
    --ckpt ${PARTUV_REPO:-$PARTUV_WORK/PartUV}/model_objaverse.ckpt \
    --timing "out/abl_${name}/timing.json" > "$LOG" 2>&1
rc=$?
t1=$(date +%s)
timing=$(cat "out/abl_${name}/timing.json" 2>/dev/null | tr -d '\n ')
echo "${name} thr=${thr} rc=${rc} wall=$((t1-t0))s ${timing}" | tee -a "$RES"
tail -2 "$LOG"