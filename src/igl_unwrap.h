// libigl parameterisation backends, used to answer "can ABF++ be replaced?".
//
// Every method here is free-boundary: two boundary vertices are pinned (the two most
// distant points on the loop), the rest is solved.  LSCM / k-harmonic / ARAP / SLIM all
// operate on the same input, so swapping them in the pipeline is a one-line dispatch.
#pragma once

#include <Eigen/Core>
#include <string>

namespace igl_unwrap {

/// Flatten `V,F` into `UV` with the named libigl method.
///   "igl_lscm"       least squares conformal maps (2 pinned boundary vertices)
///   "igl_harmonic1"  harmonic (k=1) with 2 pins
///   "igl_harmonic2"  biharmonic (k=2), equivalent to LSCM's energy
///   "igl_arap"       as-rigid-as-possible, initialised from LSCM
///   "igl_slim"       SLIM symmetric-Dirichlet, initialised from LSCM
/// Returns 0 on success, -1 when the method cannot be applied (caller falls back).
int flatten(const Eigen::MatrixXd &V, const Eigen::MatrixXi &F, Eigen::MatrixXd &UV,
            const std::string &method, int iters);

}  // namespace igl_unwrap