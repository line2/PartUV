"""Pack a PartUV result at several margins and report coverage.

Usage: blender -b -P pack_margin_curve.py -- <obj> <px> [<px> ...]
Margin is given in texels at 4096 and converted to UV units.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
path, pxs = argv[0], [float(x) for x in argv[1:]] or [2.0]
TEX = 4096.0


def coverage(obj):
    uvl = obj.data.uv_layers.active
    area = 0.0
    for poly in obj.data.polygons:
        us = [tuple(uvl.data[li].uv) for li in poly.loop_indices]
        acc = 0.0
        for i in range(len(us)):
            x1, y1 = us[i]
            x2, y2 = us[(i + 1) % len(us)]
            acc += x1 * y2 - x2 * y1
        area += abs(acc) * 0.5
    return area


def islands(obj):
    me = obj.data
    uvl = me.uv_layers.active
    parent = list(range(len(me.polygons)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    loop_vert = [l.vertex_index for l in me.loops]
    edges = {}
    for poly in me.polygons:
        ls = list(poly.loop_indices)
        n = len(ls)
        for i in range(n):
            l1, l2 = ls[i], ls[(i + 1) % n]
            v1, v2 = loop_vert[l1], loop_vert[l2]
            key = (v1, v2) if v1 < v2 else (v2, v1)
            edges.setdefault(key, []).append(
                (poly.index, {v1: tuple(uvl.data[l1].uv), v2: tuple(uvl.data[l2].uv)}))
    for key, occ in edges.items():
        if len(occ) != 2:
            continue
        (pa, ua), (pb, ub) = occ
        if all(abs(ua[v][0] - ub[v][0]) < 1e-6 and abs(ua[v][1] - ub[v][1]) < 1e-6 for v in key):
            union(pa, pb)
    return len({find(i) for i in range(len(me.polygons))})


print(f"[pack] {path}", flush=True)
for px in pxs:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    margin = px / TEX
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin, rotate=True, scale=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    cov = coverage(obj)
    print(f"[pack]   margin {px:4.1f}px ({margin:.6f}) -> coverage {cov*100:6.2f}%  "
          f"{cov*TEX*TEX/1e6:5.2f} M texels  islands {islands(obj)}", flush=True)