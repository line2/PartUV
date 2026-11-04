"""Locate the distortion tail: are bad faces concentrated at chart boundaries?"""
import os
from collections import defaultdict

import numpy as np

import sys
sys.path.insert(0, "${PARTUV_WORK}/scripts")
from partuv_uv_audit import load_obj, face_frame  # noqa: E402

OBJ = os.environ.get("PARTUV_EVAL_OBJ", "partuv_colored.obj")
V, VT, F, FT = load_obj(OBJ)
nF = len(F)
P, Q = V[F], VT[FT]

a3 = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
uv_a = 0.5 * ((Q[:, 1, 0] - Q[:, 0, 0]) * (Q[:, 2, 1] - Q[:, 0, 1]) -
              (Q[:, 2, 0] - Q[:, 0, 0]) * (Q[:, 1, 1] - Q[:, 0, 1]))
uv_abs = np.abs(uv_a)
tol = 1e-6 * float(np.median(a3))
ratio = uv_abs / np.maximum(a3, tol)
rho = ratio / (uv_abs.sum() / a3.sum())
d = np.where(rho >= 1, rho, 1 / np.maximum(rho, 1e-30))

# --- boundary faces: a face owning a UV edge that no other face uses ---------------
uv_edge = defaultdict(list)
for f in range(nF):
    a, b, c = FT[f]
    for e in ((a, b), (b, c), (c, a)):
        uv_edge[(min(e), max(e))].append(f)
boundary = np.zeros(nF, bool)
for faces in uv_edge.values():
    if len(faces) == 1:
        boundary[faces[0]] = True

valid = (a3 > tol) & (uv_abs > 0)
base_b = boundary[valid].mean()
print(f"faces valid={valid.sum():,}  boundary faces={boundary[valid].sum():,} ({base_b*100:.1f}%)")

print(f"{'band':>12} {'faces':>8} {'%all':>6} {'boundary%':>10} {'area%':>7} {'lift':>5}")
for lo, hi in ((1.0, 1.25), (1.25, 1.5), (1.5, 2.0), (2.0, 5.0), (5.0, 1e12)):
    m = valid & (d >= lo) & (d < hi)
    if m.sum() == 0:
        continue
    b = boundary[m].mean()
    print(f"{lo:>5.2f}-{hi:<6.2f} {m.sum():>8,} {m.sum()/valid.sum()*100:>5.1f}% "
          f"{b*100:>9.1f}% {a3[m].sum()/a3[valid].sum()*100:>6.2f}% {b/base_b:>5.2f}x")

# --- how much 3D area sits in charts whose median is bad vs in the tail itself -----
hi = valid & (d > 2.0)
print(f"\n尾部分布: >2.0 -> {hi.sum():,} faces, {a3[hi].sum()/a3[valid].sum()*100:.2f}% of 3D area")
print(f"          >10  -> {(valid & (d > 10)).sum():,} faces, "
      f"{a3[valid & (d > 10)].sum()/a3[valid].sum()*100:.3f}% of 3D area")
np.save(os.environ.get("PARTUV_BAD_FACES", "bad_faces.npy"),
        np.where(valid & (d > 2.0))[0].astype(np.int32))