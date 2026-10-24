"""
GuideMixin gives a component a guide curve which the user shapes in the
viewport, following the same pattern as the Maya spline spine:

    Create Guide    builds the curve from the data stored on the component
                    (or a default if nothing is stored yet)
    Remove Guide    stores the curve's points on the component and deletes it

Only one of the two is offered, depending on whether the guide exists. A
build never reads a live guide: the "Remove All Guides" step at the start of
Build Rig stores and removes any open guide, so the build always uses the
stored data.

A component using it declares a hidden option (named by guide_option, a
dictionary) and provides:

    default_guide_data()    Curve data (see lib.curves) to use when nothing is
                            stored, in the deform armature's space.
    deform_armature()       The armature the points are stored relative to.
    guides_parent()         The object a created guide is parented under.
"""
import logging

import bpy

from aniseed_blender_experimental.lib import curves
from aniseed_blender_experimental.lib.context import action_context

log = logging.getLogger(__name__)

# -- Identifies a guide curve's component, by uuid, so renaming the component
# -- or the curve never loses it
GUIDE_KEY = "aniseed_guide"


class GuideMixin:

    guide_option = "_Guide Curve"

    # ----------------------------------------------------------------------------------
    # xstack integration
    # ----------------------------------------------------------------------------------
    def mixin_functions(self):
        if self.guide_object():
            return {"Remove Guide": self.remove_guide}
        return {"Create Guide": self.create_guide}

    # ----------------------------------------------------------------------------------
    # Declarative surface
    # ----------------------------------------------------------------------------------
    def default_guide_data(self) -> dict:
        return {}

    def guides_parent(self):
        return None

    # ----------------------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------------------
    def guide_data(self) -> dict:
        """
        Returns the stored curve data, or the default if none is stored.
        """
        return self.option(self.guide_option).get() or self.default_guide_data()

    def guide_object(self):
        """
        Returns this component's guide curve, or None if it is not open.
        """
        for obj in bpy.data.objects:
            if obj.get(GUIDE_KEY) == self.uuid():
                return obj
        return None

    def create_guide(self):
        """
        Creates the guide curve from the stored (or default) data.
        """
        if self.guide_object():
            return self.guide_object()

        data = self.guide_data()
        if not data or not data.get("points"):
            log.warning(f"{self.label()} : there is no guide data, create the bones first")
            return None

        with action_context(f"Create Guide : {self.label()}", rig=self.rig):
            obj = curves.create(
                self.config.generate_name(self.config.guide, f"{self.option('Description').get()} Curve", self.option("Location").get()),
                data,
                space_object=self.deform_armature(),
                parent=self.guides_parent(),
            )
            obj[GUIDE_KEY] = self.uuid()
            obj.show_in_front = True
            obj.data.resolution_u = 24

            return obj

    def remove_guide(self):
        """
        Stores the guide curve's points on the component and deletes it.
        """
        obj = self.guide_object()
        if obj is None:
            return

        with action_context(f"Remove Guide : {self.label()}", rig=self.rig):
            self.option(self.guide_option).set(curves.serialise(obj, self.deform_armature()))

            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if not data.users:
                bpy.data.curves.remove(data)
