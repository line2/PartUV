#include "igl_unwrap.h"

#include <igl/arap.h>
#include <igl/boundary_loop.h>
#include <igl/flipped_triangles.h>
#include <igl/harmonic.h>
#include <igl/lscm.h>
#include <igl/slim.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>

namespace igl_unwrap {
namespace {

/// Two most distant points of the boundary loop (two farthest-point passes; the loop is
/// small relative to the chart, so this is free compared with the solve itself).
bool pick_pins(const Eigen::MatrixXd &V, const Eigen::VectorXi &bnd, int &i0, int &i1) {
    const int n = static_cast<int>(bnd.size());
    if (n < 3) return false;

    auto dist2 = [&](int a, int b) {
        const Eigen::Vector3d p = V.row(bnd(a)).transpose();
        const Eigen::Vector3d q = V.row(bnd(b)).transpose();
        return (p - q).squaredNorm();
    };

    i0 = 0;
    for (int k = 1; k < n; ++k)
        if (dist2(k, 0) > dist2(i0, 0)) i0 = k;

    i1 = (i0 + 1) % n;
    double best = -1.0;
    for (int k = 0; k < n; ++k) {
        if (k == i0) continue;
        const double d = dist2(i0, k);
        if (d > best) { best = d; i1 = k; }
    }
    return best > 1e-24;
}

}  // namespace

int flatten(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, Eigen::MatrixXd &UV,
            const std::string &method, int iters) {
    UV.resize(0, 2);
    const bool dbg = std::getenv("PARTUV_IGL_DEBUG") != nullptr;
    if (V.rows() < 4 || F.rows() < 2) {
        if (dbg) std::fprintf(stderr, "[igl] tiny input %d/%d\n", (int)V.rows(), (int)F.rows());
        return -1;
    }

    Eigen::VectorXi boundary;
    igl::boundary_loop(F, boundary);
    if (boundary.size() < 3) {
        // closed chart: no free boundary to pin, exactly the case where abf_unwrap also
        // gives up (it returns -2 when find_boundary_loops() is empty)
        if (dbg) std::fprintf(stderr, "[igl] closed chart (F=%d), deferring\n", (int)F.rows());
        return -2;
    }

    int p0 = 0, p1 = 0;
    if (!pick_pins(V, boundary, p0, p1)) return -1;

    Eigen::VectorXi b(2);
    b << boundary(p0), boundary(p1);
    const double span =
        (V.row(b(0)) - V.row(b(1))).norm();       // keeps the chart at model scale
    Eigen::MatrixXd bc(2, 2);
    bc << 0.0, 0.0, std::max(span, 1e-9), 0.0;

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
        if (dbg) std::fprintf(stderr, "[igl] %s threw (unknown)\n", method.c_str());
        return -1;
    }

    if (UV.rows() != V.rows() || !UV.allFinite()) {
        if (dbg) std::fprintf(stderr, "[igl] %s bad output %d rows, finite=%d\n",
                              method.c_str(), (int)UV.rows(), (int)UV.allFinite());
        return -1;
    }

    // a folded chart is useless downstream; let the caller fall back / split instead
    Eigen::VectorXi flipped;
    igl::flipped_triangles(UV, F, flipped);
    if (flipped.size() > std::max<int>(2, static_cast<int>(F.rows() / 4))) {
        if (dbg) std::fprintf(stderr, "[igl] %s flipped %d / %d\n",
                              method.c_str(), (int)flipped.size(), (int)F.rows());
        return -1;
    }   // tolerate < 2 % folds
    return 0;
}

}  // namespace igl_unwrap