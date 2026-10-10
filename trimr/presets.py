"""Performance targets. Every preset uses the same safety idea: try the boldest reduction first and keep the first result that
passes the preview check. Stronger presets only widen what is allowed to change (gates loosen slightly, more meshes are processed)."""

PRESETS = {
    "quality": dict(
        blurb="Gentle. About 33 percent fewer triangles on the meshes it touches. Strictest checks.",
        attempts=[(0.60, 0.008), (0.75, 0.006), (0.88, 0.004)], mass=0.90,
        solid=dict(tol=0.998, cov=0.990, dzp=0.008, dzm=0.002), foliage=dict(tol=0.997, cov=0.975, drms=0.07), bdiff=0.03),
    "balanced": dict(
        blurb="Recommended. About 46 percent fewer triangles on the meshes it touches.",
        attempts=[(0.45, 0.012), (0.60, 0.010), (0.75, 0.008)], mass=0.93,
        solid=dict(tol=0.998, cov=0.987, dzp=0.010, dzm=0.0025), foliage=dict(tol=0.996, cov=0.965, drms=0.08), bdiff=0.04),
    "performance": dict(
        blurb="Aggressive. About 57 percent fewer triangles on the meshes it touches.",
        attempts=[(0.30, 0.018), (0.40, 0.015), (0.55, 0.012), (0.70, 0.009)], mass=0.95,
        solid=dict(tol=0.998, cov=0.985, dzp=0.012, dzm=0.003), foliage=dict(tol=0.995, cov=0.950, drms=0.10), bdiff=0.04),
    "extreme": dict(
        blurb="Maximum. About 63 percent fewer, loosest checks, most meshes. Thinner foliage and softer rock edges are possible up close.",
        attempts=[(0.22, 0.030), (0.30, 0.025), (0.40, 0.020), (0.55, 0.015), (0.70, 0.010)], mass=0.98,
        solid=dict(tol=0.996, cov=0.970, dzp=0.020, dzm=0.005), foliage=dict(tol=0.990, cov=0.920, drms=0.13), bdiff=0.06),
}

# What can be reduced. Matched against the mesh path.
CATEGORIES = {
    "trees": ("landscape\\trees", "\\trees\\"),
    "foliage": ("\\plants\\", "\\flora\\", "landscape\\plants"),
    "rocks": ("landscape\\rocks", "landscape\\mountains", "landscape\\tundra", "\\cliff", "landscape\\ice", "landscape\\ash"),
    "buildings": ("architecture\\", "\\dungeons\\", "\\cities\\", "\\ruins\\", "\\fortifications\\"),
}
ALL_TARGETS = ("trees", "foliage", "rocks", "buildings", "other")


def category_of(rel):
    r = rel.lower()
    for cat, hints in CATEGORIES.items():
        if any(h in r for h in hints):
            return cat
    return "other"
