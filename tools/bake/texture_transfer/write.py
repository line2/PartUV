# -*- coding: utf-8 -*-
"""落盘层：把 `core.rebake()` 返回的内存数据写成文件。

CLI 调它；Python API 若不需要文件可以不调。
"""

from __future__ import annotations

import json
import os
from typing import List

import bpy

from .config import JobConfig
from .core import JobResult, log, select_only

MTL_KEY = {"BaseColor": "map_Kd", "Roughness": "map_Pr", "Metallic": "map_Pm"}


def _write_bytes(path: str, data: bytes, overwrite: bool) -> bool:
    if os.path.exists(path) and not overwrite:
        log("  skip (exists) %s" % os.path.basename(path))
        return False
    with open(path, "wb") as f:
        f.write(data)
    return True


def write_outputs(result: JobResult, config: JobConfig) -> JobResult:
    """写 PNG / MTL / OBJ / manifest，并把路径回填到 result。"""
    root = config.resolved_output_folder()
    folder = os.path.join(root, result.object_name)
    os.makedirs(folder, exist_ok=True)

    for channel, img in result.images.items():
        path = os.path.join(folder, "%s_%s.png" % (result.object_name, channel))
        if _write_bytes(path, img.png_bytes, config.overwrite):
            img.path = path
            log("  wrote %s" % os.path.basename(path))

    if config.export_obj:
        result.obj_path = _export_mesh(result, folder, config)

    manifest = _manifest(result, config)
    result.manifest = manifest
    mpath = os.path.join(root, "rebake_manifest.json")
    if config.overwrite or not os.path.exists(mpath):
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        log("  wrote manifest")
    return result


def _export_mesh(result: JobResult, folder: str, config: JobConfig) -> str:
    obj_path = os.path.join(folder, result.object_name + "_baked.obj")
    select_only(result.target_object, active=result.target_object)
    bpy.ops.wm.obj_export(
        filepath=obj_path,
        export_selected_objects=True,
        export_materials=False,
        export_uv=True,
        export_normals=True,
        export_triangulated_mesh=False,
        path_mode="RELATIVE",
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )

    mtl_name = result.object_name + ".mtl"
    lines = ["%s %s_%s.png" % (MTL_KEY[ch], result.object_name, ch)
             for ch in result.images if ch in MTL_KEY]
    mtl = ("# %s - baked by pipeline\n"
           "newmtl material_0\n"
           "Ka 1.000000 1.000000 1.000000\n"
           "Kd 1.000000 1.000000 1.000000\n"
           "Ks 0.000000 0.000000 0.000000\n"
           "d 1.000000\n"
           "illum 2\n%s\n" % (result.object_name, "\n".join(lines)))
    with open(os.path.join(folder, mtl_name), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(mtl)

    # export_materials=False 时不写 usemtl，必须补，否则 MTL 成了孤儿
    with open(obj_path, "r", encoding="utf-8", errors="replace") as f:
        src = f.readlines()
    out, has_mtllib, has_usemtl = [], False, False
    for line in src:
        if line.startswith("mtllib "):
            out.append("mtllib %s\n" % mtl_name)
            has_mtllib = True
            continue
        if line.startswith("usemtl "):
            has_usemtl = True
        if line.startswith("f ") and not has_usemtl:
            out.append("usemtl material_0\n")
            has_usemtl = True
        out.append(line)
    if not has_mtllib:
        out.insert(1, "mtllib %s\n" % mtl_name)
    with open(obj_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(out)

    log("  wrote %s" % os.path.basename(obj_path))
    return obj_path


def _manifest(result: JobResult, config: JobConfig) -> dict:
    return {
        "schema_version": 1,
        "tool": "pipeline",
        "blender": bpy.app.version_string,
        "object": result.object_name,
        "uv": {
            "layer": result.uv_layer,
            "kept": result.uv_kept,
            "islands": result.uv_islands,
            "coverage": result.uv_coverage,
        },
        "bake": {
            "size": config.texture_size,
            "samples": config.samples,
            "channels": list(result.images),
            "margin_px": config.margin_px,
            "cage_extrusion": result.cage_extrusion,
            "device": config.device,
        },
        "timings": result.timings,
        "files": {
            "obj": result.obj_path,
            "images": {ch: img.path for ch, img in result.images.items()},
        },
        "config": config.to_dict(),
    }