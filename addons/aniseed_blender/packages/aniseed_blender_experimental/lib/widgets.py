"""
The control shape library. Blender draws a control bone with a "custom shape"
object, so each shape in resources/shapes is built (once per rig) as a mesh
object of loose edges, kept in a hidden collection.

Each shape is a json file of NURBS curves (cvs, knots, degree, form), stored
the same way as the Maya aniseed_toolkit shapes, so a shape file can be copied
from one host's shapes folder to the other's. A shape's name is its file name
without the extension. A shape is drawn in the bone's space, where Y runs
along the bone, and is scaled by the bone's length.
"""
import os
import json

import bpy

# -- Custom properties identifying a widget object, so a snapshot can tell
# -- which shape a control uses
SHAPE_KEY = "aniseed_shape"
RIG_KEY = "aniseed_widget_rig"

SHAPES_FOLDER = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "resources", "shapes"))

# -- How many points to sample per span of a curve above degree 1
SAMPLES_PER_SPAN = 6

_LIBRARY = None


def library() -> dict:
    """
    Returns the shape library: {shape name: shape data}, where the shape data
    is as stored in the shape's file ({"node": str, "curves": [...]}).
    """
    global _LIBRARY

    if _LIBRARY is None:
        _LIBRARY = dict()
        for filename in sorted(os.listdir(SHAPES_FOLDER)):
            if filename.endswith(".json"):
                _LIBRARY[os.path.splitext(filename)[0]] = read_shape(os.path.join(SHAPES_FOLDER, filename))

    return _LIBRARY


def shape_path(shape: str) -> str:
    """
    Returns the file the shape with the given name is (or would be) stored in.
    """
    return os.path.join(SHAPES_FOLDER, shape + ".json")


def read_shape(shape_file: str) -> dict:
    """
    Returns the shape data in a shape file.

    Args:
        shape_file: An absolute path to a shape file, or the name of a shape
            in the shapes folder. The ".json" extension is optional.

    Raises:
        FileNotFoundError: If there is no such shape file.
    """
    if not shape_file.endswith(".json"):
        shape_file += ".json"

    if not os.path.exists(shape_file):
        shape_file = os.path.join(SHAPES_FOLDER, shape_file)

    with open(shape_file, "r") as handle:
        return json.load(handle)


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


