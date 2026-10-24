"""
Provides "Experiment : Root", the top of the rig: a root bone, driven by a
root control with an offset control beneath it.
"""
import math

from aniseed_blender_experimental import base
from aniseed_blender_experimental.mixins import BoneSpec


class Root(base.LimbComponent):
    """
    Creates a root bone at the origin, and builds a root control and an
    offset control beneath it, which drives the root bone. Everything else in
    the rig moves with the offset control.
    """

    identifier = "Experiment : Root"
    default_description = "Root"
    bone_input_names = ["Root"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(
            name="Root",
            value="",
            description="The root DEF bone",
            group="Skeleton",
        )

        self.declare_option(
            name="Deform Root",
            value=True,
            description="Whether the root bone deforms (games often need it for root motion)",
            group="Creation",
        )

        self.declare_output(name="Root Control", description="The root control")
        self.declare_output(name="Offset Control", description="The offset control, which drives the root bone", is_default=True)

    def bone_layout(self):
        return [
            BoneSpec("root", "Root", (), "Root", head=(0, 0, 0), tail=(0, 0.5, 0)),
        ]

    def create_extras(self, names):
        if not self.option("Deform Root").get():
            self.deform_armature().data.bones[names["root"]].use_deform = False

    def attach_bone(self, tag):
        return self.input("Root").get()

    def run(self):
        builder = base.Builder(self)
        root_bone = self.input("Root").get()
        length = builder.rest(root_bone)["length"]

        with builder.editing():
            root = builder.copy_bone(root_bone, "control", parent=self.control_parent())
            offset = builder.copy_bone(root_bone, "control", "Offset", parent=root, length=length * 0.8)

        # -- The root bone lies flat, pointing forward, so the shapes are turned
        # -- to lie on the ground
        flat = (math.radians(90), 0, 0)
        builder.make_control(root, "circle", size=2.4, rotation=flat)
        builder.make_control(offset, "circle", size=2.4, color=base.SECONDARY_COLOR, rotation=flat)

        builder.bind(root_bone, offset)

        self.output("Root Control").set(root)
        self.output("Offset Control").set(offset)
        return True
