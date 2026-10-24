"""
Provides "Experiment : Set Mode", which puts one of the rig's armatures (or
any object) into object, pose or edit mode. The host leaves modes and the
selection alone, so the stack decides what state the rig is left in.
"""
import logging

import bpy

import aniseed

from aniseed_blender_experimental.lib import armature as armature_lib

log = logging.getLogger(__name__)

MODES = {"Object": "OBJECT", "Pose": "POSE", "Edit": "EDIT"}
TARGETS = {"Control Armature": armature_lib.CONTROL, "Deform Armature": armature_lib.DEFORM}


class SetMode(aniseed.RigComponent):
    """
    Object mode leaves whatever mode the active object is in, and changes
    nothing else (this commits any unfinished bone edits, so use it before
    anything which reads the deform bones).

    Pose and Edit make the target the only selected object and the active
    one, then put it into that mode. The target is the Object input if it is
    given, otherwise the armature chosen by Target.
    """

    identifier = "Experiment : Set Mode"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(
            name="Object",
            value="",
            description="The object to put into the mode. If empty, Target is used",
            validate=False,
        )

        self.declare_option(
            name="Mode",
            value="Object",
            description="The mode to enter",
            pre_expose=True,
        )

        self.declare_option(
            name="Target",
            value="Control Armature",
            description="The rig armature to put into the mode, if Object is empty",
            pre_expose=True,
        )

    def input_widget(self, requirement_name):
        if requirement_name == "Object":
            return aniseed.widgets.ObjectSelector(component=self)
        return None

    def option_widget(self, option_name):
        if option_name == "Mode":
            return aniseed.widgets.ItemSelector(list(MODES), self.option("Mode").get())
        if option_name == "Target":
            return aniseed.widgets.ItemSelector(list(TARGETS), self.option("Target").get())
        return None

    def is_valid(self):
        if self.option("Mode").get() not in MODES:
            log.warning(f"{self.label()} : Mode must be one of {', '.join(MODES)}")
            return False

        if not self.input("Object").get() and self.option("Target").get() not in TARGETS:
            log.warning(f"{self.label()} : Target must be one of {', '.join(TARGETS)}")
            return False

        return True

    def run(self):
        mode = MODES[self.option("Mode").get()]
        view_layer = bpy.context.view_layer

        leave_mode(view_layer.objects.active)
        if mode == "OBJECT":
            return True

        target = self.target()
        if target is None or target.name not in view_layer.objects:
            log.warning(f"{self.label()} : there is no object to put into {mode.lower()} mode")
            return False

        for obj in view_layer.objects:
            obj.select_set(obj == target)
        view_layer.objects.active = target

        with bpy.context.temp_override(active_object=target, object=target):
            bpy.ops.object.mode_set(mode=mode)

        return True

    def target(self):
        """
        Returns the object given as the Object input, or the rig armature
        chosen by Target, or None.
        """
        name = self.input("Object").get()
        if name:
            return bpy.data.objects.get(name)

        return armature_lib.find_role(self.rig.label, TARGETS[self.option("Target").get()])


def leave_mode(obj) -> None:
    """
    Returns the object to object mode, if it is in any other.
    """
    if obj is None or obj.mode == "OBJECT":
        return

    with bpy.context.temp_override(active_object=obj, object=obj):
        bpy.ops.object.mode_set(mode="OBJECT")
