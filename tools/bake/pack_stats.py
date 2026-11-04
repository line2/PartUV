"""Pack a PartUV result and report island count + texture coverage."""
import os
import sys

import bpy

path = sys.argv[sys.argv.index("--") + 1]
margin = float(sys.argv[sys.argv.index("--") + 2]) if len(sys.argv) > sys.argv.index("--") + 2 else 0.0039

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=path)
obj = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]

uvl = obj.data.uv_layers.active
us = [d.uv[0] for d in uvl.data]
vs = [d.uv[1] for d in uvl.data]
print(f"[pack] raw uv: u [{min(us):.2f},{max(us):.2f}] v [{min(vs):.2f},{max(vs):.2f}]", flush=True)

bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.pack_islands(margin=margin, rotate=True, scale=True)
bpy.ops.object.mode_set(mode="OBJECT")

area = 0.0
for poly in obj.data.polygons:
    pts = [tuple(uvl.data[li].uv) for li in poly.loop_indices]
    acc = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        acc += x1 * y2 - x2 * y1
    area += abs(acc) * 0.5

print(f"[pack] {path}", flush=True)
print(f"[pack]   coverage {area*100:.2f}%   ({area*4096*4096/1e6:.2f} M texels @4096)", flush=True)