#include "cheap_proxy.h"

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

    // unique 1-ring adjacency
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
             Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo, int smooth_iters) {
    Vo.resize(0, 3);
    Fo.resize(0, 3);
    if (V.rows() == 0 || F.rows() == 0 || cell <= 0.0) return 0;

    const int nv = static_cast<int>(V.rows());

    // cell index per vertex
    std::unordered_map<CellKey, int, CellHash> cell_id;
    cell_id.reserve(static_cast<size_t>(nv) * 2);

    std::vector<int> vert_cell(nv, -1);   // vertex -> compacted proxy vertex
    std::vector<Eigen::Vector3d> acc;     // centroid accumulator per proxy vertex
    std::vector<int> count;

    for (int i = 0; i < nv; ++i) {
        CellKey k{static_cast<int32_t>(std::floor(V(i, 0) / cell)),
                  static_cast<int32_t>(std::floor(V(i, 1) / cell)),
                  static_cast<int32_t>(std::floor(V(i, 2) / cell))};
        auto it = cell_id.find(k);
        int id;
        if (it == cell_id.end()) {
            id = static_cast<int>(acc.size());
            cell_id.emplace(k, id);
            acc.emplace_back(Eigen::Vector3d::Zero());
            count.push_back(0);
        } else {
            id = it->second;
        }
        vert_cell[i] = id;
        acc[id] += Eigen::Vector3d(V(i, 0), V(i, 1), V(i, 2));
        count[id] += 1;
    }

    // representative position = centroid of the cell
    Eigen::MatrixXd Vp(static_cast<int>(acc.size()), 3);
    for (size_t i = 0; i < acc.size(); ++i)
        Vp.row(static_cast<int>(i)) = (acc[i] / std::max(1, count[i])).transpose();

    // rebuild faces, dropping degenerates and duplicates
    std::vector<Eigen::Vector3i> faces;
    faces.reserve(F.rows());
    std::unordered_map<uint64_t, char> seen;
    seen.reserve(static_cast<size_t>(F.rows()) * 2);

    for (int f = 0; f < F.rows(); ++f) {
        int a = vert_cell[F(f, 0)], b = vert_cell[F(f, 1)], c = vert_cell[F(f, 2)];
        if (a == b || b == c || a == c) continue;             // collapsed to an edge/point
        int lo = std::min({a, b, c}), hi = std::max({a, b, c});
        int mid = a + b + c - lo - hi;
        uint64_t key = (static_cast<uint64_t>(lo) << 42) ^
                       (static_cast<uint64_t>(mid) << 21) ^ static_cast<uint64_t>(hi);
        if (seen.emplace(key, 1).second == false) continue;   // duplicate face
        faces.emplace_back(a, b, c);
    }

    if (faces.empty()) return 0;

    // compact vertices to those actually referenced
    std::vector<int> remap(static_cast<size_t>(Vp.rows()), -1);
    std::vector<int> used;
    used.reserve(Vp.rows());
    for (const auto &t : faces) {
        for (int k = 0; k < 3; ++k) {
            int v = t[k];
            if (remap[v] < 0) {
                remap[v] = static_cast<int>(used.size());
                used.push_back(v);
            }
        }
    }

    Vo.resize(static_cast<int>(used.size()), 3);
    for (size_t i = 0; i < used.size(); ++i)
        Vo.row(static_cast<int>(i)) = Vp.row(used[i]);

    Fo.resize(static_cast<int>(faces.size()), 3);
    for (size_t i = 0; i < faces.size(); ++i)
        Fo.row(static_cast<int>(i)) << remap[faces[i][0]], remap[faces[i][1]], remap[faces[i][2]];

    // restore triangle shape: clustering snaps to cell centroids, which crushes curved
    // regions and leaves slivers; the screening stage measures distortion on this mesh,
    // so those artefacts would make good charts look bad and trigger extra splits.
    if (smooth_iters > 0) {
        taubin_smooth(Vo, Fo, smooth_iters);
        std::vector<Eigen::Vector3i> keep;   // drop faces that folded during smoothing
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