// Cheap proxy mesh: uniform grid vertex clustering (a.k.a. vertex quantization).
//
// Purpose: give the merge/overlap stage a coarse stand-in for a chart without paying
// for an iterative QEM collapse (PAMO: ~290 ms per call, 72 CUDA rounds, 7 host<->device
// transfers per round).  This is O(#V + #F) on the CPU, deterministic, allocation-light,
// and accurate only in the sense that matters here: the proxy is spatially close to the
// original surface, and its topology is a valid manifold-ish triangle soup.
//
// Approximation quality is deliberately crude -- triangle shape is not controlled.
#pragma once

#include <Eigen/Core>

namespace cheap_proxy {

/// Absolute cell size derived once from the whole model (0 = not set).
extern double g_global_cell;

/// Compute the whole-model proxy resolution: coarsen the full mesh to
/// `frac` of its faces.  Call once, before any chart is processed.
void set_global_resolution(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, double frac);

/// Decimate by snapping vertices to a regular grid of the given cell size.
/// Vertices in the same cell collapse to their centroid; faces that become degenerate
/// (two corners in one cell) or duplicate are dropped.  Output is compacted.
///
/// \param cell  grid cell size in model units (use suggest_cell() for a target count)
/// \param Vo,Fo compacted output
/// \return number of faces in the proxy (0 if everything degenerated)
int decimate(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, double cell,
             Eigen::MatrixXd &Vo, Eigen::MatrixXi &Fo);

/// Cell size that should land near `target_faces` for a surface of the given 3D area.
/// Faces per unit area ~ 1 / (0.5 * cell^2), so cell = sqrt(2 * area / target).
double suggest_cell(double area_3d, int target_faces);

}  // namespace cheap_proxy