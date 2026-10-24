"""
Armature helpers: finding the rig's armatures by role, entering edit mode
safely, and creating bones.

The rig has two armatures, told apart by a custom property rather than by
name, so renaming them never breaks anything:

    obj["aniseed_role"] == "deform"     the user's skeleton (DEF bones)
    obj["aniseed_role"] == "control"    the control rig, rebuilt every build

Edit bones only exist in edit mode, and every reference to one dies when edit
mode is left. Code here (and in the components) only ever keeps bone names.
"""
import contextlib
import typing

import bpy
from mathutils import Vector

# -- The custom property telling the rig's objects apart
ROLE_KEY = "aniseed_role"

DEFORM = "deform"
CONTROL = "control"
CONTROL_CURVE = "control_curve"

# -- The custom property on a control armature bone naming the deform bone it
# -- drives, which Link Deformation Rig constrains to it
DRIVES_KEY = "aniseed_drives"


def rig_object(rig_label: str):
    """
    Returns the rig's root object (an Empty named after the rig), or None.
    """
    return bpy.data.objects.get(rig_label)


def find_role(rig_label: str, role: str):
    """
    Returns the first object beneath the rig object with the given role, or
    None if there is none.
    """
    root = rig_object(rig_label)
    if root is None:
        return None

    for obj in root.children_recursive:
        if obj.get(ROLE_KEY) == role:
            return obj

    return None


def find_all_roles(rig_label: str, roles: typing.Iterable[str]) -> list:
    """
    Returns every object beneath the rig object with one of the given roles.
    """
    roles = set(roles)
    root = rig_object(rig_label)
    if root is None:
        return []

    return [obj for obj in root.children_recursive if obj.get(ROLE_KEY) in roles]


def rig_armatures(rig_label: str) -> list:
    """
    Returns every armature object beneath the rig object.
    """
    root = rig_object(rig_label)
    if root is None:
        return []

    return [obj for obj in root.children_recursive if obj.type == "ARMATURE"]


def bone_names(armature) -> typing.List[str]:
    """
    Returns the names of the armature's bones. While the armature is in edit
    mode its bones are not up to date, so the edit bones are read instead.
    """
    if armature.data.is_editmode:
        return [bone.name for bone in armature.data.edit_bones]
    return [bone.name for bone in armature.data.bones]


def selected_bone(armature) -> str:
    """
    Returns the armature's active bone if the user has it selected, otherwise
    an empty string. Outside edit mode, the armature itself must be selected
    too.
    """
    if armature is None or armature.type != "ARMATURE":
        return ""

    if armature.data.is_editmode:
        bone = armature.data.edit_bones.active
        return bone.name if bone and bone.select else ""

    try:
        if not armature.select_get():
            return ""
    except RuntimeError:
        # -- The armature is not in the current view layer
        return ""

    bone = armature.data.bones.active
    if bone is None:
        return ""

    # -- Blender 5 moved bone selection outside edit mode to the pose bone
    pose_bone = armature.pose.bones.get(bone.name)
    selected = pose_bone.select if hasattr(pose_bone, "select") else bone.select
    return bone.name if selected else ""


def create_armature(name: str, parent, role: str, collection=None):
    """
    Creates an armature object (and its data) beneath the parent, sitting on
    the parent, tagged with the given role.
    """
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)

    collection = collection or (parent.users_collection[0] if parent and parent.users_collection else bpy.context.scene.collection)
    collection.objects.link(obj)

    if parent:
        obj.parent = parent

    obj[ROLE_KEY] = role
    return obj


def remove_object(obj) -> None:
    """
    Removes the object and, if nothing else uses it, its data.
    """
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)

    if data is None or data.users:
        return

    for data_type, collection in (
            (bpy.types.Armature, bpy.data.armatures),
            (bpy.types.Curve, bpy.data.curves),
            (bpy.types.Mesh, bpy.data.meshes),
    ):
        if isinstance(data, data_type):
            collection.remove(data)
            return


