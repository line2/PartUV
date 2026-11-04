#include "cheap_proxy.h"
#include <Eigen/Cholesky>
#include <Eigen/LU>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <unordered_map>
#include <vector>

namespace cheap_proxy {
namespace {

struct CellKey {
    int32_t x, y, z;
    bool operator==(const CellKey &o) const {
        return x == o.x && y == o.y && z == o.z;
    }
};

struct CellHash {
    size_t operator()(const CellKey &k) const noexcept {
        // pack three 21-bit signed cells into 64 bits; collisions are harmless
        uint64_t ux = static_cast<uint32_t>(k.x) & 0x1FFFFF;
        uint64_t uy = static_cast<uint32_t>(k.y) & 0x1FFFFF;
        uint64_t uz = static_cast<uint32_t>(k.z) & 0x1FFFFF;
        return (ux << 42) ^ (uy << 21) ^ uz;
    }
};

/// Symmetric 4x4 plane quadric, stored as 10 coefficients (Garland & Heckbert).
struct Quadric {
    double a00 = 0, a01 = 0, a02 = 0, a11 = 0, a12 = 0, a22 = 0;
    double b0 = 0, b1 = 0, b2 = 0, c = 0;

    void add_plane(const Eigen::Vector3d &n, double d, double w) {
        a00 += w * n.x() * n.x(); a01 += w * n.x() * n.y(); a02 += w * n.x() * n.z();
        a11 += w * n.y() * n.y(); a12 += w * n.y() * n.z(); a22 += w * n.z() * n.z();
        b0 += w * d * n.x(); b1 += w * d * n.y(); b2 += w * d * n.z();
        c += w * d * d;
    }

    void add(const Quadric &o) {
        a00 += o.a00; a01 += o.a01; a02 += o.a02;
        a11 += o.a11; a12 += o.a12; a22 += o.a22;
        b0 += o.b0; b1 += o.b1; b2 += o.b2; c += o.c;
    }

    double evaluate(const Eigen::Vector3d &p) const {
        const double x = p.x(), y = p.y(), z = p.z();
        return a00 * x * x + 2 * a01 * x * y + 2 * a02 * x * z +
               a11 * y * y + 2 * a12 * y * z + a22 * z * z +
               2 * (b0 * x + b1 * y + b2 * z) + c;
    }

