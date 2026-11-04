"""Re-pack a PartUV OBJ with Blender's Pack Islands and write the result back out.

Usage: blender -b -P pack_to_obj.py -- <in.obj> <out.obj> <margin_px> [tex_size]
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
margin_px = float(argv[2]) if len(argv) > 2 else 4.0
tex = float(argv[3]) if len(argv) > 3 else 4096.0
margin = margin_px / tex

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=src)
obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]

uvl = obj.data.uv_layers.active
us = [d.uv[0] for d in uvl.data]
vs = [d.uv[1] for d in uvl.data]
print(f"[pack] in  uv range u [{min(us):.3f},{max(us):.3f}] v [{min(vs):.3f},{max(vs):.3f}]")
print(f"[pack] mesh {len(obj.data.vertices)} verts {len(obj.data.polygons)} faces")

bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.pack_islands(margin=margin, rotate=True, scale=True)
bpy.ops.object.mode_set(mode="OBJECT")

uvl = obj.data.uv_layers.active
us = [d.uv[0] for d in uvl.data]
vs = [d.uv[1] for d in uvl.data]

area = 0.0
for poly in obj.data.polygons:
    pts = [tuple(uvl.data[li].uv) for li in poly.loop_indices]
    acc = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        acc += x1 * y2 - x2 * y1
    area += abs(acc) * 0.5

print(f"[pack] out uv range u [{min(us):.3f},{max(us):.3f}] v [{min(vs):.3f},{max(vs):.3f}]")
print(f"[pack] margin {margin_px:.1f}px ({margin:.6f}) -> coverage {area*100:.2f}%  "
      f"({area*tex*tex/1e6:.2f} M texels)")

bpy.ops.wm.obj_export(filepath=dst, export_uv=True, export_normals=False,
                      export_materials=False, export_selected_objects=True)
print(f"[pack] wrote {dst}")