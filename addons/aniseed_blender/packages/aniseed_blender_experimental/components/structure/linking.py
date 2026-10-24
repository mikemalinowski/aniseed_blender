"""
Provides "Experiment : Link Deformation Rig", which constrains every deform
bone to the control armature bone driving it, and "Experiment : Unlink
Deformation Rig", which removes those constraints again so the deform bones
can be edited.
"""
import logging

import bpy

import aniseed

from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import rigging

log = logging.getLogger(__name__)

# -- Every link constraint is given this name, so unlinking only removes
# -- constraints aniseed added
LINK_CONSTRAINT = "aniseed_link"

# -- What the link constraints were called before, so rigs built then can
# -- still be unlinked
LEGACY_CONSTRAINTS = ("aniseed_bind",)


class LinkDeformationRig(aniseed.RigComponent):
    """
    Adds a world space Copy Transforms constraint to each deform bone,
    targeting the control armature bone which the components marked as
    driving it (with an "aniseed_drives" custom property, see
    base.Builder.bind).
    """

    identifier = "Experiment : Link Deformation Rig"

    def run(self):
        deform = armature_lib.find_role(self.rig.label, armature_lib.DEFORM)
        control = armature_lib.find_role(self.rig.label, armature_lib.CONTROL)

        if deform is None or control is None:
            log.warning(f"{self.label()} : the deform and control armatures must both exist")
            return False

        linked = 0
        for control_bone in control.data.bones:
            deform_bone = control_bone.get(armature_lib.DRIVES_KEY)
            if not deform_bone:
                continue

            if deform_bone not in deform.pose.bones:
                log.warning(f"{self.label()} : {control_bone.name} drives {deform_bone}, which does not exist, skipping")
                continue

            rigging.constrain(
                deform.pose.bones[deform_bone],
                "COPY_TRANSFORMS",
                name=LINK_CONSTRAINT,
                target=control,
                subtarget=control_bone.name,
            )
            linked += 1

        log.info(f"{self.label()} : linked {linked} deform bone(s)")
        return True


class UnlinkDeformationRig(aniseed.RigComponent):
    """
    Removes the link constraints from the deform armature, puts it back in
    its rest pose, and shows it, so its bones can be edited.
    """

    identifier = "Experiment : Unlink Deformation Rig"

    def run(self):
        deform = armature_lib.find_role(self.rig.label, armature_lib.DEFORM)
        if deform is None:
            return True

        prefixes = (LINK_CONSTRAINT,) + LEGACY_CONSTRAINTS
        for pose_bone in deform.pose.bones:
            for constraint in list(pose_bone.constraints):
                if constraint.name.startswith(prefixes):
                    pose_bone.constraints.remove(constraint)

        armature_lib.reset_pose(deform)

        deform.hide_viewport = False
        if deform.name in bpy.context.view_layer.objects:
            deform.hide_set(False)

        return True
