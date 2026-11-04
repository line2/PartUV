// Intrinsic-Delaunay proxy.
//
// Positions come from the quadric clustering (which keeps the proxy on the surface);
// connectivity comes *only* from an intrinsic Delaunay triangulation of those points --
// no remeshing, no smoothing, no vertex movement.  Edge flips in the intrinsic metric
// maximise the minimum angle, which is exactly the property the parameterisation stage
// cares about, so the proxy's triangles are well shaped without inventing geometry.
#pragma once

#include <Eigen/Core>

namespace idt_proxy {

/// Cluster `V,F` down to ~`target_faces`, then re-triangulate intrinsically Delaunay.
/// Returns the produced face count (0 on failure).
int build(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, int target_faces,
          Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo);

}  // namespace idt_proxy