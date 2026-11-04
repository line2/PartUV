"""Bake the source mesh's base color onto a PartUV result (new UVs) and export a textured OBJ.

PartUV normalizes vertices in memory ((v-c)*0.9/max_extent+0.5) before writing
final_components.obj, so the result sits in a different coordinate frame than the original
model. We invert that exact transform (using the decimated mesh bbox) to bring it back.

Colour transfer avoids ray casting entirely:
  1. copy the target, drop its UVs, DataTransfer the *source* UVs onto it (nearest face,
     interpolated),
  2. copy those per-loop UVs back onto the target as a second layer "srcUV",
  3. EMIT-bake a material that samples Image_0.png through "srcUV" into an image laid out
     with the target's new packed UVs.

Usage:
  blender -b --factory-startup --python partuv_bake_color.py -- \
      <source_with_texture.obj> <target_partuv.obj> <decimated_ref.obj> <out_dir> [res]
"""
import bpy
import os
import sys

import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
src_obj, tgt_obj, ref_obj, out_dir = args[0], args[1], args[2], args[3]
res = int(args[4]) if len(args) > 4 else 3072
uv_npz = args[5] if len(args) > 5 else None
tex_override = args[6] if len(args) > 6 else None
pack_margin = float(args[7]) if len(args) > 7 else 0.0
model_space = (args[8] == "1") if len(args) > 8 else False
os.makedirs(out_dir, exist_ok=True)

MESH_SCALE = 0.9  # PartField run_inference normalization


