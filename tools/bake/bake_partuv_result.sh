#!/bin/bash
PARTUV_WORK=${PARTUV_WORK:-$HOME/partuv_work}
PARTUV_REPO=${PARTUV_REPO:-$PARTUV_WORK/PartUV}
# Bake the original asset's textures onto a PartUV result, using the texture_transfer addon.
#
# Two steps, because PartUV writes an *unpacked* UV layout: every chart gets its own unit
# square, so the coordinate range is e.g. u in [-3.1, 19.8] and a keep-uv bake would only
# capture whatever falls inside [0,1].  Step 1 packs the islands; step 2 bakes.
#
# Usage: bake_partuv_result.sh <partuv_result.obj> <source_textured.obj> <out_dir> [size]
set -e
W=${BAKE_WORK:?set BAKE_WORK to the directory holding the scripts/assets}
BL=${BLENDER_BIN:?set BLENDER_BIN to the blender executable}

TGT="$1"; SRC="$2"; OUT="$3"; SIZE="${4:-4096}"
PACKED="$OUT/$(basename "${TGT%.obj}")_packed.obj"
mkdir -p "$OUT"

echo "=== 1/2 packing UV islands ==="
"$BL" -b --factory-startup --python "$W/pack_uv_obj.py" -- 0.004 2>&1 \
    | grep -E "^\[pack\]" | sed 's/^/  /'

echo "=== 2/2 baking BaseColor / Roughness / Metallic ==="
"$BL" -b --factory-startup --python-exit-code 2 --python "$W/blender_texture_transfer.py" -- \
    --dest_mesh_path "$TGT" \
    --source_mesh_path "$SRC" \
    --keep_uv --output_folder "$OUT" --texture_size "$SIZE" --samples 32 \
    --log_path "$OUT/bake.log" > /dev/null 2>&1
grep -E "^  (uv|baked|wrote|done)" "$OUT/bake.log" | sed 's/^/  /'