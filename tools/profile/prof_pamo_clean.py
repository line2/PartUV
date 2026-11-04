#!/usr/bin/env python3
"""Restore CuMeshSimplifier.cpp, re-apply the cudaFreeHost fix, and instrument the
PAMO loop with non-overlapping (brace-scoped) timers."""
import subprocess
import sys

REPO = "${PARTUV_WORK}/PartUV"
p = f"{REPO}/src/CuMeshSimplifier.cpp"

subprocess.run(["git", "checkout", "--", "src/CuMeshSimplifier.cpp"], cwd=REPO, check=True)
s = open(p, encoding="utf-8").read()
print("restored pristine file")

# --- 1. cudaFreeHost fix (was lost by the checkout) -----------------------------
old_free = "    // cudaStreamDestroy(stream); // Cleanup\n    return {V_out,F_out};"
new_free = ("    cudaFreeHost(d_v);\n    cudaFreeHost(d_f);\n    cudaFreeHost(d_fixed_vertices);\n\n"
            "    // cudaStreamDestroy(stream); // Cleanup\n    return {V_out,F_out};")
if old_free not in s:
    print("!! free anchor missing"); sys.exit(1)
s = s.replace(old_free, new_free, 1)

# --- 2. instrument the loop ----------------------------------------------------
start_marker = "    for(int it=0; it<max_iter; ++it)\n    {\n        boundary = boundary_edges_from_faces(faces);"
end_marker = ("        faces.swap(faces_new);\n        init=false;\n"
              "        // std::cout << \"iter: \" << it << \" faces: \" << faces.size() << std::endl;\n"
              "        // cudaFree(d_v); cudaFree(d_f); cudaFree(d_e);\n    }\n")

i = s.index(start_marker)
j = s.index(end_marker, i) + len(end_marker)
old_block = s[i:j]

new_block = '''    for(int it=0; it<max_iter; ++it)
    {
        prof::add_work("pamo.iter", 1);

        {
            prof::Scope _pb("pamo.boundary");
            boundary = boundary_edges_from_faces(faces);
            fixed_vertices = get_boundary_vertices(boundary);
        }

        {
            prof::Scope _pm("pamo.h2d");
            std::memcpy(d_v,verts.data(),verts.size()*sizeof(Vertex<float>));
            std::memcpy(d_f,faces.data(),faces.size()*sizeof(Triangle<int>));
            std::memcpy(d_fixed_vertices, fixed_vertices.data(), fixed_vertices.size()*sizeof(int));
        }

        {
            prof::Scope _pk("pamo.kernel");
            if (stream == nullptr) {
                sp.forward(d_v,d_f,d_e,d_fixed_vertices,
                           int(verts.size()), int(faces.size()), int(boundary.size()),
                           int(fixed_vertices.size()),
                           scale,threshold,init);
            } else {
                sp.forward(d_v,d_f,d_e,d_fixed_vertices,
                           int(verts.size()), int(faces.size()), int(boundary.size()),
                           int(fixed_vertices.size()),
                           scale,threshold,init, stream);
            }
        }

        {
            prof::Scope _ps("pamo.sync");
            cudaStreamSynchronize(stream);
        }

        decltype(d2h(sp.pts_occ, sp.n_pts, stream)) occ, map;
        decltype(d2h(sp.points, sp.n_pts, stream))  v;
        decltype(d2h(sp.triangles, sp.n_tris, stream)) f;
        {
            prof::Scope _pd("pamo.d2h");
            occ = d2h(sp.pts_occ, sp.n_pts, stream);
            map = d2h(sp.pts_map, sp.n_pts, stream);
            v   = d2h(sp.points , sp.n_pts, stream);
            f   = d2h(sp.triangles, sp.n_tris, stream);
        }

        bool converged = false;
        {
            prof::Scope _ph("pamo.host");
            std::vector<Triangle<int>> faces_new;
            faces_new.reserve(f.size());
            for(auto &t:f) if(t.i>=0)
                faces_new.push_back({map[t.i],map[t.j],map[t.k]});

            std::vector<Vertex<float>> verts_new;
            verts_new.reserve(verts.size());
            for(size_t k=0;k<v.size();++k) if(occ[k]) verts_new.push_back(v[k]);

            if(faces_new.size()==faces.size())
            {
                converged = true;
            }
            else
            {
                verts.swap(verts_new);
                faces.swap(faces_new);
                init=false;
            }
        }
        if (converged) break;
    }
'''

s = s[:i] + new_block + s[j:]
if '#include "prof.h"' not in s:
    k = s.index("#include")
    s = s[:k] + '#include "prof.h"\n' + s[k:]
open(p, "w", encoding="utf-8").write(s)
print("loop instrumented cleanly")