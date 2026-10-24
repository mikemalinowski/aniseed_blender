"""
Provides "Rig Configuration : Experiment", which names everything in the form
TYPE_ObjectDescription_##_LOCATION (for example DEF_UpperArm_01_L), and sets
up the Make Rig Editable / Build Rig stack, the rig's groups and the deform
armature when a new rig is created with it.
"""
import re
import logging

import bpy

import aniseed
from aniseed.config import NamingConventionError

from aniseed_blender_experimental.lib import armature as armature_lib

log = logging.getLogger(__name__)


class ExperimentConfig(aniseed.RigConfiguration):
    """
    Names things TYPE_ObjectDescription_##_LOCATION, with underscores only.
    The counter starts at 01 and increases until the name is unique across
    the file's objects and the bones of the rig's armatures.

    New rigs start with a Make Rig Editable block (which removes the control
    rig) and a Build Rig block (which rebuilds it), the rig's groups and an
    empty deform armature. Add the limb components beneath the "Components"
    organiser in Build Rig.
    """

    identifier = "Rig Configuration : Experiment"

    # -- Locations. L and R as the last part of a name are recognised by
    # -- Blender's own name flipping (Paste Pose Flipped, X-Axis Mirror)
    left = "L"
    right = "R"
    middle = "M"
    front = "FR"
    back = "BK"

    # -- Types
    organisational = "ORG"
    control = "CTL"
    joint = "DEF"
    zero = "ZRO"
    offset = "OFF"
    mechanical = "MECH"
    guide = "GDE"
    widget = "WGT"

    # -- The labels of the blocks created by the default stack, which other
    # -- components look up
    EDITABLE_BLOCK = "Make Rig Editable"
    BUILD_BLOCK = "Build Rig"
    COMPONENTS_ORGANISER = "Components"

    def generate_name(
            self,
            classification: str,
            description: str,
            location: str,
            counter: int = 1,
            unique: bool = True,
    ) -> str:
        """
        Returns a name in the form TYPE_ObjectDescription_##_LOCATION.

        The description is made PascalCase so it is always a single part of
        the name ("upper arm", "upper_arm" and "upperArm" all become UpperArm).

        Args:
            classification: The type token, or the name of one of this
                configuration's tokens (such as "joint").
            description: What the thing is.
            location: The location token, or the name of one (such as "left").
            counter: The number to start counting from.
            unique: If True, the counter is increased until no object in the
                file, and no bone in the rig's armatures, has the name.
        """
        location = getattr(self, location, location)
        classification = getattr(self, classification, classification)
        description = self.format_description(description)

        taken = self._taken_names() if unique else set()

        while True:
            name = f"{classification}_{description}_{counter:02d}_{location}"

            if name not in taken:
                return name

            counter += 1

    @staticmethod
    def format_description(description: str) -> str:
        """
        Returns the description as PascalCase, with no separators.
        """
        words = [word for word in re.split(r"[\s_\-.]+", description or "") if word]

        if not words:
            log.warning("No description given for a name, using 'Unnamed'")
            words = ["Unnamed"]

        return "".join(word[0].upper() + word[1:] for word in words)

    def _taken_names(self) -> set:
        """
        Returns every object name in the file and every bone name in the rig's
        armatures (including any in edit mode).
        """
        taken = set(bpy.data.objects.keys())

        for armature in armature_lib.rig_armatures(self.rig.label):
            taken.update(armature_lib.bone_names(armature))

        return taken

    # -- The extract functions reverse generate_name, so they must agree with
    # -- it exactly

    def extract_location(self, name: str) -> str:
        return self._parts(name)[3]

    def extract_classification(self, name: str) -> str:
        return self._parts(name)[0]

    def extract_description(self, name: str) -> str:
        return self._parts(name)[1]

    def extract_counter(self, name: str) -> int:
        try:
            return int(self._parts(name)[2])

        except ValueError as exc:
            raise NamingConventionError(f"Could not extract counter from {name!r}") from exc

    @staticmethod
    def _parts(name: str):
        """
        Splits a name into its type, description, counter and location.
        """
        match = re.match(r"^([A-Z]+)_([^_]+)_(\d+)_([A-Z]+)$", name or "")

        if not match:
            raise NamingConventionError(
                f"{name!r} is not in the form TYPE_ObjectDescription_##_LOCATION"
            )

        return match.groups()

    # ----------------------------------------------------------------------------------
    def create_default_stack(self):
        """
        Called when this configuration is the first component of a new rig.
        Creates the rig's groups and the deform armature, adds the Make Rig
        Editable and Build Rig blocks, and leaves the rig editable.
        """
        rig_object = bpy.data.objects[self.rig.label]

        skeleton_org = self._create_empty(self.generate_name(self.organisational, "Skeleton", self.middle), rig_object)
        controls_org = self._create_empty(self.generate_name(self.organisational, "Controls", self.middle), rig_object)
        self._create_empty(self.generate_name(self.organisational, "Guides", self.middle), rig_object)

        if not armature_lib.find_role(self.rig.label, armature_lib.DEFORM):
            deform = armature_lib.create_armature(
                self.generate_name(self.joint, "Armature", self.middle),
                parent=skeleton_org,
                role=armature_lib.DEFORM,
            )
            deform.show_in_front = True

        # -- Make Rig Editable removes the control rig, so the deform bones
        # -- can be edited. It starts by leaving any mode the user is in,
        # -- which also commits any unfinished bone edits
        editable = self.rig.add_component("Stack : Execution Block", label=self.EDITABLE_BLOCK)
        self.rig.add_component(
            "Experiment : Set Mode",
            label="Enter Object Mode",
            options={"Mode": "Object"},
            parent=editable,
        )
        self.rig.add_component("Experiment : Unlink Deformation Rig", label="Unlink Deformation Rig", parent=editable)
        self.rig.add_component("Experiment : Delete Control Rig", label="Delete Control Rig", parent=editable)

        # -- Build Rig always starts from an editable rig
        build = self.rig.add_component("Stack : Execution Block", label=self.BUILD_BLOCK)
        self.rig.add_component(
            "Stack : Run Execution Block",
            label="Ensure Rig Is Editable",
            inputs={"Execution Block Label": self.EDITABLE_BLOCK},
            parent=build,
        )
        self.rig.add_component("Experiment : Remove All Guides", label="Remove All Guides", parent=build)
        self.rig.add_component(
            "Experiment : Create Control Armature",
            label="Create Control Armature",
            inputs={"Parent": controls_org.name},
            parent=build,
        )
        self.rig.add_component("Stack : Organiser", label=self.COMPONENTS_ORGANISER, parent=build)

        post_build = self.rig.add_component("Stack : Organiser", label="Post Build", parent=build)
        self.rig.add_component("Experiment : Link Deformation Rig", label="Link Deformation Rig", parent=post_build)
        self.rig.add_component("Experiment : Control Visuals", label="Control Visuals", parent=post_build)
        self.rig.add_component("Experiment : Finalise", label="Finalise", parent=post_build)
        self.rig.add_component(
            "Experiment : Set Mode",
            label="Enter Pose Mode",
            options={"Mode": "Pose", "Target": "Control Armature"},
            parent=post_build,
        )

        self.rig.build(build_below=editable)

    @staticmethod
    def _create_empty(name, parent):
        """
        Returns the Empty with the given name, creating it under the parent
        (and in the parent's collection) if it does not exist.
        """
        obj = bpy.data.objects.get(name)
        if obj is not None:
            return obj

        obj = bpy.data.objects.new(name, None)
        (parent.users_collection[0] if parent.users_collection else bpy.context.scene.collection).objects.link(obj)
        obj.parent = parent
        return obj
