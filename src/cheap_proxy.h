// Cheap proxy mesh: uniform grid vertex clustering + optional Taubin smoothing.
//
// Purpose: give the split/merge screening stage a coarse stand-in for a chart without
// paying for an iterative QEM collapse (PAMO: ~290 ms per call, 72 CUDA rounds, 7
// host<->device transfers per round).  O(#V + #F) on the CPU, deterministic.
//
// Clustering alone snaps every vertex to its cell centroid, which crushes high-curvature
// regions and produces slivers/needles.  Because the screening stage measures distortion
// *on the proxy*, those artefacts bias the decision (charts look worse than they are and
// get split too eagerly).  A few Taubin passes (lambda/mu, non-shrinking) restore triangle
// shape and de-jag the boundary for O(V) per pass.
#pragma once

#include <Eigen/Core>

namespace cheap_proxy {

/// Decimate by snapping vertices to a regular grid of the given cell size.
/// Vertices in the same cell collapse to their centroid; faces that become degenerate
/// (two corners in one cell) or duplicate are dropped.  Output is compacted.
///
/// \param cell         grid cell size in model units (use suggest_cell() for a target count)
/// \param Vo,Fo        compacted output
/// \param smooth_iters Taubin passes applied to the clustered mesh (0 disables)
/// \return number of faces in the proxy (0 if everything degenerated)
int decimate(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, double cell,
             Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo, int smooth_iters = 4);

/// Cell size that should land near `target_faces` for a surface of the given 3D area.
/// Faces per unit area ~ 1 / (0.5 * cell^2), so cell = sqrt(2 * area / target).
double suggest_cell(double area_3d, int target_faces);

/// Taubin (lambda/mu) smoothing of a triangle mesh; vertices move, topology does not.
/// Used by decimate() and exposed for benchmarking.
void taubin_smooth(Eigen::MatrixXd &V, const Eigen::MatrixXi &F,
                   int iters, double lambda = 0.50, double mu = -0.53);

}  // namespace cheap_proxy