"""
Converts the Maya aniseed_toolkit control shapes (core_*.json) into the widget
library used by this package (lib/shapes.json), so both hosts share shape
names.

Each Maya shape is one or more NURBS curves. Degree 1 curves are polylines, so
their CVs are used as they are. Higher degree curves are sampled, so the
widget follows the curve rather than its hull.

Maya is Y up and the shapes are drawn around the Y axis. Blender draws a
custom shape in the bone's space, where Y runs along the bone, so the shapes
need no conversion: a Maya circle becomes a ring around the bone.

This only needs running when the Maya shapes change. Run it with any Python 3:

    python convert_maya_shapes.py <path to aniseed_toolkit/_resources/shapes>
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "..", "lib", "shapes.json")

# -- How many points to sample per span of a curve above degree 1
SAMPLES_PER_SPAN = 6


def _de_boor(degree, knots, cvs, t):
    """
    Returns the point at parameter t on the B-spline with the given knots and
    control points.
    """
    # -- Find the knot span holding t
    span = degree
    while span < len(knots) - degree - 2 and t >= knots[span + 1]:
        span += 1

    points = [list(cvs[span - degree + index]) for index in range(degree + 1)]

    for level in range(1, degree + 1):
        for index in range(degree, level - 1, -1):
            knot_index = span - degree + index
            denominator = knots[knot_index + degree - level + 1] - knots[knot_index]
            alpha = 0.0 if denominator == 0 else (t - knots[knot_index]) / denominator
            points[index] = [
                (1.0 - alpha) * points[index - 1][axis] + alpha * points[index][axis]
                for axis in range(3)
            ]

    return points[degree]


def _curve_points(curve):
    """
    Returns the polyline for a Maya curve, and whether it is closed.
    """
    degree = curve["degree"]
    cvs = curve["cvs"]
    closed = curve.get("form", 0) != 0

    if degree == 1:
        return [list(cv) for cv in cvs], closed

    # -- Maya stores knots without the two end knots, which de Boor needs
    knots = list(curve["knots"])
    knots = [knots[0]] + knots + [knots[-1]]

    start, end = knots[degree], knots[len(knots) - degree - 1]
    spans = max(1, len(cvs) - degree)
    count = spans * SAMPLES_PER_SPAN

    points = [
        _de_boor(degree, knots, cvs, start + (end - start) * index / count)
        for index in range(count + (0 if closed else 1))
    ]
    return points, closed


def convert(shape_folder):
    library = dict()

    for filename in sorted(os.listdir(shape_folder)):
        if not filename.endswith(".json"):
            continue

        with open(os.path.join(shape_folder, filename), "r") as handle:
            data = json.load(handle)

        verts = []
        edges = []

        for curve in data.get("curves", []):
            points, closed = _curve_points(curve)
            offset = len(verts)

            verts.extend([round(value, 4) for value in point] for point in points)
            edges.extend([offset + index, offset + index + 1] for index in range(len(points) - 1))

            if closed and len(points) > 2:
                edges.append([offset + len(points) - 1, offset])

        name = os.path.splitext(filename)[0]
        if name.startswith("core_"):
            name = name[len("core_"):]

        library[name] = dict(verts=verts, edges=edges)

    with open(OUTPUT, "w") as handle:
        json.dump(library, handle, indent=None, separators=(",", ":"))

    print(f"Wrote {len(library)} shapes to {os.path.abspath(OUTPUT)}")


if __name__ == "__main__":
    convert(sys.argv[1])
