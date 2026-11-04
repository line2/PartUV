"""Pack PartUV charts with Blender's pack_islands, measure UV stats, render checks.

Usage:
  blender -b --factory-startup --python partuv_pack_metrics.py -- <final_components.obj> <out_dir> [margin]
"""
import bpy
import json
import math
import os
import sys
import time

import numpy as np


def arg_after_dashes():
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1:]


def uv_island_count(mesh, uv_layer):
    """Count UV charts: polygons joined when both UVs of their shared edge agree."""
    me = mesh
    n_loops = len(me.loops)
    n_polys = len(me.polygons)

    vert_of_loop = np.empty(n_loops, dtype=np.int64)
    me.loops.foreach_get("vertex_index", vert_of_loop)
    edge_of_loop = np.empty(n_loops, dtype=np.int64)
    me.loops.foreach_get("edge_index", edge_of_loop)
    poly_of_loop = np.empty(n_loops, dtype=np.int64)
    # Blender's loop.polygon_index is not exposed via foreach_get in 5.x; derive from poly ranges
    poly_start = np.empty(n_polys, dtype=np.int64)
    poly_total = np.empty(n_polys, dtype=np.int64)
    me.polygons.foreach_get("loop_start", poly_start)
    me.polygons.foreach_get("loop_total", poly_total)
    for pi, (s, t) in enumerate(zip(poly_start.tolist(), poly_total.tolist())):
        poly_of_loop[s:s + t] = pi
    uvs = np.empty((n_loops, 2), dtype=np.float64)
    uv_layer.data.foreach_get("uv", uvs.ravel())

    # next loop inside each polygon (loops are ordered per polygon)
    next_loop = np.empty(n_loops, dtype=np.int64)
    for s, t in zip(poly_start.tolist(), poly_total.tolist()):
        for k in range(t):
            next_loop[s + k] = s + (k + 1) % t

    # edge -> list of (polygon, {vertex: uv}) for the two endpoints
    edge_ends = {}
    for li in range(n_loops):
        e = int(edge_of_loop[li])
        p = int(poly_of_loop[li])
        v0 = int(vert_of_loop[li])
        v1 = int(vert_of_loop[int(next_loop[li])])
        edge_ends.setdefault(e, []).append((p, v0, v1, uvs[li], uvs[int(next_loop[li])]))

    parent = np.arange(n_polys, dtype=np.int64)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    eps = 1e-6
    for ends in edge_ends.values():
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                pi, a0, a1, ua0, ua1 = ends[i]
                pj, b0, b1, ub0, ub1 = ends[j]
                if pi == pj:
                    continue
                # align both loops on the same start vertex
                if a0 == b0:
                    same = (abs(ua0[0] - ub0[0]) < eps and abs(ua0[1] - ub0[1]) < eps
                            and abs(ua1[0] - ub1[0]) < eps and abs(ua1[1] - ub1[1]) < eps)
                elif a0 == b1:
                    same = (abs(ua0[0] - ub1[0]) < eps and abs(ua0[1] - ub1[1]) < eps
                            and abs(ua1[0] - ub0[0]) < eps and abs(ua1[1] - ub0[1]) < eps)
                else:
                    same = False
                if same:
                    ri, rj = find(pi), find(pj)
                    if ri != rj:
                        parent[ri] = rj
    return len({find(i) for i in range(n_polys)})


def uv_area_sum(mesh, uv_layer):
    me = mesh
    n_loops = len(me.loops)
    uvs = np.empty((n_loops, 2), dtype=np.float64)
    uv_layer.data.foreach_get("uv", uvs.ravel())
    n_polys = len(me.polygons)
    starts = np.empty(n_polys, dtype=np.int64)
    totals = np.empty(n_polys, dtype=np.int64)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    area = 0.0
    for s, t in zip(starts.tolist(), totals.tolist()):
        loop_idx = np.arange(s, s + t)
        tri = uvs[loop_idx]
        x = tri[:, 0]
        y = tri[:, 1]
        area += 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return float(area)


def uv_bbox(mesh, uv_layer):
    n_loops = len(mesh.loops)
    uvs = np.empty((n_loops, 2), dtype=np.float64)
    uv_layer.data.foreach_get("uv", uvs.ravel())
    return [float(uvs[:, 0].min()), float(uvs[:, 1].min()),
            float(uvs[:, 0].max()), float(uvs[:, 1].max())]


