"""
Riggers Toolkit tools for how controls are drawn.
"""
import logging

import bpy
import aniseed

from aniseed_blender_standard.toolkit import core
from aniseed_blender_standard.toolkit import scene

log = logging.getLogger(__name__)

CUSTOM = "CUSTOM"


def _palettes() -> list:
    """
    Returns Blender's bone colour palettes (DEFAULT, THEME01... and CUSTOM).
    """
    return [item.identifier for item in bpy.types.BoneColor.bl_rna.properties["palette"].enum_items]


def _towards_white(colour, amount: float) -> list:
    return [value + (1.0 - value) * amount for value in colour]


# --------------------------------------------------------------------------------------
class SetControlColour(core.Tool):
    """
    Sets the colour the selected pose bones are drawn with: one of Blender's
    theme colours, or (with the CUSTOM palette) the custom colour. The
    selected and active colours of a custom colour are lighter versions of
    it.
    """

    identifier = "Set Control Colour"
    toolkit = "Riggers"
    categories = ["Controls"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Palette",
            value="THEME01",
            description="The colour palette to use. CUSTOM uses the custom colour",
        )

        self.declare_option(
            name="Custom Colour",
            value=[255, 160, 0],
            description="The colour used with the CUSTOM palette",
        )

    def option_widget(self, option_name: str):
        if option_name == "Palette":
            return aniseed.widgets.ItemSelector(_palettes(), self.option("Palette").get())

        if option_name == "Custom Colour":
            return aniseed.widgets.ColorPicker(self.option("Custom Colour").get())

        return None

    def is_valid(self) -> bool:
        if self.option("Palette").get() not in _palettes():
            log.warning(f"There is no colour palette called {self.option('Palette').get()!r}")
            return False

        if not scene.selected_pose_bones():
            log.warning("Select the pose bones to colour, in pose mode")
            return False

        return True

    def run(self) -> None:
        palette = self.option("Palette").get()
        colour = [value / 255.0 for value in self.option("Custom Colour").get()]
        pose_bones = scene.selected_pose_bones()

        for pose_bone in pose_bones:
            pose_bone.color.palette = palette

            if palette == CUSTOM:
                pose_bone.color.custom.normal = colour
                pose_bone.color.custom.select = _towards_white(colour, 0.5)
                pose_bone.color.custom.active = _towards_white(colour, 0.8)

        if any(scene.is_control_armature(pose_bone.id_data) for pose_bone in pose_bones):
            log.warning(
                "The control armature is rebuilt by every build. To keep these colours, "
                "snapshot them with the rig's Control Visuals component."
            )
