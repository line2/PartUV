# -*- coding: utf-8 -*-
"""核心烘焙逻辑（必须在 Blender 进程内运行）。

对外只暴露一个函数：`rebake(config) -> JobResult`。
本模块**不写最终产物**：图像以内存数据（numpy 数组 + PNG 字节）返回，
由 `write.py` / CLI 决定落盘位置。
"""

from __future__ import annotations

import os
import re
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from typing import Optional

import bpy
import numpy as np

from .config import CHANNELS, JobConfig

# ---------------------------------------------------------------- 结果类型


@dataclass
class BakeImage:
    """单通道烘焙结果。`png_bytes` 是权威数据，`array` 便于二次加工。"""

    channel: str
    size: int
    array: np.ndarray            # uint8, shape (H, W, 4)
    png_bytes: bytes
    path: Optional[str] = None   # 由 write 层填充


@dataclass
class JobResult:
    object_name: str
    uv_layer: str
    uv_kept: bool
    uv_islands: int
    uv_coverage: float
    cage_extrusion: float
    images: dict = field(default_factory=dict)   # channel -> BakeImage
    timings: dict = field(default_factory=dict)  # channel -> seconds
    target_object: object = None                 # bpy 物体，write 层导出用
    obj_path: Optional[str] = None               # 由 write 层填充
    manifest: dict = field(default_factory=dict)


def log(msg: str) -> None:
    print(msg, flush=True)


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "Mesh"


# ---------------------------------------------------------------- 场景工具
def select_only(*objects, active=None):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = active or (objects[-1] if objects else None)


def duplicate_mesh(original, suffix: str):
    ob = original.copy()
    ob.data = original.data.copy()
    bpy.context.collection.objects.link(ob)
    ob.name = original.name + suffix
    ob.hide_render = False
    ob.hide_set(False)
    return ob


def uv_stats(mesh, uv_name: str):
    """返回 (岛数, UV 面积总和)。

    按**面**做并查集：按顶点做会把边界上未连通的顶点各自算成岛（实测 38741
    vs 正确的 14488）；不看 UV 则退化成网格连通分量。
    """
    uvl = mesh.uv_layers.get(uv_name)
    if uvl is None:
        return 0, 0.0

    npoly = len(mesh.polygons)
    parent = list(range(npoly))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    loop_vert = [l.vertex_index for l in mesh.loops]
    edges = {}
    for poly in mesh.polygons:
        ls = list(poly.loop_indices)
        n = len(ls)
        for i in range(n):
            l1, l2 = ls[i], ls[(i + 1) % n]
            v1, v2 = loop_vert[l1], loop_vert[l2]
            key = (v1, v2) if v1 < v2 else (v2, v1)
            edges.setdefault(key, []).append(
                (poly.index, {v1: tuple(uvl.data[l1].uv),
                              v2: tuple(uvl.data[l2].uv)}))

    for key, occ in edges.items():
        if len(occ) != 2:
            continue
        (pa, ua), (pb, ub) = occ
        if all(abs(ua[v][0] - ub[v][0]) < 1e-6
               and abs(ua[v][1] - ub[v][1]) < 1e-6 for v in key):
            union(pa, pb)

    islands = len({find(i) for i in range(npoly)})

    area = 0.0
    for poly in mesh.polygons:
        us = [tuple(uvl.data[li].uv) for li in poly.loop_indices]
        acc = 0.0
        for i in range(len(us)):
            x1, y1 = us[i]
            x2, y2 = us[(i + 1) % len(us)]
            acc += x1 * y2 - x2 * y1
        area += abs(acc) * 0.5
    return islands, area


