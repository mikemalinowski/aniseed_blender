"""
Provides "Experiment : Control Visuals", which holds the look of the rig's
controls (shape, size and colour) so it survives rebuilds.

The limb components give their controls a default look as they build them.
Tailor the controls in Blender (Bone properties > Viewport Display > Custom
Shape, and Bone Color), then press Snapshot on this component to store them.
Every build after that re-applies what is stored, control by control, so a
control added later still gets its default.
"""
import logging

import aniseed

from aniseed_blender_experimental import base
from aniseed_blender_experimental.lib import armature as armature_lib

log = logging.getLogger(__name__)


class ControlVisuals(aniseed.RigComponent):
    """
    Re-applies the stored shape, size and colour of each control. Use
    Snapshot to store the controls as they look now, or Snapshot Selected to
    store (or update) just the selected controls.
    """

    identifier = "Experiment : Control Visuals"

    # -- Version 1 stores {bone: {"shape": str, "size": [x, y, z], "color": ...}}.
    # -- Adding more keys later (offsets, wire width...) only needs a version
    # -- bump if existing data has to be converted.
    version = 1

    BUTTONS = ("Snapshot", "Snapshot Selected", "Clear", "Save File", "Load File")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Apply",
            value=True,
            description="If off, the stored visuals are not applied, and the controls keep their defaults",
        )

        for button in self.BUTTONS:
            self.declare_option(name=button, value=None, description=f"{button} the stored control visuals")

        self.declare_option(
            name="_Visuals",
            value=dict(),
            hidden=True,
            description="The stored visuals, keyed by control bone",
        )

    def option_widget(self, option_name):
        functions = {
            "Snapshot": self.snapshot,
            "Snapshot Selected": self.snapshot_selected,
            "Clear": self.clear,
            "Save File": self.save_file,
            "Load File": self.load_file,
        }
        if option_name in functions:
            return aniseed.widgets.ButtonWidget(button_name=option_name, func=functions[option_name])
        return None

    def run(self):
        if not self.option("Apply").get():
            return True

        control = armature_lib.find_role(self.rig.label, armature_lib.CONTROL)
        if control is None:
            log.warning(f"{self.label()} : there is no control armature to apply visuals to")
            return True

        for bone, visual in self.option("_Visuals").get().items():
            if bone not in control.pose.bones:
                continue
            base.apply_visual(control, self.rig.label, self.config, bone, visual)

        return True

    # ----------------------------------------------------------------------------------
    def visuals(self) -> dict:
        return dict(self.option("_Visuals").get())

    def snapshot(self) -> int:
        """
        Stores the visuals of every control (every control armature bone with
        a custom shape), replacing anything stored before. Returns how many
        were stored.
        """
        control = self._control_armature()
        if control is None:
            return 0

        visuals = {
            pose_bone.name: base.read_visual(control, pose_bone.name)
            for pose_bone in control.pose.bones
            if pose_bone.custom_shape
        }
        self.option("_Visuals").set(visuals)

        log.info(f"{self.label()} : stored the visuals of {len(visuals)} control(s)")
        return len(visuals)

    def snapshot_selected(self) -> int:
        """
        Stores (or updates) the visuals of the selected controls only.
        """
        control = self._control_armature()
        if control is None:
            return 0

        visuals = self.visuals()
        selected = [
            pose_bone.name
            for pose_bone in control.pose.bones
            if pose_bone.custom_shape and _is_selected(pose_bone)
        ]

        for bone in selected:
            visuals[bone] = base.read_visual(control, bone)

        self.option("_Visuals").set(visuals)

        log.info(f"{self.label()} : stored the visuals of {len(selected)} selected control(s)")
        return len(selected)

    def clear(self):
        aniseed.dialogs.clear_option(
            self.option("_Visuals"),
            title="Clear Control Visuals",
            message="Are you sure you want to clear the stored control visuals?",
            empty_value=dict(),
        )

    def save_file(self):
        aniseed.dialogs.save_json_file(title="Save Control Visuals", get_data=self.visuals)

    def load_file(self):
        aniseed.dialogs.load_json_file(title="Load Control Visuals", option=self.option("_Visuals"))

    def _control_armature(self):
        control = armature_lib.find_role(self.rig.label, armature_lib.CONTROL)
        if control is None:
            log.warning(f"{self.label()} : build the rig before taking a snapshot")
        return control


def _is_selected(pose_bone) -> bool:
    """
    Returns whether the pose bone is selected. Blender 5 moved selection
    from the bone to the pose bone.
    """
    if hasattr(pose_bone, "select"):
        return pose_bone.select
    return pose_bone.bone.select
