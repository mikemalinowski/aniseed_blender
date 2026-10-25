"""
Animators Toolkit tools for a rig's controls: selecting, resetting and keying
them. A control is a pose bone with a custom shape on a rig's control
armature.
"""
import logging

import bpy

from aniseed_blender_standard.toolkit import core
from aniseed_blender_standard.toolkit import scene

log = logging.getLogger(__name__)

# -- The property holding each rotation mode's rotation
_ROTATION_PATHS = {
    "QUATERNION": "rotation_quaternion",
    "AXIS_ANGLE": "rotation_axis_angle",
}


def _target_controls(selected_only: bool) -> list:
    """
    Returns the selected controls, or every control of the rigs anything
    selected belongs to.
    """
    if selected_only:
        return [
            pose_bone for pose_bone in scene.selected_pose_bones()
            if pose_bone.custom_shape and scene.is_control_armature(pose_bone.id_data)
        ]

    return [
        pose_bone
        for armature in scene.selected_control_armatures()
        for pose_bone in scene.controls(armature)
    ]


def _missing_controls_message(selected_only: bool) -> str:
    if selected_only:
        return "Select the controls, in pose mode (or turn off Selected Only)"
    return "Select any part of a rig"


# --------------------------------------------------------------------------------------
class SelectControls(core.Tool):
    """
    Selects every (visible) control of the rigs anything selected belongs
    to, or of every rig in the scene with All Rigs on. The control armatures
    are put into pose mode.
    """

    identifier = "Select Controls"
    toolkit = "Animators"
    categories = ["Controls"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="All Rigs",
            value=False,
            description="Whether to select the controls of every rig in the scene",
        )

    def armatures(self) -> list:
        if self.option("All Rigs").get():
            return scene.control_armatures()
        return scene.selected_control_armatures()

    def is_valid(self) -> bool:
        if not self.armatures():
            log.warning("Select any part of a rig, or turn on All Rigs")
            return False
        return True

    def run(self) -> None:
        armatures = self.armatures()
        view_layer = bpy.context.view_layer
        active = view_layer.objects.active

        # -- mode_set acts on the active object (and the other selected ones),
        # -- so make the control armatures the selection first
        if active is not None and active.mode != "OBJECT":
            with bpy.context.temp_override(active_object=active, object=active):
                bpy.ops.object.mode_set(mode="OBJECT")

        for obj in view_layer.objects:
            obj.select_set(obj in armatures)
        view_layer.objects.active = armatures[0]

        with bpy.context.temp_override(active_object=armatures[0], object=armatures[0]):
            bpy.ops.object.mode_set(mode="POSE")

        for armature in armatures:
            controls = [pose_bone for pose_bone in scene.controls(armature) if not pose_bone.bone.hide]

            for pose_bone in armature.pose.bones:
                scene.set_selected(pose_bone, pose_bone in controls)

            if controls:
                armature.data.bones.active = controls[0].bone


# --------------------------------------------------------------------------------------
class ResetControls(core.Tool):
    """
    Returns controls to their rest pose: their location and rotation are
    cleared and their scale set to 1. Locked channels are left alone (a
    quaternion or axis angle rotation is left alone if any of its channels
    are locked).
    """

    identifier = "Reset Controls"
    toolkit = "Animators"
    categories = ["Controls"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Selected Only",
            value=True,
            description="Whether to reset the selected controls, or every control of the selected rigs",
        )

    def is_valid(self) -> bool:
        if not _target_controls(self.option("Selected Only").get()):
            log.warning(_missing_controls_message(self.option("Selected Only").get()))
            return False
        return True

    def run(self) -> None:
        for pose_bone in _target_controls(self.option("Selected Only").get()):
            for axis in range(3):
                if not pose_bone.lock_location[axis]:
                    pose_bone.location[axis] = 0.0

                if not pose_bone.lock_scale[axis]:
                    pose_bone.scale[axis] = 1.0

                if not pose_bone.lock_rotation[axis]:
                    pose_bone.rotation_euler[axis] = 0.0

            if not pose_bone.lock_rotation_w and not any(pose_bone.lock_rotation):
                pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
                pose_bone.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)


# --------------------------------------------------------------------------------------
class KeyControls(core.Tool):
    """
    Keys the location, rotation and scale of controls at the current frame.
    """

    identifier = "Key Controls"
    toolkit = "Animators"
    categories = ["Controls"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Selected Only",
            value=True,
            description="Whether to key the selected controls, or every control of the selected rigs",
        )

    def is_valid(self) -> bool:
        if not _target_controls(self.option("Selected Only").get()):
            log.warning(_missing_controls_message(self.option("Selected Only").get()))
            return False
        return True

    def run(self) -> None:
        frame = bpy.context.scene.frame_current

        for pose_bone in _target_controls(self.option("Selected Only").get()):
            rotation = _ROTATION_PATHS.get(pose_bone.rotation_mode, "rotation_euler")

            for path in ("location", rotation, "scale"):
                pose_bone.keyframe_insert(path, frame=frame, group=pose_bone.name)
