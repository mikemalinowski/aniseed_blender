"""
Riggers Toolkit tools for control shapes: applying shapes from the shape
library, saving shapes into it, and copying a shape from one control to
others.
"""
import re
import logging

import bpy
import aniseed

from aniseed_blender_standard.toolkit import core
from aniseed_blender_standard.toolkit import scene
from aniseed_blender_experimental.lib import widgets

log = logging.getLogger(__name__)

# -- What Copy Shape copied, for Paste Shape
_CLIPBOARD = dict()

# -- The characters a shape name (which is its file name) may use
_SHAPE_NAME = re.compile(r"[A-Za-z0-9_\-]+")


def _warn_if_rebuilt(pose_bones) -> None:
    """
    Warns when any of the pose bones are on a rig's control armature, which
    every build recreates.
    """
    if any(scene.is_control_armature(pose_bone.id_data) for pose_bone in pose_bones):
        log.warning(
            "The control armature is rebuilt by every build. To keep these shapes, "
            "snapshot them with the rig's Control Visuals component."
        )


# --------------------------------------------------------------------------------------
class ApplyShape(core.Tool):
    """
    Gives the selected pose bones a shape from the shape library. The shape
    is drawn by a widget object in the rig's hidden widget collection. Turn
    on Set Size to also set the size the shape is drawn at.

    A rig's control armature is rebuilt by every build, so snapshot shapes
    applied to it with the rig's Control Visuals component to keep them.
    """

    identifier = "Apply Shape"
    toolkit = "Riggers"
    categories = ["Shapes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Shape",
            value="core_circle",
            description="The shape to apply, from the shape library",
        )

        self.declare_option(
            name="Set Size",
            value=False,
            description="Whether to also set the size the shape is drawn at",
        )

        self.declare_option(
            name="Size",
            value=1.0,
            description="The size to draw the shape at, if Set Size is on",
        )

    def option_widget(self, option_name: str):
        if option_name == "Shape":
            return aniseed.widgets.ItemSelector(sorted(widgets.library()), self.option("Shape").get())
        return None

    def is_valid(self) -> bool:
        if self.option("Shape").get() not in widgets.library():
            log.warning(f"There is no shape called {self.option('Shape').get()!r}")
            return False

        if not scene.selected_pose_bones():
            log.warning("Select the pose bones to apply the shape to, in pose mode")
            return False

        return True

    def run(self) -> None:
        shape = self.option("Shape").get()
        pose_bones = scene.selected_pose_bones()

        for pose_bone in pose_bones:
            rig_label = scene.rig_root(pose_bone.id_data).name
            pose_bone.custom_shape = widgets.widget(rig_label, shape, f"WGT_{rig_label}_{shape}")

            if self.option("Set Size").get():
                pose_bone.custom_shape_scale_xyz = [self.option("Size").get()] * 3

        _warn_if_rebuilt(pose_bones)


# --------------------------------------------------------------------------------------
class SaveShape(core.Tool):
    """
    Saves a shape into the shape library, so it can be applied like any
    other. The shape is taken from the active pose bone's custom shape or,
    without one, from the active curve or mesh object.

    The shape is saved as it is drawn in the widget object's own space, so a
    pose bone's custom shape offset, rotation and scale are not included.
    """

    identifier = "Save Shape"
    toolkit = "Riggers"
    categories = ["Shapes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Name",
            value="",
            description="The name of the shape (its file name in the shape library)",
        )

        self.declare_option(
            name="Overwrite",
            value=False,
            description="Whether to replace a shape which already has this name",
        )

    @staticmethod
    def source():
        """
        Returns the object to save the shape of, or None.
        """
        pose_bone = scene.active_pose_bone()
        if pose_bone is not None and pose_bone.custom_shape is not None:
            return pose_bone.custom_shape

        obj = bpy.context.view_layer.objects.active
        if obj is not None and obj.type in ("CURVE", "MESH"):
            return obj

        return None

    def is_valid(self) -> bool:
        name = self.option("Name").get()

        if not _SHAPE_NAME.fullmatch(name or ""):
            log.warning("Give the shape a name, using only letters, numbers, - and _")
            return False

        if name in widgets.library() and not self.option("Overwrite").get():
            log.warning(f"There is already a shape called {name!r}. Turn on Overwrite to replace it.")
            return False

        if self.source() is None:
            log.warning("Make a pose bone with a custom shape, or a curve or mesh object, active")
            return False

        return True

    def run(self) -> bool:
        source = self.source()
        path = widgets.shape_path(self.option("Name").get())

        if not widgets.save_shape(source, path):
            log.warning(f"{source.name} has no curves or edges to save")
            return False

        log.info(f"Saved the shape of {source.name} to {path}")
        return True


# --------------------------------------------------------------------------------------
class CopyShape(core.Tool):
    """
    Remembers the active pose bone's shape: its custom shape object and the
    offset, rotation and scale it is drawn with. Paste Shape gives them to
    other pose bones.
    """

    identifier = "Copy Shape"
    toolkit = "Riggers"
    categories = ["Shapes"]

    def is_valid(self) -> bool:
        pose_bone = scene.active_pose_bone()

        if pose_bone is None or pose_bone.custom_shape is None:
            log.warning("Make a pose bone with a custom shape active, in pose mode")
            return False

        return True

    def run(self) -> None:
        pose_bone = scene.active_pose_bone()

        _CLIPBOARD.clear()
        _CLIPBOARD.update(
            source=pose_bone.name,
            shape=pose_bone.custom_shape.name,
            scale=list(pose_bone.custom_shape_scale_xyz),
            translation=list(pose_bone.custom_shape_translation),
            rotation=list(pose_bone.custom_shape_rotation_euler),
        )
        log.info(f"Copied the shape of {pose_bone.name}")


# --------------------------------------------------------------------------------------
class PasteShape(core.Tool):
    """
    Gives the selected pose bones the shape copied with Copy Shape.
    """

    identifier = "Paste Shape"
    toolkit = "Riggers"
    categories = ["Shapes"]

    def is_valid(self) -> bool:
        if not _CLIPBOARD:
            log.warning("Copy a shape with Copy Shape first")
            return False

        if _CLIPBOARD["shape"] not in bpy.data.objects:
            log.warning(f"The copied shape ({_CLIPBOARD['shape']}) no longer exists")
            return False

        if not scene.selected_pose_bones():
            log.warning("Select the pose bones to paste the shape onto, in pose mode")
            return False

        return True

    def run(self) -> None:
        pose_bones = scene.selected_pose_bones()

        for pose_bone in pose_bones:
            pose_bone.custom_shape = bpy.data.objects[_CLIPBOARD["shape"]]
            pose_bone.custom_shape_scale_xyz = _CLIPBOARD["scale"]
            pose_bone.custom_shape_translation = _CLIPBOARD["translation"]
            pose_bone.custom_shape_rotation_euler = _CLIPBOARD["rotation"]

        _warn_if_rebuilt(pose_bones)