    /// Minimiser of the quadric; falls back (and clamps to the cell box) when ill-conditioned.
    Eigen::Vector3d optimal(const Eigen::Vector3d &fallback,
                            const Eigen::Vector3d &lo, const Eigen::Vector3d &hi) const {
        Eigen::Matrix3d A;
        A << a00, a01, a02,
             a01, a11, a12,
             a02, a12, a22;
        const double det = A.determinant();
        const double scale = std::max({std::abs(a00), std::abs(a11), std::abs(a22), 1e-30});
        Eigen::Vector3d p = fallback;
        if (std::abs(det) > 1e-9 * scale * scale * scale) {
            const Eigen::Vector3d rhs(-b0, -b1, -b2);
            p = A.ldlt().solve(rhs);
            if (!p.allFinite()) p = fallback;
        }
        // a nearly planar cell has no unique minimum along the normal -- keep it local
        for (int i = 0; i < 3; ++i) p(i) = std::min(std::max(p(i), lo(i)), hi(i));
        return p;
    }
};

/// One uniform-Laplacian pass: out = V + w * (mean(neighbours) - V).
void laplacian_pass(const Eigen::MatrixXd &V, const std::vector<std::vector<int>> &adj,
                    double w, Eigen::MatrixXd &out) {
    const int nv = static_cast<int>(V.rows());
    out.resize(nv, 3);
    for (int i = 0; i < nv; ++i) {
        const auto &nb = adj[i];
        if (nb.empty()) {                    // isolated vertex: leave it where it is
            out.row(i) = V.row(i);
            continue;
        }
        Eigen::RowVector3d acc = Eigen::RowVector3d::Zero();
        for (int j : nb) acc += V.row(j);
        acc /= static_cast<double>(nb.size());
        out.row(i) = V.row(i) + w * (acc - V.row(i));
    }
}

}  // namespace

double suggest_cell(double area_3d, int target_faces) {
    if (target_faces < 4 || area_3d <= 0.0) return 0.0;
    return std::sqrt(2.0 * area_3d / static_cast<double>(target_faces));
}

void taubin_smooth(Eigen::MatrixXd &V, const Eigen::MatrixXi &F, int iters,
                   double lambda, double mu) {
    const int nv = static_cast<int>(V.rows());
    if (nv == 0 || iters <= 0) return;

    std::vector<std::vector<int>> adj(nv);
    auto link = [&](int a, int b) {
        adj[a].push_back(b);
        adj[b].push_back(a);
    };
    for (int f = 0; f < F.rows(); ++f) {
        const int a = F(f, 0), b = F(f, 1), c = F(f, 2);
        link(a, b); link(b, c); link(c, a);
    }
    for (auto &v : adj) {
        std::sort(v.begin(), v.end());
        v.erase(std::unique(v.begin(), v.end()), v.end());
    }

    Eigen::MatrixXd tmp;
    for (int it = 0; it < iters; ++it) {
        laplacian_pass(V, adj, lambda, tmp);
        V.swap(tmp);
        laplacian_pass(V, adj, mu, tmp);     // mu negative: undoes the shrinkage
        V.swap(tmp);
    }
}

int decimate(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, double cell,
             Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo, const Options &opt) {
    Vo.resize(0, 3);
    Fo.resize(0, 3);
    if (V.rows() == 0 || F.rows() == 0 || cell <= 0.0) return 0;

    const int nv = static_cast<int>(V.rows());

    // ---- per-vertex quadrics (area-weighted face planes) -----------------------------
    std::vector<Quadric> vq;
    if (opt.quadric_repr) {
        vq.resize(nv);
        for (int f = 0; f < F.rows(); ++f) {
            const Eigen::Vector3d a = V.row(F(f, 0)).transpose();
            const Eigen::Vector3d b = V.row(F(f, 1)).transpose();
            const Eigen::Vector3d c = V.row(F(f, 2)).transpose();
            const Eigen::Vector3d cr = (b - a).cross(c - a);
            const double len = cr.norm();
            if (len <= 1e-20) continue;
            const Eigen::Vector3d n = cr / len;
            const double area2 = len;                       // 2 * area
            const double d = -n.dot(a);
            for (int k = 0; k < 3; ++k) vq[F(f, k)].add_plane(n, d, area2);
        }
    }

    // ---- bucket vertices into cells ---------------------------------------------------
    std::unordered_map<CellKey, int, CellHash> cell_id;
    cell_id.reserve(static_cast<size_t>(nv) * 2);

    std::vector<int> vert_cell(nv, -1);
    std::vector<Eigen::Vector3d> acc;          // centroid accumulator
    std::vector<Quadric> cell_q;               // quadric accumulator
    std::vector<Eigen::Vector3d> lo, hi;       // cell bounding box (clamp for the optimum)
    std::vector<int> count;

    for (int i = 0; i < nv; ++i) {
        CellKey k{static_cast<int32_t>(std::floor(V(i, 0) / cell)),
                  static_cast<int32_t>(std::floor(V(i, 1) / cell)),
                  static_cast<int32_t>(std::floor(V(i, 2) / cell))};
        auto it = cell_id.find(k);
        int id;
        const Eigen::Vector3d p(V(i, 0), V(i, 1), V(i, 2));
        if (it == cell_id.end()) {
            id = static_cast<int>(acc.size());
            cell_id.emplace(k, id);
            acc.emplace_back(Eigen::Vector3d::Zero());
            cell_q.emplace_back();
            lo.push_back(p);
            hi.push_back(p);
            count.push_back(0);
        } else {
            id = it->second;
            for (int d = 0; d < 3; ++d) {
                lo[id](d) = std::min(lo[id](d), p(d));
                hi[id](d) = std::max(hi[id](d), p(d));
            }
        }
        vert_cell[i] = id;
        acc[id] += p;
        count[id] += 1;
        if (opt.quadric_repr) cell_q[id].add(vq[i]);
    }

    // ---- representative position ------------------------------------------------------
    Eigen::MatrixXd Vp(static_cast<int>(acc.size()), 3);
    for (size_t i = 0; i < acc.size(); ++i) {
        const Eigen::Vector3d centroid = acc[i] / std::max(1, count[i]);
        const Eigen::Vector3d rep = opt.quadric_repr
                                       ? cell_q[i].optimal(centroid, lo[i], hi[i])
                                       : centroid;
        Vp.row(static_cast<int>(i)) = rep.transpose();
    }

    // ---- rebuild faces, dropping degenerates and duplicates ---------------------------
    std::vector<Eigen::Vector3i> faces;
    faces.reserve(F.rows());
    std::unordered_map<uint64_t, char> seen;
    seen.reserve(static_cast<size_t>(F.rows()) * 2);

    for (int f = 0; f < F.rows(); ++f) {
        int a = vert_cell[F(f, 0)], b = vert_cell[F(f, 1)], c = vert_cell[F(f, 2)];
        if (a == b || b == c || a == c) continue;
        int l = std::min({a, b, c}), h = std::max({a, b, c});
        int m = a + b + c - l - h;
        uint64_t key = (static_cast<uint64_t>(l) << 42) ^
                       (static_cast<uint64_t>(m) << 21) ^ static_cast<uint64_t>(h);
        if (seen.emplace(key, 1).second == false) continue;
        faces.emplace_back(a, b, c);
    }
    if (faces.empty()) return 0;

    // ---- compact ----------------------------------------------------------------------
    std::vector<int> remap(static_cast<size_t>(Vp.rows()), -1);
    std::vector<int> used;
    used.reserve(Vp.rows());
    for (const auto &t : faces) {
        for (int k = 0; k < 3; ++k) {
            if (remap[t[k]] < 0) {
                remap[t[k]] = static_cast<int>(used.size());
                used.push_back(t[k]);
            }
        }
    }

    Vo.resize(static_cast<int>(used.size()), 3);
    for (size_t i = 0; i < used.size(); ++i) Vo.row(static_cast<int>(i)) = Vp.row(used[i]);

    Fo.resize(static_cast<int>(faces.size()), 3);
    for (size_t i = 0; i < faces.size(); ++i)
        Fo.row(static_cast<int>(i)) << remap[faces[i][0]], remap[faces[i][1]], remap[faces[i][2]];

    if (opt.smooth_iters > 0) {
        taubin_smooth(Vo, Fo, opt.smooth_iters);
        std::vector<Eigen::Vector3i> keep;
        keep.reserve(Fo.rows());
        for (int f = 0; f < Fo.rows(); ++f) {
            const Eigen::Vector3d a = Vo.row(Fo(f, 0)).transpose();
            const Eigen::Vector3d b = Vo.row(Fo(f, 1)).transpose();
            const Eigen::Vector3d c = Vo.row(Fo(f, 2)).transpose();
            if ((b - a).cross(c - a).squaredNorm() > 1e-24)
                keep.emplace_back(Fo(f, 0), Fo(f, 1), Fo(f, 2));
        }
        if (keep.empty()) return 0;
        Fo.resize(static_cast<int>(keep.size()), 3);
        for (size_t i = 0; i < keep.size(); ++i) Fo.row(static_cast<int>(i)) = keep[i].transpose();
    }

    return static_cast<int>(Fo.rows());
}

}  // namespace cheap_proxy