def _curve_points(curve: dict):
    """
    Returns the polyline for a curve, and whether it is closed. Degree 1
    curves are polylines, so their CVs are used as they are. Higher degree
    curves are sampled, so the widget follows the curve rather than its hull.
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


def polylines(data: dict):
    """
    Returns the verts and edges of a loose edge mesh drawing the given shape
    data.
    """
    verts = []
    edges = []

    for curve in data.get("curves", []):
        points, closed = _curve_points(curve)
        offset = len(verts)

        verts.extend(tuple(point) for point in points)
        edges.extend((offset + index, offset + index + 1) for index in range(len(points) - 1))

        if closed and len(points) > 2:
            edges.append((offset + len(points) - 1, offset))

    return verts, edges


def _curve(cvs: list, degree: int = 1, knots: list = None, form: int = 0) -> dict:
    """
    Returns curve data in the stored form. Without knots, the knots of a
    degree 1 curve are used (0, 1, 2...).
    """
    return dict(
        cvs=[[float(value) for value in cv] for cv in cvs],
        degree=degree,
        form=form,
        knots=[float(knot) for knot in (knots if knots is not None else range(len(cvs)))],
    )


def _spline_curve(spline) -> dict:
    """
    Returns the curve data of a spline of a curve object, or None if it has
    too few points to draw.
    """
    if spline.type == "BEZIER":
        points = list(spline.bezier_points)
        if len(points) < 2:
            return None

        # -- A bezier is a degree 3 curve with every knot repeated three times,
        # -- so each segment is drawn by its two points and their handles
        segments = list(zip(points, points[1:]))
        if spline.use_cyclic_u:
            segments.append((points[-1], points[0]))

        cvs = [points[0].co]
        for first, second in segments:
            cvs.extend([first.handle_right, second.handle_left, second.co])

        knots = [index // 3 for index in range(3 * (len(segments) + 1))]
        return _curve(cvs, 3, knots)

    # -- POLY and NURBS points are (x, y, z, weight). Weights are not stored.
    cvs = [point.co[:3] for point in spline.points]
    if len(cvs) < 2:
        return None

    degree = min(spline.order_u, len(cvs)) - 1 if spline.type == "NURBS" else 1

    if degree == 1:
        if spline.use_cyclic_u:
            cvs.append(cvs[0])
        return _curve(cvs)

    knots = _nurbs_knots(len(cvs), degree + 1, spline.use_cyclic_u, spline.use_endpoint_u, spline.use_bezier_u)

    if spline.use_cyclic_u:
        # -- A periodic curve repeats its first cvs at the end
        cvs.extend(cvs[:degree])

    # -- Some knot modes (bezier without endpoint) only draw the middle of
    # -- the spline. Leave out the cvs which do not affect the drawn part, as
    # -- Maya cannot make a curve from them.
    start, end = knots[degree], knots[len(cvs)]
    used = [index for index in range(len(cvs)) if knots[index] < end and knots[index + degree + 1] > start]
    periodic = spline.use_cyclic_u and len(used) == len(cvs)
    cvs = cvs[used[0]:used[-1] + 1]
    knots = knots[used[0]:used[-1] + degree + 2]

    # -- Stored knots leave out the first and last knot, as Maya does
    return _curve(cvs, degree, knots[1:-1], 2 if periodic else 0)


def _nurbs_knots(count: int, order: int, cyclic: bool, endpoint: bool, bezier: bool) -> list:
    """
    Returns the full knot vector Blender gives a NURBS spline with the given
    point count, order and flags. A cyclic spline's knots cover its points
    plus the order - 1 points it wraps around to.
    """
    repeat_inner = order - 1 if bezier else 1
    if endpoint:
        head = order - (1 if cyclic else 0)
    else:
        head = min(2, repeat_inner) if bezier else 1
    tail = 2 * order - 1 if cyclic else (order if endpoint else 0)

    size = count + order + (order - 1 if cyclic else 0)
    knots = [0.0] * size

    current = 0.0
    repeat = head
    offset = 1 if endpoint and cyclic else 0
    if offset:
        current += 1.0

    for index in range(offset, size - tail):
        knots[index] = current
        repeat -= 1
        if repeat == 0:
            current += 1.0
            repeat = repeat_inner

    # -- The tail repeats the spacing of the head
    for index in range(tail):
        knots[size - tail + index] = current + knots[index] - knots[0]

    return knots


def _edge_chains(mesh) -> list:
    """
    Returns the mesh's edges walked into chains of vertex indices. A closed
    loop ends with its first vertex. Chains break where more than two edges
    meet.
    """
    neighbours = {index: [] for index in range(len(mesh.vertices))}
    for edge in mesh.edges:
        first, second = edge.vertices
        neighbours[first].append(second)
        neighbours[second].append(first)

    visited = set()
    chains = []

    def walk(start, step):
        chain = [start, step]
        visited.add(frozenset((start, step)))
        while len(neighbours[chain[-1]]) == 2:
            following = next(
                (vertex for vertex in neighbours[chain[-1]] if frozenset((chain[-1], vertex)) not in visited),
                None,
            )
            if following is None:
                break
            visited.add(frozenset((chain[-1], following)))
            chain.append(following)
        return chain

    # -- Open chains start at an end (or a junction), then what is left are
    # -- closed loops
    starts = [vertex for vertex, linked in neighbours.items() if len(linked) != 2]
    starts += [vertex for vertex, linked in neighbours.items() if len(linked) == 2]

    for start in starts:
        for step in neighbours[start]:
            if frozenset((start, step)) not in visited:
                chains.append(walk(start, step))

    return chains


def shape_data(obj) -> dict:
    """
    Returns the shape data of an object, in the object's local space, as a
    shape file stores it.

    A curve object gives a curve per spline: poly splines become degree 1
    curves, NURBS splines keep their degree, and bezier splines become degree
    3 curves (exactly, with every knot repeated three times). A mesh object
    (such as a widget) gives a degree 1 curve per chain of edges.

    Args:
        obj: A curve or mesh object.

    Raises:
        TypeError: If the object is neither a curve nor a mesh.
    """
    curves = []

    if obj.type == "CURVE":
        for spline in obj.data.splines:
            curve = _spline_curve(spline)
            if curve:
                curves.append(curve)

    elif obj.type == "MESH":
        vertices = obj.data.vertices
        for chain in _edge_chains(obj.data):
            curves.append(_curve([vertices[index].co for index in chain]))

    else:
        raise TypeError(f"{obj.name} is a {obj.type} object, not a curve or a mesh")

    return dict(node=obj.name, curves=curves)


def write_shape(filepath: str, data: dict) -> dict:
    """
    Writes shape data to a shape file. If the file is in the shapes folder,
    the library is reloaded the next time it is used, so the shape appears in
    it.

    Returns:
        The data written.
    """
    with open(filepath, "w") as handle:
        json.dump(data, handle, indent=4, sort_keys=True)

    global _LIBRARY
    if os.path.normcase(os.path.dirname(os.path.abspath(filepath))) == os.path.normcase(SHAPES_FOLDER):
        _LIBRARY = None

    return data


def save_shape(obj, filepath: str) -> dict:
    """
    Writes the shape of a curve or mesh object (see shape_data) to a shape
    file. To add it to the library, write it to shape_path(name).

    Returns:
        The data written, or an empty dict (writing nothing) if the object
        has no curves or edges.
    """
    data = shape_data(obj)
    if not data["curves"]:
        return {}

    return write_shape(filepath, data)


def collection_name(rig_label: str) -> str:
    return f"{rig_label}_Widgets"


def widget_collection(rig_label: str, create: bool = True):
    """
    Returns the rig's (hidden) widget collection, creating it beneath the rig
    object's collection if needed.
    """
    name = collection_name(rig_label)
    collection = bpy.data.collections.get(name)

    if collection is None and create:
        collection = bpy.data.collections.new(name)
        collection.hide_viewport = True
        collection.hide_render = True

        root = bpy.data.objects.get(rig_label)
        parent = root.users_collection[0] if root and root.users_collection else bpy.context.scene.collection
        parent.children.link(collection)

    return collection


def widget(rig_label: str, shape: str, name: str):
    """
    Returns the rig's widget object for the shape, creating it if needed.

    Args:
        rig_label: The rig the widget belongs to.
        shape: The shape's name in the library.
        name: The name to give the object if it has to be created.

    Raises:
        KeyError: If the shape is not in the library.
    """
    collection = widget_collection(rig_label)

    for obj in collection.objects:
        if obj.get(SHAPE_KEY) == shape:
            return obj

    verts, edges = polylines(library()[shape])

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj[SHAPE_KEY] = shape
    obj[RIG_KEY] = rig_label
    collection.objects.link(obj)

    return obj


def shape_of(widget_object) -> str:
    """
    Returns the library name of a widget object, or an empty string if it is
    not one of the library's widgets.
    """
    if widget_object is None:
        return ""
    return widget_object.get(SHAPE_KEY, "")


def remove_widgets(rig_label: str) -> None:
    """
    Removes the rig's widget collection, its objects and their meshes.
    """
    collection = widget_collection(rig_label, create=False)
    if collection is None:
        return

    for obj in list(collection.objects):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and not mesh.users:
            bpy.data.meshes.remove(mesh)

    bpy.data.collections.remove(collection)
