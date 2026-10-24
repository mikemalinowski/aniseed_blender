"""
Mirrors positions and bones across the YZ plane (left to right), in the
armature's space.

A mirrored bone has its head and tail reflected and its Z axis reflected,
which gives the same result as Blender's Symmetrize (the roll is negated), so
a pose copied from one side can be pasted flipped on the other.
"""
from mathutils import Vector


def mirror_point(point) -> Vector:
    """
    Returns the point reflected across the YZ plane.
    """
    return Vector((-point[0], point[1], point[2]))


def mirror_bone(head, tail, z_axis) -> tuple:
    """
    Returns the (head, tail, z_axis) of the bone mirrored across the YZ plane.
    """
    return mirror_point(head), mirror_point(tail), mirror_point(z_axis)
