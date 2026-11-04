// Cheap proxy mesh: uniform grid vertex clustering with a quadric-optimal representative.
//
// Purpose: give the split/merge screening stage a coarse stand-in for a chart without
// paying for an iterative QEM collapse (PAMO: ~290 ms per call, 72 CUDA rounds, 7
// host<->device transfers per round).  O(#V + #F) on the CPU, deterministic.
//
// Taking the cell *centroid* as the representative is what made the old proxy lossy: chord
// through a curved patch always sits inside the surface, so the proxy shrank (measured
// 0.70-0.95 of the chart's area) and every distortion reading was biased.  Instead the
// representative is the point that minimises the summed quadric error of the faces in the
// cell (Lindstrom 2000), which is the same error measure QEM collapse uses, clamped to the
// cell so a near-singular quadric cannot fling a vertex across the model.
#pragma once

#include <Eigen/Core>

namespace cheap_proxy {

struct Options {
    int smooth_iters = 0;        ///< Taubin passes after clustering (0 = raw grid)
    bool quadric_repr = true;    ///< false = old centroid representative (for comparison)
};

/// Decimate by snapping vertices to a regular grid of the given cell size.
/// Vertices in the same cell collapse to one representative; faces that become degenerate
/// (two corners in one cell) or duplicate are dropped.  Output is compacted.
///
/// \param cell  grid cell size in model units (use suggest_cell() for a target count)
/// \param Vo,Fo compacted output
/// \return number of faces in the proxy (0 if everything degenerated)
int decimate(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, double cell,
             Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo, const Options &opt = Options{});

/// Cell size that should land near `target_faces` for a surface of the given 3D area.
/// Faces per unit area ~ 1 / (0.5 * cell^2), so cell = sqrt(2 * area / target).
double suggest_cell(double area_3d, int target_faces);

/// Taubin (lambda/mu) smoothing of a triangle mesh; vertices move, topology does not.
void taubin_smooth(Eigen::MatrixXd &V, const Eigen::MatrixXi &F,
                   int iters, double lambda = 0.50, double mu = -0.53);

}  // namespace cheap_proxy