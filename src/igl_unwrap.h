// libigl parameterisation backends, used to answer "can ABF++ be replaced?".
//
// Every method here is free-boundary: two vertices per connected component are pinned
// (the two most distant ones, preferring the boundary), the rest is solved.  A chart that
// came out of a merge can contain several components, and LSCM / harmonic are singular
// unless *each* component is pinned -- that, not closed charts, is what made ARAP fail on
// ~10 % of real charts.
#pragma once

#include <Eigen/Core>
#include <string>

namespace igl_unwrap {

/// Flatten `V,F` into `UV` with the named libigl method.
///   "igl_lscm"       least squares conformal maps
///   "igl_harmonic1"  harmonic (k=1)
///   "igl_harmonic2"  biharmonic (k=2), equivalent to LSCM's energy
///   "igl_arap"       as-rigid-as-possible, initialised from LSCM
///   "igl_slim"       SLIM symmetric-Dirichlet, initialised from LSCM
/// Returns 0 on success, -1 when the method cannot be applied, -2 when the chart is closed
/// (no boundary loop) -- the same convention abf_unwrap uses.
int flatten(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, Eigen::MatrixXd &UV,
            const std::string &method, int iters);

}  // namespace igl_unwrap