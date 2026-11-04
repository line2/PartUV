#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Make the cheap proxy the default backend and verify once.
cd ${PARTUV_REPO:-$PARTUV_WORK/PartUV}
grep -n "pamo_backend" config/config.yaml || \
  sed -i 's/^\( *\)pamo: true/\1pamo: true\n\1pamo_backend: "cluster"   # cheap vertex-clustering proxy (deterministic, ~35% faster than cuda QEM)/' config/config.yaml
grep -nE "pamo:|pamo_backend|usePamoFaceThreshold" config/config.yaml

cd ${PARTUV_WORK:-$HOME/partuv_work}
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
./venv/bin/python $W/run_core.py out/shusheng/model/model.obj out/shusheng/model/bin/model.bin out/default_cluster 1.25 \
    > "$W/default_cluster.log" 2>&1
echo "rc=$? $(grep -E '^\[done\]' "$W/default_cluster.log" | sed 's/peak RSS //')"
md5sum out/default_cluster/final_components.obj | cut -d' ' -f1