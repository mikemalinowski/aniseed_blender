"""
Provides "Experiment : Create Control Armature", which creates the armature
the limb components build their controls in, and "Experiment : Delete Control
Rig", which removes it (and everything else a build creates) again.
"""
import logging

import bpy

import aniseed

from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import widgets

log = logging.getLogger(__name__)

# -- The custom property the Blender host checks to leave an object out of the
# -- recipe (aniseed_blender_standard/hosts/blender.py)
TRANSIENT_KEY = "aniseed_transient"

# -- The bone collections every control armature starts with, in display order
COLLECTIONS = ["Controls", "FK", "IK", "Fingers", "Properties", "Mechanics"]


class CreateControlArmature(aniseed.RigComponent):
    """
    Creates the control armature: an empty armature at the deform armature's
    position, tagged so the limbs (and Delete Control Rig) can find it.
    """

    identifier = "Experiment : Create Control Armature"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(
            name="Parent",
            value="",
            description="The object the control armature is parented under, normally the controls group",
            group="Scene",
        )

        self.declare_input(
            name="Deform Armature",
            value="",
            description="The deform armature, which the control armature is placed on. Found automatically if empty.",
            validate=False,
            group="Scene",
        )

        self.declare_output(
            name="Armature",
            description="The control armature object",
            is_default=True,
        )

    def input_widget(self, requirement_name):
        if requirement_name in ("Parent", "Deform Armature"):
            return aniseed.widgets.ObjectSelector(component=self)
        return None

    def run(self):
        if armature_lib.find_role(self.rig.label, armature_lib.CONTROL):
            log.warning(f"{self.label()} : a control armature already exists. Run Make Rig Editable first.")
            return False

        parent = bpy.data.objects[self.input("Parent").get()]
        deform = (
            bpy.data.objects.get(self.input("Deform Armature").get() or "")
            or armature_lib.find_role(self.rig.label, armature_lib.DEFORM)
        )

        armature = armature_lib.create_armature(
            self.config.generate_name(self.config.control, "Armature", self.config.middle),
            parent=parent,
            role=armature_lib.CONTROL,
        )
        armature.show_in_front = True
        armature.data.display_type = "WIRE"

        # -- Tells the Blender host not to store it with the recipe, as every
        # -- build recreates it
        armature[TRANSIENT_KEY] = True

        bpy.context.view_layer.update()
        if deform is not None:
            armature.matrix_world = deform.matrix_world.copy()

        for name in COLLECTIONS:
            armature.data.collections.new(name)

        self.output("Armature").set(armature.name)
        return True


class DeleteControlRig(aniseed.RigComponent):
    """
    Removes everything a build creates: the control armature, the curves it
    uses (such as the spine's Spline IK curve) and the control widgets.
    """

    identifier = "Experiment : Delete Control Rig"

    def run(self):
        for obj in armature_lib.find_all_roles(self.rig.label, [armature_lib.CONTROL, armature_lib.CONTROL_CURVE]):
            armature_lib.remove_object(obj)

        widgets.remove_widgets(self.rig.label)
        return True