# ---------------------------------------------------------------- 材质
def find_principled(node_tree, material_output):
    surface = material_output.inputs.get("Surface")
    stack = [l.from_node for l in surface.links] if surface else []
    seen = set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        if node.type == "BSDF_PRINCIPLED":
            return node
        for sock in node.inputs:
            stack.extend(l.from_node for l in sock.links)
    return next((n for n in node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def prepare_source_materials(source):
    """私有材质副本：把三通道各接一个 Emission，原材质节点树保持不动。"""
    states, temps = [], []
    if not len(source.data.materials):
        source.data.materials.append(bpy.data.materials.new("Bake_Default"))

    for idx in range(len(source.data.materials)):
        old = source.data.materials[idx]
        mat = old.copy() if old is not None else bpy.data.materials.new("Bake_Default")
        mat.name = "__TEMP_BAKE_%s_%d" % (source.name, idx)
        source.data.materials[idx] = mat
        temps.append(mat)

        if not mat.use_nodes:
            mat.use_nodes = True

        tree = mat.node_tree
        output = next((n for n in tree.nodes
                       if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
        if output is None:
            output = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = tree.nodes.new("ShaderNodeOutputMaterial")

        emission = tree.nodes.new("ShaderNodeEmission")
        emission.name = "_TEMP_BAKE_EMISSION"
        emission.inputs["Strength"].default_value = 1.0

        states.append({
            "tree": tree,
            "output": output,
            "principled": find_principled(tree, output),
            "emission": emission,
            "fallback": {
                "BaseColor": tuple(mat.diffuse_color),
                "Metallic": float(mat.metallic),
                "Roughness": float(mat.roughness),
            },
        })
    return states, temps


def source_pass(states, channel: str):
    """把指定 Principled 输入临时接到 Emission，供 EMIT 烘焙取样。"""
    socket_name = {
        "BaseColor": "Base Color",
        "Metallic": "Metallic",
        "Roughness": "Roughness",
    }[channel]

    for state in states:
        tree = state["tree"]
        surface = state["output"].inputs["Surface"]
        for link in list(surface.links):
            tree.links.remove(link)

        emit = state["emission"]
        color = emit.inputs["Color"]
        for link in list(color.links):
            tree.links.remove(link)

        bsdf = state["principled"]
        sock = bsdf.inputs.get(socket_name) if bsdf else None
        if sock is not None and sock.is_linked:
            tree.links.new(sock.links[0].from_socket, color)
        elif sock is not None:
            value = sock.default_value
            if channel == "BaseColor":
                color.default_value = tuple(value)
            else:
                v = float(value)
                color.default_value = (v, v, v, 1.0)
        else:
            value = state["fallback"][channel]
            color.default_value = (tuple(value) if channel == "BaseColor"
                                   else (value, value, value, 1.0))

        tree.links.new(emit.outputs["Emission"], surface)


def new_target_material(target):
    mat = bpy.data.materials.new(target.name + "_PBR")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (480, 100)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (180, 100)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    target.data.materials.clear()
    target.data.materials.append(mat)
    for poly in target.data.polygons:
        poly.material_index = 0
    return mat, bsdf


def unwrap_target(target, uv_name: str, margin: float, angle_deg: float):
    import math

    for layer in list(target.data.uv_layers):
        target.data.uv_layers.remove(layer)
    layer = target.data.uv_layers.new(name=uv_name)
    target.data.uv_layers.active = layer
    layer.active_render = True

    select_only(target, active=target)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(
            island_margin=margin,
            angle_limit=math.radians(angle_deg),
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=True,
        )
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


# ---------------------------------------------------------------- 烘焙
def _image_to_result(image, channel: str) -> BakeImage:
    """把 bpy 图像读成 uint8 数组 + PNG 字节（PNG 用临时文件编码，随后删除）。"""
    w, h = image.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(buf)
    arr = np.rint(np.clip(buf, 0.0, 1.0).reshape(h, w, 4) * 255.0).astype(np.uint8)

    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image.filepath_raw = tmp
        image.file_format = "PNG"
        image.save()
        with open(tmp, "rb") as f:
            png_bytes = f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return BakeImage(channel=channel, size=w, array=arr, png_bytes=png_bytes)


def bake_channel(target, source, material, channel, size, margin_px,
                 cage, samples):
    image = bpy.data.images.new("%s_%s" % (safe_name(target.name), channel),
                                width=size, height=size, alpha=False,
                                float_buffer=False)
    if channel != "BaseColor":
        image.colorspace_settings.name = "Non-Color"

    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.name = "Baked_" + channel
    node.image = image
    for n in material.node_tree.nodes:
        n.select = False
    node.select = True
    material.node_tree.nodes.active = node   # 烘焙目标 = 激活的图像节点

    bpy.context.scene.cycles.samples = samples

    t0 = time.perf_counter()
    select_only(source, target, active=target)
    bpy.context.view_layer.update()
    bpy.ops.object.bake(
        type="EMIT",
        use_selected_to_active=True,
        use_cage=True,
        cage_extrusion=cage,
        margin=margin_px,
        use_clear=True,
        target="IMAGE_TEXTURES",
    )
    elapsed = time.perf_counter() - t0

    result = _image_to_result(image, channel)
    mat_nodes = material.node_tree.nodes
    mat_nodes.remove(node)
    if image.users == 0:
        bpy.data.images.remove(image)
    return result, elapsed


# ---------------------------------------------------------------- 主入口
def rebake(config: JobConfig) -> JobResult:
    """执行一次烘焙。不写最终产物，返回内存结果。"""
    config.validate()

    if config.dest_mesh_path:
        path = os.path.abspath(config.dest_mesh_path)
        if not os.path.exists(path):
            raise FileNotFoundError("input not found: %s" % path)
        before = set(bpy.context.scene.objects)
        bpy.ops.wm.obj_import(filepath=path)
        originals = [o for o in bpy.context.scene.objects
                     if o.type == "MESH" and o not in before]
    else:
        originals = [o for o in bpy.context.selected_objects if o.type == "MESH"]

    if not originals:
        raise ValueError("no mesh to bake (pass dest_mesh_path or select a mesh)")
    if len(originals) > 1:
        raise ValueError("v1 supports a single target mesh, got %d" % len(originals))

    source_obj = None
    if config.source_mesh_path:
        src = os.path.abspath(config.source_mesh_path)
        if not os.path.exists(src):
            raise FileNotFoundError("source not found: %s" % src)
        before_src = set(bpy.context.scene.objects)
        bpy.ops.wm.obj_import(filepath=src)
        pool = [o for o in bpy.context.scene.objects
                if o.type == "MESH" and o not in before_src]
        if not pool:
            raise ValueError("source has no mesh: %s" % src)
        source_obj = pool[0]

    original = originals[0]
    scene = bpy.context.scene
    old_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    scene.cycles.device = config.device
    scene.cycles.samples = config.samples

    source = target = None
    temps = []
    ok = False
    try:
        src_from = source_obj if source_obj is not None else original
        source = duplicate_mesh(src_from, "__BAKE_SOURCE")

        target = duplicate_mesh(original, "_Baked")
        if config.keep_uv:
            layer = target.data.uv_layers.active
            if layer is None:
                raise ValueError("keep_uv=True but the input mesh has no UV layer")
            layer.active_render = True
            uv_name = layer.name
        else:
            uv_name = "UV_Rebaked"
            unwrap_target(target, uv_name, config.uv_margin, config.uv_angle)

        islands, area = uv_stats(target.data, uv_name)

        states, temps = prepare_source_materials(source)
        material, bsdf = new_target_material(target)

        cage = max(1e-5, max(target.dimensions) * config.cage_ratio)

        images, timings = {}, {}
        for channel in CHANNELS:
            source_pass(states, channel)
            img, dt = bake_channel(target, source, material, channel,
                                   config.texture_size, config.margin_px, cage,
                                   config.samples)
            images[channel] = img
            timings[channel] = round(dt, 2)
            log("  baked %-10s %6.2fs" % (channel, dt))

        original.hide_set(True)
        original.hide_render = True
        ok = True

        return JobResult(
            object_name=safe_name(original.name),
            uv_layer=uv_name,
            uv_kept=bool(config.keep_uv),
            uv_islands=islands,
            uv_coverage=round(area, 6),
            cage_extrusion=round(cage, 6),
            images=images,
            timings=timings,
            target_object=target,
        )
    finally:
        if source:
            data = source.data
            bpy.data.objects.remove(source, do_unlink=True)
            if data.users == 0:
                bpy.data.meshes.remove(data)
        for mat in temps:
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        if not ok and target:
            # 失败时不留半成品；成功时 target 交给 write 层导出
            data = target.data
            bpy.data.objects.remove(target, do_unlink=True)
            if data.users == 0:
                bpy.data.meshes.remove(data)
        scene.render.engine = old_engine