@contextlib.contextmanager
def edit_bones(armature):
    """
    Enters edit mode on the armature and yields its edit bones, always
    returning to object mode afterwards.

    mode_set acts on the view layer's active object (an override alone does
    nothing), and also puts every other selected armature into edit mode, so
    the armature is made the only selected object while editing. The
    selection, active object and visibility are put back afterwards.
    """
    view_layer = bpy.context.view_layer

    # -- Leave whatever mode the current object is in first
    current = view_layer.objects.active
    if current and current.mode != "OBJECT":
        with bpy.context.temp_override(active_object=current, object=current):
            bpy.ops.object.mode_set(mode="OBJECT")

    previous_active = current.name if current else None
    previous_selection = [obj.name for obj in view_layer.objects if obj.select_get()]

    # -- A hidden object cannot enter edit mode
    was_hidden = armature.hide_get()
    was_viewport_hidden = armature.hide_viewport
    armature.hide_set(False)
    armature.hide_viewport = False

    for obj in view_layer.objects:
        obj.select_set(False)

    armature.select_set(True)
    view_layer.objects.active = armature

    try:
        with bpy.context.temp_override(active_object=armature, object=armature):
            bpy.ops.object.mode_set(mode="EDIT")

        yield armature.data.edit_bones

    finally:
        with bpy.context.temp_override(active_object=armature, object=armature):
            bpy.ops.object.mode_set(mode="OBJECT")

        armature.hide_viewport = was_viewport_hidden
        armature.hide_set(was_hidden)

        for obj in view_layer.objects:
            obj.select_set(obj.name in previous_selection)
        view_layer.objects.active = view_layer.objects.get(previous_active) if previous_active else None


def new_bone(
        edit_bones_,
        name: str,
        head: Vector,
        tail: Vector,
        z_axis: Vector = None,
        parent: str = None,
        connect: bool = False,
        deform: bool = False,
) -> str:
    """
    Creates an edit bone and returns its name (which Blender may have made
    unique). Positions are in armature space.

    Args:
        edit_bones_: The armature's edit bones (from edit_bones()).
        name: The name to give the bone.
        head: Where the bone starts.
        tail: Where the bone ends.
        z_axis: The direction the bone's Z axis should point (as near as it
            can, being perpendicular to the bone). Defaults to world up, or
            forward for a vertical bone.
        parent: The name of the parent bone, if any.
        connect: Whether the bone's head is locked to its parent's tail.
        deform: Whether the bone deforms meshes.
    """
    bone = edit_bones_.new(name)
    bone.head = Vector(head)
    bone.tail = Vector(tail)

    if z_axis is None:
        direction = (bone.tail - bone.head).normalized()
        z_axis = Vector((0, 0, 1)) if abs(direction.z) < 0.99 else Vector((0, -1, 0))

    bone.align_roll(Vector(z_axis))
    bone.use_deform = deform

    if parent:
        bone.parent = edit_bones_[parent]
        bone.use_connect = connect and (bone.parent.tail - bone.head).length < 1e-5

    return bone.name


def rest_data(armature, bone_name: str) -> dict:
    """
    Returns the head, tail, Z axis, length and matrix of the bone's rest
    position, in armature space. Only valid in object mode.
    """
    bone = armature.data.bones[bone_name]
    matrix = bone.matrix_local.copy()

    return dict(
        head=bone.head_local.copy(),
        tail=bone.tail_local.copy(),
        z_axis=matrix.col[2].xyz.normalized(),
        x_axis=matrix.col[0].xyz.normalized(),
        y_axis=matrix.col[1].xyz.normalized(),
        length=bone.length,
        matrix=matrix,
        parent=bone.parent.name if bone.parent else "",
    )


def reset_pose(armature) -> None:
    """
    Puts every pose bone back to its rest position.
    """
    for pose_bone in armature.pose.bones:
        pose_bone.location = (0, 0, 0)
        pose_bone.rotation_quaternion = (1, 0, 0, 0)
        pose_bone.rotation_euler = (0, 0, 0)
        pose_bone.rotation_axis_angle = (0, 0, 1, 0)
        pose_bone.scale = (1, 1, 1)


def world_to_armature(armature, point) -> Vector:
    """
    Returns the world space point in the armature's space.
    """
    return armature.matrix_world.inverted() @ Vector(point)
