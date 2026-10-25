"""
Scene helpers shared by toolkit tools: pose bone selection (which differs
between Blender versions) and finding an aniseed rig's controls.
"""
import bpy

# -- The custom property aniseed_blender_experimental marks its armatures with,
# -- and the value marking the control armature
ROLE_KEY = "aniseed_role"
CONTROL_ROLE = "control"


# --------------------------------------------------------------------------------------
def is_selected(pose_bone) -> bool:
    """
    Returns whether the pose bone is selected. Blender 5 selects pose bones
    themselves; before that, selection was on the bone.
    """
    if hasattr(pose_bone, "select"):
        return pose_bone.select
    return pose_bone.bone.select


def set_selected(pose_bone, value: bool) -> None:
    """
    Selects or deselects the pose bone (see is_selected).
    """
    if hasattr(pose_bone, "select"):
        pose_bone.select = value
    else:
        pose_bone.bone.select = value


# --------------------------------------------------------------------------------------
def pose_armatures() -> list:
    """
    Returns the armatures in pose mode: the active object and any selected
    ones.
    """
    view_layer = bpy.context.view_layer
    objects = [obj for obj in view_layer.objects if obj.select_get()]

    if view_layer.objects.active and view_layer.objects.active not in objects:
        objects.insert(0, view_layer.objects.active)

    return [obj for obj in objects if obj.type == "ARMATURE" and obj.mode == "POSE"]


def selected_pose_bones() -> list:
    """
    Returns the selected pose bones of the armatures in pose mode.
    """
    return [
        pose_bone
        for obj in pose_armatures()
        for pose_bone in obj.pose.bones
        if is_selected(pose_bone)
    ]


def active_pose_bone():
    """
    Returns the active bone of the active armature, if it is in pose mode.
    """
    obj = bpy.context.view_layer.objects.active

    if obj is None or obj.type != "ARMATURE" or obj.mode != "POSE":
        return None

    bone = obj.data.bones.active
    return obj.pose.bones.get(bone.name) if bone else None


# --------------------------------------------------------------------------------------
def rig_root(obj):
    """
    Returns the top-most parent of the object, which for an aniseed rig is
    the rig object (named after the rig).
    """
    while obj.parent:
        obj = obj.parent
    return obj


def is_control_armature(obj) -> bool:
    return obj is not None and obj.type == "ARMATURE" and obj.get(ROLE_KEY) == CONTROL_ROLE


def control_armatures() -> list:
    """
    Returns every aniseed control armature in the scene.
    """
    return [obj for obj in bpy.context.scene.objects if is_control_armature(obj)]


def selected_control_armatures() -> list:
    """
    Returns the control armatures of the rigs anything selected (or active)
    belongs to, so selecting any part of a rig picks its controls.
    """
    view_layer = bpy.context.view_layer
    objects = [obj for obj in view_layer.objects if obj.select_get()]
    if view_layer.objects.active:
        objects.append(view_layer.objects.active)

    found = []
    for obj in objects:
        root = rig_root(obj)
        for candidate in [root] + list(root.children_recursive):
            if is_control_armature(candidate) and candidate not in found:
                found.append(candidate)

    return found


def controls(armature) -> list:
    """
    Returns the controls of a control armature: its pose bones with a custom
    shape.
    """
    return [pose_bone for pose_bone in armature.pose.bones if pose_bone.custom_shape]