def import_mesh(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not new:
        raise RuntimeError(f"no mesh in {path}")
    if len(new) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in new:
            o.select_set(True)
        bpy.context.view_layer.objects.active = new[0]
        bpy.ops.object.join()
        return bpy.context.view_layer.objects.active
    return new[0]


def bbox(o):
    vs = np.empty(len(o.data.vertices) * 3, dtype=np.float64)
    o.data.vertices.foreach_get("co", vs)
    vs = vs.reshape(-1, 3)
    return vs.min(0), vs.max(0)


def read_loop_uvs(o, layer_index=0):
    me = o.data
    uvl = me.uv_layers[layer_index]
    n = len(me.loops)
    flat = np.empty(n * 2, dtype=np.float64)
    uvl.data.foreach_get("uv", flat)
    return flat.reshape(-1, 2)


bpy.ops.wm.read_factory_settings(use_empty=True)

# --- reference bbox (the decimated mesh PartUV consumed) -> invert its normalization ---
ref = import_mesh(ref_obj)
rmin, rmax = bbox(ref)
center = (rmin + rmax) * 0.5
extent = float((rmax - rmin).max())
scale = MESH_SCALE / extent
print(f"[ref] center={center.round(4)} extent={extent:.4f} scale={scale:.6f}", flush=True)
bpy.data.objects.remove(ref, do_unlink=True)

tgt = import_mesh(tgt_obj)
co = np.empty(len(tgt.data.vertices) * 3, dtype=np.float64)
tgt.data.vertices.foreach_get("co", co)
if not model_space:
    co = (co.reshape(-1, 3) - 0.5) / scale + center
tgt.data.vertices.foreach_set("co", co.ravel())
tgt.data.update()
tmin, tmax = bbox(tgt)
print(f"[target] verts={len(tgt.data.vertices)} faces={len(tgt.data.polygons)} "
      f"restored bbox {tmin.round(3)} .. {tmax.round(3)} uv_layers="
      f"{[l.name for l in tgt.data.uv_layers]}", flush=True)

src = import_mesh(src_obj)
smin, smax = bbox(src)
print(f"[source] verts={len(src.data.vertices)} bbox {smin.round(3)} .. {smax.round(3)} "
      f"mats={[m.name for m in src.data.materials]}", flush=True)

# --- 1. per-vertex source UVs (precomputed by partuv_transfer_uv.py: KD-tree + barycentric) ---
if not uv_npz or not os.path.exists(uv_npz):
    raise RuntimeError("uv_npz with transferred source UVs is required")
src_uv_vert = np.load(uv_npz)["uv"]
if src_uv_vert.shape[0] != len(tgt.data.vertices):
    raise RuntimeError(f"uv npz has {src_uv_vert.shape[0]} rows, target has "
                       f"{len(tgt.data.vertices)} verts")

# --- 2. put those UVs on the target as a second layer ---
tgt_uv_layers = tgt.data.uv_layers
packed_name = tgt_uv_layers[0].name
src_layer = tgt_uv_layers.new(name="srcUV")
n_loops = len(tgt.data.loops)
loop_vert = np.empty(n_loops, dtype=np.int64)
tgt.data.loops.foreach_get("vertex_index", loop_vert)
src_uv = src_uv_vert[loop_vert]
src_layer.data.foreach_set("uv", src_uv.ravel())
tgt.data.update()
# baking lays texels out in the *active render* UV layer -> force the packed one
packed_layer = tgt.data.uv_layers[packed_name]
tgt.data.uv_layers.active = packed_layer
packed_layer.active_render = True
src_layer.active_render = False
print(f"[uv] target layers now {[l.name for l in tgt.data.uv_layers]} (packed={packed_name}, "
      f"active_render={tgt.data.uv_layers.active_render.name}) "
      f"srcUV range {src_uv.min(0).round(3)} .. {src_uv.max(0).round(3)}", flush=True)

# --- 3. pack the charts (final_components.obj is unpacked: every chart sits in a unit square) ---
bpy.ops.object.select_all(action="DESELECT")
tgt.select_set(True)
bpy.context.view_layer.objects.active = tgt
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.select_all(action="SELECT")
bpy.ops.uv.pack_islands(margin=pack_margin)
bpy.ops.object.mode_set(mode="OBJECT")
print(f"[pack] islands packed, active uv={tgt.data.uv_layers.active.name}", flush=True)

# --- 4. material: source texture through srcUV -> emission, bake into packed-UV image ---
img = bpy.data.images.new("baked_basecolor", width=res, height=res, alpha=False)
img.colorspace_settings.name = "sRGB"

src_img = None
for m in src.data.materials:
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image is not None:
            src_img = n.image
            break
    if src_img:
        break
if src_img is None:
    raise RuntimeError("no texture found on source material")
if tex_override:
    src_img = bpy.data.images.load(tex_override, check_existing=True)
    src_img.colorspace_settings.name = "sRGB"
    print(f"[tex] override supplied: {tex_override}", flush=True)
print(f"[tex] source image {src_img.name} {tuple(src_img.size)}", flush=True)

mat = bpy.data.materials.new("partuv_baked")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
emit = nt.nodes.new("ShaderNodeEmission")
tex_src = nt.nodes.new("ShaderNodeTexImage")
tex_src.image = src_img
uv_src = nt.nodes.new("ShaderNodeUVMap")
uv_src.uv_map = "srcUV"
bake_target = nt.nodes.new("ShaderNodeTexImage")
bake_target.image = img
uv_packed = nt.nodes.new("ShaderNodeUVMap")
uv_packed.uv_map = packed_name

nt.links.new(uv_src.outputs["UV"], tex_src.inputs["Vector"])
nt.links.new(tex_src.outputs["Color"], emit.inputs["Color"])
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
nt.links.new(uv_packed.outputs["UV"], bake_target.inputs["Vector"])

tgt.data.materials.clear()
tgt.data.materials.append(mat)
nt.nodes.active = bake_target
bake_target.select = True

# --- 4. EMIT bake ---
bpy.ops.object.select_all(action="DESELECT")
tgt.select_set(True)
bpy.context.view_layer.objects.active = tgt
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.render.bake.use_pass_direct = False
scene.render.bake.use_pass_indirect = False
scene.render.bake.use_selected_to_active = False
scene.render.bake.margin = 16

print(f"[bake] {res}x{res} EMIT", flush=True)
bpy.ops.object.bake(type="EMIT")

px = np.empty(res * res * 4, dtype=np.float32)
img.pixels.foreach_get(px)
rgb = px.reshape(res, res, 4)[:, :, :3]
nz = rgb.sum(2) > 0.02
ys, xs = np.nonzero(nz)
print(f"[bake] buffer mean={rgb.reshape(-1,3).mean(0).round(4)} std={rgb.reshape(-1,3).std(0).round(4)} "
      f"nonblack={nz.mean():.3f}", flush=True)
if len(xs):
    print(f"[bake] nonblack bbox x {xs.min()}..{xs.max()} y {ys.min()}..{ys.max()}", flush=True)

img.filepath_raw = os.path.join(out_dir, "baked_basecolor.png")
img.file_format = "PNG"
img.save()
img.reload()
print(f"[bake] saved {img.filepath_raw}", flush=True)

# --- 5. swap in an exportable Principled material that uses the baked map ---
mat2 = bpy.data.materials.new("partuv_colored")
mat2.use_nodes = True
nt2 = mat2.node_tree
nt2.nodes.clear()
out2 = nt2.nodes.new("ShaderNodeOutputMaterial")
bsdf2 = nt2.nodes.new("ShaderNodeBsdfPrincipled")
tex2 = nt2.nodes.new("ShaderNodeTexImage")
tex2.image = img
tex2.interpolation = "Linear"
uv2 = nt2.nodes.new("ShaderNodeUVMap")
uv2.uv_map = packed_name
nt2.links.new(uv2.outputs["UV"], tex2.inputs["Vector"])
nt2.links.new(tex2.outputs["Color"], bsdf2.inputs["Base Color"])
nt2.links.new(bsdf2.outputs["BSDF"], out2.inputs["Surface"])
tgt.data.materials.clear()
tgt.data.materials.append(mat2)
nt2.nodes.active = tex2
tex2.select = True

# --- 6. export textured OBJ ---
bpy.ops.object.select_all(action="DESELECT")
tgt.select_set(True)
bpy.context.view_layer.objects.active = tgt
obj_path = os.path.join(out_dir, "partuv_colored.obj")
bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True,
                      export_materials=True, export_normals=True, export_uv=True,
                      export_triangulated_mesh=False, path_mode="RELATIVE")
print(f"[export] {obj_path}", flush=True)

