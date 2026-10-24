"""
Provides "Experiment : Remove All Guides", which stores and removes every open
guide in the rig, so a build always uses the guide data stored on the
components rather than whatever happens to be in the scene.
"""
import aniseed

from aniseed_blender_experimental.mixins import GuideMixin


class RemoveAllGuides(aniseed.RigComponent):
    """
    Calls Remove Guide on every component in the rig which has a guide open.
    """

    identifier = "Experiment : Remove All Guides"

    def run(self):
        for component in self.rig.components():
            if isinstance(component, GuideMixin) and component.guide_object():
                component.remove_guide()
        return True
