#include "iso_proxy.h"
#include "cheap_proxy.h"   // PRE_DECIMATE pre-pass

#ifdef PARTUV_HAS_CGAL
#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/remesh.h>
#include <CGAL/boost/graph/helpers.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace iso_proxy {
namespace {

#endif  // PARTUV_HAS_CGAL

#ifdef PARTUV_HAS_CGAL
using Kernel = CGAL::Simple_cartesian<double>;
using Point = Kernel::Point_3;
using Mesh = CGAL::Surface_mesh<Point>;

}  // namespace

int remesh(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, int target_faces,
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

    // PRE_DECIMATE: the remesher is a redistributor, not a decimator -- asking it to go
    // from 500k faces to 3k means collapsing ~160 edges per surviving face and it does not
    // finish.  Cheaply coarsen to a few times the budget first (quadric clustering keeps
    // the surface), then let the remesher make it uniform.
    Eigen::MatrixXd Vd;
    Eigen::MatrixXi Fd;
    const Eigen::MatrixXd *Vin = &V;
    const Eigen::MatrixXi *Fin = &F;
    if (F.rows() > 8 * target_faces) {
        cheap_proxy::Options popt;
        popt.quadric_repr = true;
        const int pre = std::max(8 * target_faces, 64);
        const double cell = cheap_proxy::suggest_cell(area, pre);
        const int npre = cheap_proxy::decimate(V, F, cell, Vd, Fd, popt);
        if (npre >= 8) {
            Vin = &Vd;
            Fin = &Fd;
        }
    }

    Mesh m;
    std::vector<Mesh::Vertex_index> vid(static_cast<size_t>(Vin->rows()));
    for (int i = 0; i < Vin->rows(); ++i) {
        if (!std::isfinite((*Vin)(i, 0)) || !std::isfinite((*Vin)(i, 1)) ||
            !std::isfinite((*Vin)(i, 2)))
            return 0;
        vid[i] = m.add_vertex(Point((*Vin)(i, 0), (*Vin)(i, 1), (*Vin)(i, 2)));
    }

    int skipped = 0;
    for (int f = 0; f < Fin->rows(); ++f) {
        const int a = (*Fin)(f, 0), b = (*Fin)(f, 1), c = (*Fin)(f, 2);
        if (a < 0 || b < 0 || c < 0 || a >= Vin->rows() || b >= Vin->rows() || c >= Vin->rows())
            return 0;
        if (a == b || b == c || a == c) { ++skipped; continue; }
        // add_face() refuses duplicates and faces that would break the halfedge
        // structure; a chart that came out of a merge can legitimately contain those.
        if (!m.add_face(vid[a], vid[b], vid[c]).is_valid()) ++skipped;
    }
    const char *dbg = std::getenv("PARTUV_ISO_DEBUG");
    if (dbg) {
        std::fprintf(stderr,
                     "[iso] in %d faces (%d skipped) -> mesh %zu faces, target %d, pre %d\n",
                     Fin->rows(), skipped, m.number_of_faces(), target_faces, Fin->rows());
    }
    if (m.number_of_faces() < 8) return 0;

    // equilateral triangle of area A/f has edge sqrt(4A/(f*sqrt(3)))
    const double edge =
        std::sqrt(4.0 * area / (static_cast<double>(target_faces) * std::sqrt(3.0)));

    try {
        CGAL::Polygon_mesh_processing::isotropic_remeshing(
            m.faces(), edge, m,
            CGAL::parameters::number_of_iterations(3).protect_constraints(false));
    } catch (const std::exception &e) {
        if (dbg) std::fprintf(stderr, "[iso] remesh threw: %s\n", e.what());
        return 0;
    } catch (...) {
        return 0;
    }
    if (m.number_of_faces() < 8) return 0;

    // compact and export
    std::vector<int> index(static_cast<size_t>(m.number_of_vertices()), -1);
    int nv = 0;
    for (auto v : m.vertices()) index[v] = nv++;
    if (nv < 4) return 0;

    Vo.resize(nv, 3);
    for (auto v : m.vertices()) {
        const Point &p = m.point(v);
        Vo.row(index[v]) << p.x(), p.y(), p.z();
    }

    Fo.resize(static_cast<int>(m.number_of_faces()), 3);
    int fi = 0;
    for (auto f : m.faces()) {
        int k = 0;
        for (auto v : CGAL::vertices_around_face(m.halfedge(f), m)) {
            if (k < 3) Fo(fi, k) = index[v];
            ++k;
        }
        if (k != 3) return 0;      // non-triangular face should not happen
        ++fi;
    }
    return static_cast<int>(Fo.rows());
}

}  // namespace iso_proxy

#else   // !PARTUV_HAS_CGAL
// The isotropic remesher needs CGAL.  Callers treat a face count below 8 as "refused
// the chart" and fall back to vertex clustering, so returning 0 is a clean no-op.
namespace iso_proxy {
int remesh(const Eigen::MatrixXd &, const Eigen::MatrixXi &, int,
           Eigen::MatrixXd &, Eigen::MatrixXi &) {
    return 0;
}
}  // namespace iso_proxy
#endif  // PARTUV_HAS_CGAL