def distortion_stats(mesh, uv_layer):
    """Per-face texel-density consistency: scale = sqrt(uv_area / 3d_area)."""
    me = mesh
    n_polys = len(me.polygons)
    n_loops = len(me.loops)
    uvs = np.empty((n_loops, 2), dtype=np.float64)
    uv_layer.data.foreach_get("uv", uvs.ravel())
    starts = np.empty(n_polys, dtype=np.int64)
    totals = np.empty(n_polys, dtype=np.int64)
    areas3d = np.empty(n_polys, dtype=np.float64)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)
    me.polygons.foreach_get("area", areas3d)

    uv_area = np.empty(n_polys, dtype=np.float64)
    for pi in range(n_polys):
        s, t = int(starts[pi]), int(totals[pi])
        tri = uvs[s:s + t]
        x, y = tri[:, 0], tri[:, 1]
        uv_area[pi] = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

    ok = (areas3d > 1e-12) & (uv_area > 1e-16)
    scale = np.sqrt(uv_area[ok] / areas3d[ok])
    if not len(scale):
        return {}
    med = float(np.median(scale))
    ratio = scale / med
    return {
        "faces_evaluated": int(ok.sum()),
        "faces_degenerate_uv": int((~ok).sum()),
        "texel_scale_median": round(med, 6),
        "density_cv": round(float(np.std(ratio)), 4),
        "density_p05": round(float(np.percentile(ratio, 5)), 4),
        "density_p95": round(float(np.percentile(ratio, 95)), 4),
        "density_p95_over_p05": round(float(np.percentile(ratio, 95) / max(np.percentile(ratio, 5), 1e-9)), 3),
    }


def stats(obj):
    me = obj.data
    uv = me.uv_layers.active
    t0 = time.time()
    islands = uv_island_count(me, uv)
    t_islands = time.time() - t0
    return {
        "verts": len(me.vertices),
        "edges": len(me.edges),
        "faces": len(me.polygons),
        "loops": len(me.loops),
        "uv_islands": int(islands),
        "uv_area_sum": round(uv_area_sum(me, uv), 6),
        "uv_bbox": [round(v, 4) for v in uv_bbox(me, uv)],
        "island_count_s": round(t_islands, 2),
        "distortion": distortion_stats(me, uv),
    }


def add_checker_material(obj, scale=40.0):
    mat = bpy.data.materials.new("uv_checker")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexChecker")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Color1"].default_value = (0.05, 0.05, 0.06, 1.0)
    tex.inputs["Color2"].default_value = (0.95, 0.55, 0.10, 1.0)
    nt.links.new(coord.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def setup_render(scene, res=900, samples=16):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.02, 0.02, 1)
    scene.world = world


def frame_object(cam_obj, obj, angle_deg=0.0, margin=1.25):
    import mathutils
    bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    center = sum(bbox, mathutils.Vector()) / 8.0
    radius = max((v - center).length for v in bbox)
    dist = radius * margin / math.tan(cam_obj.data.angle / 2.0)
    a = math.radians(angle_deg)
    cam_obj.location = center + mathutils.Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.12 * dist))
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main():
    args = arg_after_dashes()
    in_obj = args[0]
    out_dir = args[1]
    margin = float(args[2]) if len(args) > 2 else 0.001
    no_pack = len(args) > 3 and args[3] == "nopack"
    os.makedirs(out_dir, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    t0 = time.time()
    bpy.ops.wm.obj_import(filepath=in_obj)
    import_s = time.time() - t0
    meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("no mesh imported")
    if len(meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    print(f"[import] objects={len(meshes)} faces={len(obj.data.polygons)} in {import_s:.2f}s", flush=True)

    before = stats(obj)
    print("[stats] before pack " + json.dumps(before), flush=True)

    if no_pack:
        out = {"input": in_obj, "before": before, "packed": False}
        with open(os.path.join(out_dir, "blender_stats.json"), "w") as fh:
            json.dump(out, fh, indent=2)
        print("[done] nopack " + json.dumps(before), flush=True)
        return

    t0 = time.time()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    pack_s = time.time() - t0

    after = stats(obj)
    after["pack_s"] = round(pack_s, 2)
    after["import_s"] = round(import_s, 2)
    print("[stats] after pack " + json.dumps(after), flush=True)

    packed_path = os.path.join(out_dir, "final_packed.obj")
    t0 = time.time()
    bpy.ops.wm.obj_export(filepath=packed_path, export_selected_objects=True,
                          export_materials=False, export_normals=False,
                          export_uv=True, export_triangulated_mesh=False)
    print(f"[export] {packed_path} in {time.time()-t0:.2f}s", flush=True)

    # checker renders
    add_checker_material(obj)
    scene = bpy.context.scene
    setup_render(scene)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.angle = math.radians(35)
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    renders = []
    for name, ang in (("uv_checker_front.png", 0.0), ("uv_checker_side.png", 70.0)):
        frame_object(cam, obj, ang)
        scene.render.filepath = os.path.join(out_dir, name)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        renders.append({"file": name, "render_s": round(time.time() - t0, 2)})
        print(f"[render] {name} {renders[-1]['render_s']}s", flush=True)

    out = {"input": in_obj, "margin": margin, "before": before, "after": after,
           "packed_obj": packed_path, "renders": renders}
    with open(os.path.join(out_dir, "blender_stats.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print("[done] " + json.dumps({k: out[k] for k in ("before", "after")}), flush=True)


if __name__ == "__main__":
    main()