"""
Rigging helpers for pose bones: constraints, drivers, custom properties, bone
collections and the IK pole angle.
"""
from mathutils import Vector


def constrain(pose_bone, constraint_type: str, name: str = "", **properties):
    """
    Adds a constraint to the pose bone, sets the given properties on it, and
    returns it. Spaces default to world space.
    """
    constraint = pose_bone.constraints.new(constraint_type)

    if name:
        constraint.name = name

    for property_name, value in properties.items():
        setattr(constraint, property_name, value)

    return constraint


def add_property(
        pose_bone,
        name: str,
        default: float,
        minimum: float = None,
        maximum: float = None,
        description: str = "",
        items: list = None,
) -> None:
    """
    Adds an animatable custom property to the pose bone, with limits.

    If items (a list of labels) are given, the property is an integer shown
    as a drop down of those labels, and its value is the chosen label's index.
    """
    pose_bone[name] = default

    ui = pose_bone.id_properties_ui(name)
    settings = dict(default=default, description=description)

    if minimum is not None:
        settings.update(min=minimum, soft_min=minimum)
    if maximum is not None:
        settings.update(max=maximum, soft_max=maximum)
    if items:
        settings.update(items=[(label, label, "", index) for index, label in enumerate(items)])

    ui.update(**settings)

    # -- Lets the property be animated when the rig is linked into a shot
    pose_bone.property_overridable_library_set(f'["{name}"]', True)


def drive(
        owner,
        data_path: str,
        armature,
        property_bone: str,
        property_name: str,
        expression: str = "var",
        index: int = -1,
):
    """
    Drives a property of owner (a constraint, pose bone or other struct) from
    a custom property on a pose bone of the armature.

    Args:
        owner: What holds the property to drive, such as a constraint.
        data_path: The property to drive on the owner, such as "influence".
        armature: The armature object holding the property bone.
        property_bone: The pose bone holding the custom property.
        property_name: The custom property's name.
        expression: The driver expression, where the property is "var".
        index: The array index to drive, or -1 for a single value property.

    Returns:
        The driver's fcurve.
    """
    fcurve = owner.driver_add(data_path, index) if index >= 0 else owner.driver_add(data_path)

    driver = fcurve.driver
    driver.type = "SCRIPTED"

    variable = driver.variables.new()
    variable.name = "var"
    variable.type = "SINGLE_PROP"
    variable.targets[0].id_type = "OBJECT"
    variable.targets[0].id = armature
    variable.targets[0].data_path = f'pose.bones["{property_bone}"]["{property_name}"]'

    driver.expression = expression
    return fcurve


def assign_collection(armature, bone_name: str, collection_name: str):
    """
    Adds the bone to the named bone collection, creating the collection if
    needed. Returns the collection.
    """
    collections = armature.data.collections_all
    collection = collections.get(collection_name) or armature.data.collections.new(collection_name)
    collection.assign(armature.data.bones[bone_name])
    return collection


def pole_angle(base: dict, tip: dict, pole_location: Vector) -> float:
    """
    Returns the IK constraint pole angle which keeps a two bone chain in its
    rest pose, given the rest data (see armature.rest_data) of the chain's
    first and last bones and the pole's location, all in armature space.

    Blender measures the pole angle from the first bone's X axis, so the
    angle depends on the bones' rolls and cannot be hard coded.
    """
    pole_normal = (tip["tail"] - base["head"]).cross(Vector(pole_location) - base["head"])
    projected_pole_axis = pole_normal.cross(base["y_axis"])
    return _signed_angle(base["x_axis"], projected_pole_axis, base["y_axis"])


def pole_location(base: dict, tip: dict, distance: float, fallback: Vector) -> Vector:
    """
    Returns where to put a pole control for a two bone chain: out from the
    middle joint, in the direction the chain bends.

    Args:
        base: Rest data of the first bone.
        tip: Rest data of the second bone.
        distance: How far from the middle joint to place the pole.
        fallback: The direction to use if the chain is straight.
    """
    start = base["head"]
    middle = base["tail"]
    end = tip["tail"]

    chain = end - start
    offset = middle - start

    # -- The part of the middle joint's offset which is perpendicular to the
    # -- chain is the direction the chain bends in
    if chain.length > 1e-6:
        offset = offset - chain.normalized() * offset.dot(chain.normalized())

    direction = offset.normalized() if offset.length > 1e-4 else Vector(fallback).normalized()
    return middle + direction * distance


def _signed_angle(vector_u: Vector, vector_v: Vector, normal: Vector) -> float:
    """
    Returns the angle between two vectors, signed by the side of the normal.
    """
    angle = vector_u.angle(vector_v)
    if vector_u.cross(vector_v).angle(normal) < 1:
        angle = -angle
    return angle
