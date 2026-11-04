#include "igl_unwrap.h"

#include <igl/arap.h>
#include <igl/boundary_loop.h>
#include <igl/flipped_triangles.h>
#include <igl/harmonic.h>
#include <igl/lscm.h>
#include <igl/slim.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace igl_unwrap {
namespace {

/// Label the connected components of the vertex graph induced by F.
int vertex_components(const Eigen::MatrixXi &F, Eigen::VectorXi &label) {
    int nv = 0;
    for (int f = 0; f < F.rows(); ++f)
        nv = std::max(nv, static_cast<int>(std::max({F(f, 0), F(f, 1), F(f, 2)})) + 1);

    std::vector<std::vector<int>> adj(static_cast<size_t>(nv));
    for (int f = 0; f < F.rows(); ++f) {
        const int a = F(f, 0), b = F(f, 1), c = F(f, 2);
        adj[a].push_back(b); adj[b].push_back(a);
        adj[b].push_back(c); adj[c].push_back(b);
        adj[c].push_back(a); adj[a].push_back(c);
    }

    label = Eigen::VectorXi::Constant(nv, -1);
    int ncomp = 0;
    std::vector<int> stack;
    for (int s = 0; s < nv; ++s) {
        if (label(s) >= 0) continue;
        label(s) = ncomp;
        stack.assign(1, s);
        while (!stack.empty()) {
            const int v = stack.back();
            stack.pop_back();
            for (int w : adj[v]) {
                if (label(w) < 0) {
                    label(w) = ncomp;
                    stack.push_back(w);
                }
            }
        }
        ++ncomp;
    }
    return ncomp;
}

}  // namespace

int flatten(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, Eigen::MatrixXd &UV,
            const std::string &method, int iters) {
    UV.resize(0, 2);
    const bool dbg = std::getenv("PARTUV_IGL_DEBUG") != nullptr;
    if (V.rows() < 4 || F.rows() < 2) return -1;

    Eigen::VectorXi boundary;
    igl::boundary_loop(F, boundary);
    if (boundary.size() < 3) {
        // closed chart: nothing to pin, exactly where abf_unwrap gives up too
        if (dbg) std::fprintf(stderr, "[igl] closed chart (F=%d), deferring\n", (int)F.rows());
        return -2;
    }

    // ---- pins: two per connected component, preferring boundary vertices --------------
    Eigen::VectorXi comp;
    const int ncomp = vertex_components(F, comp);
    if (ncomp < 1) return -1;

    std::vector<char> on_boundary(static_cast<size_t>(V.rows()), 0);
    for (int i = 0; i < boundary.size(); ++i) on_boundary[boundary(i)] = 1;

    std::vector<std::vector<int>> cand(static_cast<size_t>(ncomp));
    std::vector<std::vector<int>> all(static_cast<size_t>(ncomp));
    for (int v = 0; v < V.rows(); ++v) {
        all[comp(v)].push_back(v);
        if (on_boundary[v]) cand[comp(v)].push_back(v);
    }
    for (int c = 0; c < ncomp; ++c)
        if (cand[c].empty()) cand[c] = all[c];   // closed component inside an open chart

    std::vector<int> pins;
    std::vector<Eigen::RowVector2d> pin_uv;
    for (int c = 0; c < ncomp; ++c) {
        const auto &pool = cand[c];
        if (pool.size() < 2) return -1;

        int i0 = pool[0];
        const Eigen::RowVector3d seed = V.row(pool[0]);
        double best = -1.0;
        for (int v : pool) {                       // farthest from an arbitrary seed
            const double d = (V.row(v) - seed).squaredNorm();
            if (d > best) { best = d; i0 = v; }
        }
        int i1 = -1;
        best = -1.0;
        for (int v : pool) {                       // farthest from i0
            if (v == i0) continue;
            const double d = (V.row(i0) - V.row(v)).squaredNorm();
            if (d > best) { best = d; i1 = v; }
        }
        if (i1 < 0 || best <= 1e-24) return -1;

        const double span = std::sqrt(best);
        pins.push_back(i0);
        pins.push_back(i1);
        pin_uv.emplace_back(0.0, 0.0);
        pin_uv.emplace_back(span, 0.0);
    }

    Eigen::VectorXi b(static_cast<int>(pins.size()));
    for (size_t i = 0; i < pins.size(); ++i) b(static_cast<int>(i)) = pins[i];
    Eigen::MatrixXd bc(static_cast<int>(pin_uv.size()), 2);
    for (size_t i = 0; i < pin_uv.size(); ++i) bc.row(static_cast<int>(i)) = pin_uv[i];

    try {
        if (method == "igl_lscm") {
            if (!igl::lscm(V, F, b, bc, UV)) return -1;
        } else if (method == "igl_harmonic1" || method == "igl_harmonic2") {
            const int k = (method == "igl_harmonic2") ? 2 : 1;
            if (!igl::harmonic(V, F, b, bc, k, UV)) return -1;
        } else if (method == "igl_arap") {
            Eigen::MatrixXd init;
            if (!igl::lscm(V, F, b, bc, init)) return -1;
            igl::ARAPData data;
            data.max_iter = std::max(1, iters);
            if (!igl::arap_precomputation(V, F, 2, b, data)) return -1;
            UV = init;
            if (!igl::arap_solve(bc, data, UV)) return -1;
        } else if (method == "igl_slim") {
            Eigen::MatrixXd init;
            if (!igl::lscm(V, F, b, bc, init)) return -1;
            igl::SLIMData data;
            igl::slim_precompute(V, F, init, data, igl::SYMMETRIC_DIRICHLET,
                                 b, bc, /*soft_p=*/1.0);
            UV = igl::slim_solve(data, std::max(1, iters));
        } else {
            return -1;
        }
    } catch (const std::exception &e) {
        if (dbg) std::fprintf(stderr, "[igl] %s threw: %s\n", method.c_str(), e.what());
        return -1;
    } catch (...) {
        return -1;
    }

    if (UV.rows() != V.rows() || !UV.allFinite()) {
        if (dbg) std::fprintf(stderr, "[igl] %s bad output (%d rows)\n", method.c_str(),
                              (int)UV.rows());
        return -1;
    }

    // a folded chart is useless downstream; let the caller fall back / split instead
    Eigen::VectorXi flipped;
    igl::flipped_triangles(UV, F, flipped);
    if (flipped.size() > std::max<int>(2, static_cast<int>(F.rows() / 4))) {
        if (dbg) std::fprintf(stderr, "[igl] %s folded %d / %d\n", method.c_str(),
                              (int)flipped.size(), (int)F.rows());
        return -1;
    }
    return 0;
}

}  // namespace igl_unwrap