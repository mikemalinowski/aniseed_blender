"""
Provides "Experiment : Singular": a single bone driven by a single control.
Mirrorable.
"""
import logging

import aniseed

from aniseed_blender_experimental import base
from aniseed_blender_experimental.lib import widgets
from aniseed_blender_experimental.mixins import BoneSpec, MirrorMixin

log = logging.getLogger(__name__)

class Singular(base.LimbComponent, MirrorMixin):
    """
    Creates one bone (at the tail of the selected DEF bone, or of the parent
    component's bone, pointing up) and builds one control matching it, which
    drives it.
    """

    identifier = "Experiment : Singular"
    default_description = "Singular"
    bone_input_names = ["Bone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(
            name="Bone",
            value="",
            description="The DEF bone to drive",
            group="Skeleton",
        )

        self.declare_option(
            name="Shape",
            value="core_cube",
            description="The shape of the control",
            group="Visuals",
            pre_expose=True,
        )

        self.declare_output(name="Control", description="The control, which drives the bone", is_default=True)

    def option_widget(self, option_name):
        if option_name == "Shape":
            return aniseed.widgets.ItemSelector(sorted(widgets.library()), self.option("Shape").get())
        return super().option_widget(option_name)

    # ----------------------------------------------------------------------------------
    def bone_layout(self):
        return [
            BoneSpec("bone", "Bone", (), self.option("Description").get(), head=(0, 0, 0), tail=(0, 0, 0.1)),
        ]

    def layout_anchor(self):
        # -- The layout starts at the origin, so the bone starts at the tail of
        # -- the bone it is created beneath (or at the origin if there is none)
        return (0, 0, 0)

    def attach_bone(self, tag):
        return self.input("Bone").get()

    def is_valid(self):
        if self.option("Shape").get() not in widgets.library():
            log.warning(f"{self.label()} : there is no shape called {self.option('Shape').get()!r}")
            return False
        return super().is_valid()

    # ----------------------------------------------------------------------------------
    def run(self):
        builder = base.Builder(self)
        bone = self.input("Bone").get()

        with builder.editing():
            control = builder.copy_bone(bone, "control", parent=self.control_parent())

        builder.make_control(control, self.option("Shape").get())

        builder.bind(bone, control)

        self.output("Control").set(control)
        return True
