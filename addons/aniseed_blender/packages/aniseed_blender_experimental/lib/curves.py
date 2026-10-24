"""
Reads and writes curve objects as json friendly data, so a guide curve can be
stored on a component and rebuilt later.

Only NURBS and poly splines are supported: each of their points is one
control point, which keeps hook modifiers (which address points by index)
simple. Points are stored in the space of a reference object (the deform
armature), so the curve follows the rig if the rig is moved.
"""
import bpy
from mathutils import Vector


def serialise(curve_object, space_object) -> dict:
    """
    Returns the first spline of the curve as data, with its points in the
    space of space_object.
    """
    spline = curve_object.data.splines[0]
    to_space = space_object.matrix_world.inverted() @ curve_object.matrix_world

    return dict(
        type=spline.type,
        order=spline.order_u,
        points=[list(to_space @ point.co.xyz) for point in spline.points],
    )


def create(name: str, data: dict, space_object, parent=None, collection=None):
    """
    Creates a curve object from data written by serialise, placed so its
    points sit where they were relative to space_object.

    Args:
        name: The name of the object (and its curve data).
        data: The curve data.
        space_object: The object the points are stored relative to.
        parent: The object to parent the curve under, if any.
        collection: The collection to link it into. Defaults to the parent's.
    """
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"

    points = data["points"]
    spline = curve.splines.new(data.get("type", "NURBS"))
    spline.points.add(len(points) - 1)

    for point, position in zip(spline.points, points):
        point.co = (position[0], position[1], position[2], 1.0)

    if spline.type == "NURBS":
        spline.order_u = max(2, min(data.get("order", 4), len(points)))

        # -- Makes the curve start and end exactly on its first and last
        # -- points, rather than somewhere between them
        spline.use_endpoint_u = True

    obj = bpy.data.objects.new(name, curve)

    collection = collection or (parent.users_collection[0] if parent and parent.users_collection else bpy.context.scene.collection)
    collection.objects.link(obj)

    if parent:
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()

    # -- The points are in space_object's space, so put the curve there
    obj.matrix_basis = space_object.matrix_world.copy()
    return obj


def through(points, spline_type: str = "NURBS", order: int = 4) -> dict:
    """
    Returns curve data for a curve using the given points.
    """
    return dict(type=spline_type, order=order, points=[list(Vector(point)) for point in points])
