#include "prof.h"
#include "CuMeshSimplifier.h"

#ifdef PARTUV_HAS_CUDA
#include "cusimp.h"
#define CUDA_API_PER_THREAD_DEFAULT_STREAM
#include <cuda_runtime.h>
#include <vector>
#include <unordered_map>
#include <iostream>
#include <unordered_set>


#include <easy/profiler.h>


using cusimp::Vertex;
using cusimp::Triangle;
using cusimp::Edge;

// ‑‑‑‑ helper: largest bbox edge ------------------------------------------------
static float bbox_max_extent(const Eigen::MatrixXf &V)
{
    auto minv = V.colwise().minCoeff();
    auto maxv = V.colwise().maxCoeff();
    return (maxv - minv).maxCoeff();
}

// ‑‑‑‑ helper: boundary edges ---------------------------------------------------
static std::vector<Edge<int>>
boundary_edges_from_faces(const std::vector<Triangle<int>> &F)
{
    struct H { size_t operator()(const std::pair<int,int>& p) const noexcept
               { return (size_t(p.first) << 32) ^ size_t(p.second); } };

    std::unordered_map<std::pair<int,int>,int,H> cnt;  cnt.reserve(F.size()*3);

    auto add=[&](int a,int b){ if(a>b) std::swap(a,b); ++cnt[{a,b}]; };
    for(auto &t:F){ add(t.i,t.j); add(t.j,t.k); add(t.k,t.i); }

    std::vector<Edge<int>> E;  E.reserve(cnt.size());
    for(auto &kv:cnt) if(kv.second==1) E.push_back({kv.first.first,kv.first.second});
    return E;
}

// ‑‑‑‑ helper: boundary vertices -------------------------------------------------
static std::vector<int>
get_boundary_vertices(const std::vector<Edge<int>> &E)
{
    std::unordered_set<int> boundary_vertices;
    for(auto &e:E)
    {
        boundary_vertices.insert(e.u);
        boundary_vertices.insert(e.v);
    }
    return std::vector<int>(boundary_vertices.begin(),boundary_vertices.end());
}

// ‑‑‑‑ helper: copy device→host --------------------------------------------------
template<class T>
static std::vector<T> d2h(const T* d,size_t n, cudaStream_t stream)
{
    std::vector<T> h(n);
    cudaMemcpyAsync(h.data(),d,n*sizeof(T),cudaMemcpyDeviceToHost, stream);
    return h;
}

// ‑‑‑‑ public interface ---------------------------------------------------------
std::pair<Eigen::MatrixXf,Eigen::MatrixXi>
CuMeshSimplifier::simplify(const Eigen::MatrixXf& V_in,
                           const Eigen::MatrixXi& F_in,
                           float threshold,
                           int   max_iter,
                           cudaStream_t stream)
{
    // copy – we promise "not in‑place"
    Eigen::MatrixXf V = V_in;
    Eigen::MatrixXi F = F_in;

    // centre the mesh like PaSP.preprocess_mesh
    Eigen::Vector3f mean = V.colwise().mean();
    V.rowwise() -= mean.transpose();
    float scale = bbox_max_extent(V);

    // convert to cusimp host vectors
    std::vector<Vertex<float>> verts(V.rows());
    for(int i=0;i<V.rows();++i) verts[i]={V(i,0),V(i,1),V(i,2)};

    std::vector<Triangle<int>> faces(F.rows());
    for(int i=0;i<F.rows();++i) faces[i]={F(i,0),F(i,1),F(i,2)};

    cusimp::CUSimp sp;
    bool init=true;
    EASY_BLOCK("Simplify",profiler::colors::Grey);

    auto boundary = boundary_edges_from_faces(faces);
    auto fixed_vertices = get_boundary_vertices(boundary);
    EASY_BLOCK("mallocHost",profiler::colors::White);

    int* d_fixed_vertices;
    Vertex<float>*  d_v; Triangle<int>* d_f; Edge<int>* d_e;
    cudaMallocHost(&d_v, verts.size()*sizeof(Vertex<float>));
    cudaMallocHost(&d_f, faces.size()*sizeof(Triangle<int>));
    // cudaMallocHost(&d_e, boundary.size()*sizeof(Edge<int>));
    cudaMallocHost(&d_fixed_vertices, fixed_vertices.size()*sizeof(int));
    EASY_END_BLOCK;
    for(int it=0; it<max_iter; ++it)
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
    EASY_END_BLOCK;
    // convert back to Eigen & un‑centre
    Eigen::MatrixXf V_out(verts.size(),3);
    for(int i=0;i<V_out.rows();++i)
    {
        V_out.row(i) << verts[i].x,verts[i].y,verts[i].z;
    }
    V_out.rowwise() += mean.transpose();

    Eigen::MatrixXi F_out(faces.size(),3);
    for(int i=0;i<F_out.rows();++i)
    {
        F_out(i,0)=faces[i].i; F_out(i,1)=faces[i].j; F_out(i,2)=faces[i].k;
    }

    cudaFreeHost(d_v);
    cudaFreeHost(d_f);
    cudaFreeHost(d_fixed_vertices);

    // cudaStreamDestroy(stream); // Cleanup
    return {V_out,F_out};
}

#else   // !PARTUV_HAS_CUDA ------------------------------------------------
// CPU build: the CUDA PAMO path is not compiled in.  Component.cpp checks the
// flag before calling this, so reaching here is a programming error.
#include <stdexcept>

namespace CuMeshSimplifier {
std::pair<Eigen::MatrixXf, Eigen::MatrixXi>
simplify(const Eigen::MatrixXf &, const Eigen::MatrixXi &, float, int, cudaStream_t) {
    throw std::runtime_error(
        "partuv was built without CUDA: unwrap.pamo_backend=\"\" is unavailable. "
        "Use pamo_backend: \"none\" (default), \"cluster\", or rebuild with "
        "-DPARTUV_ENABLE_CUDA=ON on a CUDA host.");
}
}  // namespace CuMeshSimplifier

#endif  // PARTUV_HAS_CUDA
