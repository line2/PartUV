// Isotropic-remeshing proxy.
//
// The clustering proxy (cheap_proxy) is fast but its triangles inherit the shape of the
// grid, so the mesh it produces is only loosely a "clean" surface for the screening stage
// to unwrap.  This backend rebuilds the chart with CGAL's isotropic remesher: target edge
// length is derived from the same face budget, and the remesher keeps every vertex on the
// input surface while producing near-equilateral triangles.
//
// It is deliberately expensive (CGAL, several passes over the mesh) -- this exists to
// answer "can a proper proxy reproduce the no-proxy pipeline decisions", not to be fast.
#pragma once

#include <Eigen/Core>

namespace iso_proxy {

/// Rebuild `V,F` as an isotropic triangle mesh with roughly `target_faces` triangles.
/// Non-manifold faces are skipped; returns the produced face count, 0 on failure.
int remesh(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, int target_faces,
           Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo);

}  // namespace iso_proxy