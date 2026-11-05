#pragma once
// Convex hull of a 2D point set, returning the *area* of the hull.
//
// This replaces CGAL::convex_hull_2, which the cutting-plane search used only to measure
// the cross-section area of a slab.  The hull is unique, so the area is too; only the
// ring order can differ, and the shoelace sum is order-invariant for a CCW ring.
//
// Andrew's monotone chain: O(n log n), no dependencies, deterministic.
#include <algorithm>
#include <cmath>
#include <vector>

namespace hull2d {

inline double area(const std::vector<std::pair<double, double>> &pts)
{
    const size_t n = pts.size();
    if (n < 3) return 0.0;

    std::vector<std::pair<double, double>> p = pts;
    std::sort(p.begin(), p.end());

    auto cross = [](const std::pair<double, double> &o,
                    const std::pair<double, double> &a,
                    const std::pair<double, double> &b) {
        return (a.first - o.first) * (b.second - o.second) -
               (a.second - o.second) * (b.first - o.first);
    };

    std::vector<std::pair<double, double>> h(2 * n);
    size_t k = 0;
    for (size_t i = 0; i < n; ++i) {              // lower hull
        while (k >= 2 && cross(h[k - 2], h[k - 1], p[i]) <= 0.0) --k;
        h[k++] = p[i];
    }
    for (size_t i = n - 1, lower = k + 1; i-- > 0;) {  // upper hull
        while (k >= lower && cross(h[k - 2], h[k - 1], p[i]) <= 0.0) --k;
        h[k++] = p[i];
    }
    h.resize(k);   // last point repeats the first

    double twice = 0.0;
    for (size_t i = 0; i + 1 < h.size(); ++i) {
        twice += h[i].first * h[i + 1].second - h[i + 1].first * h[i].second;
    }
    return 0.5 * std::fabs(twice);
}

}  // namespace hull2d
