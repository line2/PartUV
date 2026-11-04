#include "idt_proxy.h"

#include <igl/edge_lengths.h>
#include <igl/intrinsic_delaunay_triangulation.h>

#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <vector>

#include "cheap_proxy.h"

namespace idt_proxy {
namespace {

/// Drop faces with a repeated index and faces with the same vertex set as an earlier one.
/// The intrinsic flips are allowed to produce both (Fisher et al. 2007, Fig. 3).
void clean_faces(const Eigen::MatrixXi &Fin, Eigen::MatrixXi &Fout) {
    std::vector<Eigen::Vector3i> keep;
    keep.reserve(static_cast<size_t>(Fin.rows()));
    std::unordered_map<uint64_t, char> seen;
    seen.reserve(static_cast<size_t>(Fin.rows()) * 2);

    for (int f = 0; f < Fin.rows(); ++f) {
        int a = Fin(f, 0), b = Fin(f, 1), c = Fin(f, 2);
        if (a == b || b == c || a == c) continue;
        int lo = std::min({a, b, c}), hi = std::max({a, b, c});
        int mid = a + b + c - lo - hi;
        const uint64_t key = (static_cast<uint64_t>(lo) << 42) ^
                             (static_cast<uint64_t>(mid) << 21) ^ static_cast<uint64_t>(hi);
        if (!seen.emplace(key, 1).second) continue;
        keep.emplace_back(a, b, c);
    }
    Fout.resize(static_cast<int>(keep.size()), 3);
    for (size_t i = 0; i < keep.size(); ++i)
        Fout.row(static_cast<int>(i)) = keep[i].transpose();
}

}  // namespace

int build(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, int target_faces,
          Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo) {
    Vo.resize(0, 3);
    Fo.resize(0, 3);
    if (V.rows() == 0 || F.rows() == 0 || target_faces < 8) return 0;

    double area = 0.0;
    for (int f = 0; f < F.rows(); ++f) {
        const Eigen::Vector3d a = V.row(F(f, 0)).transpose();
        const Eigen::Vector3d b = V.row(F(f, 1)).transpose();
        const Eigen::Vector3d c = V.row(F(f, 2)).transpose();
        area += 0.5 * ((b - a).cross(c - a)).norm();
    }
    if (!(area > 0.0)) return 0;

    // 1) positions: quadric clustering down to the budget
    cheap_proxy::Options popt;
    popt.quadric_repr = true;
    popt.smooth_iters = 0;
    const double cell = cheap_proxy::suggest_cell(area, std::max(8, target_faces));
    Eigen::MatrixXd Vs;
    Eigen::MatrixXi Fs;
    const int ns = cheap_proxy::decimate(V, F, cell, Vs, Fs, popt);
    if (ns < 8) return 0;

    // 2) connectivity: intrinsic Delaunay flips over those positions
    Eigen::MatrixXd l_in, l_out;
    Eigen::MatrixXi Fd;
    igl::edge_lengths(Vs, Fs, l_in);
    try {
        igl::intrinsic_delaunay_triangulation(l_in, Fs, l_out, Fd);
    } catch (...) {
        Vo = Vs;
        Fo = Fs;
        return ns;
    }

    // 3) the flips may leave combinatorial junk behind
    Eigen::MatrixXi Fc;
    clean_faces(Fd, Fc);
    if (Fc.rows() < 8) {
        Vo = Vs;
        Fo = Fs;
        return ns;
    }

    // 4) keep only vertices that survived, so the output is compact
    std::vector<int> remap(static_cast<size_t>(Vs.rows()), -1);
    std::vector<int> used;
    used.reserve(static_cast<size_t>(Vs.rows()));
    for (int f = 0; f < Fc.rows(); ++f) {
        for (int k = 0; k < 3; ++k) {
            const int v = Fc(f, k);
            if (remap[v] < 0) {
                remap[v] = static_cast<int>(used.size());
                used.push_back(v);
            }
        }
    }
    Vo.resize(static_cast<int>(used.size()), 3);
    for (size_t i = 0; i < used.size(); ++i) Vo.row(static_cast<int>(i)) = Vs.row(used[i]);
    Fo.resize(Fc.rows(), 3);
    for (int f = 0; f < Fc.rows(); ++f)
        Fo.row(f) << remap[Fc(f, 0)], remap[Fc(f, 1)], remap[Fc(f, 2)];

    return static_cast<int>(Fo.rows());
}

}  // namespace idt_proxy