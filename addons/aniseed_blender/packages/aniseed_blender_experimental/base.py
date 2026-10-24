"""
The base class shared by the limb components, and the Builder they use to
create control rig bones during a build.

Every limb works the same way:

    * Its inputs name bones in the deform (DEF) armature. CreateBonesMixin
      creates them when the component is added, if they are empty, as
      children of the selected DEF bone (or of the parent component's bone).
      From then on the deform hierarchy lives in the armature alone.
    * Its build creates control (CTL) and mechanical (MECH) bones in the
      control armature, and marks each bone which drives a DEF bone (see
      Builder.bind), so "Link Deformation Rig" can constrain the DEF bones
      to them.
    * Its "Parent" input is the control armature bone everything it builds
      is parented to, normally an address of another component's output.
      When the component is added beneath another, it is hooked to that
      component's default output (or an output matching parent_tags). The
      control hierarchy is therefore free to differ from the deform one.
    * It has an output for every control it creates, and for mechanical
      bones other components may find useful, such as the blended bones.

Component modules must import this module (``from aniseed_blender_experimental
import base``) rather than importing LimbComponent by name, as the component
factory registers every RigComponent subclass found in a module's namespace.
"""
import typing
import logging
import contextlib

import bpy
from mathutils import Vector

import aniseed

from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import rigging
from aniseed_blender_experimental.lib import widgets
from aniseed_blender_experimental.mixins import CreateBonesMixin

log = logging.getLogger(__name__)

# -- Blender's bone colour themes used for each side by default
SIDE_COLORS = {
    "left": "THEME04",
    "right": "THEME01",
    "middle": "THEME09",
}

# -- Used for controls which are secondary to the main ones, such as fingers
SECONDARY_COLOR = "THEME03"

# -- Bone collections in the control armature
CONTROLS = "Controls"
FK = "FK"
IK = "IK"
FINGERS = "Fingers"
PROPERTIES = "Properties"
MECHANICS = "Mechanics"


# --------------------------------------------------------------------------------------
class LimbComponent(aniseed.RigComponent, CreateBonesMixin):
    """
    Base class for the experiment's limb components.
    """

    # -- The defaults for the Description and Location options. The location
    # -- is the name of a configuration token, such as "left".
    default_description = "Limb"
    default_location = "middle"

    # -- Which bone this component attaches to when added beneath another
    # -- limb. The parent limb's attach_bone() is given this tag.
    attach_tag = "end"

    # -- The tags given to hook_to_parent when the component is added beneath
    # -- another: the first of the parent's outputs whose name contains one of
    # -- them becomes the Parent, falling back to the parent's default output
    parent_tags = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(
            name="Parent",
            value="",
            description=(
                "The control armature bone this component's controls are parented to, "
                "normally another component's output"
            ),
            validate=False,
            group="Control Rig",
        )

        deform = armature_lib.find_role(self.rig.label, armature_lib.DEFORM) if self.rig else None

        self.declare_input(
            name="Deform Armature",
            value=deform.name if deform else "",
            description="The armature holding the deform (DEF) bones this component builds from",
            group="Skeleton",
        )

        self.declare_option(
            name="Description",
            value=self.default_description,
            description="Used when naming the controls",
            group="Naming",
            pre_expose=True,
        )

        self.declare_option(
            name="Location",
            value=getattr(self.config, self.default_location, self.default_location),
            description="The location (side) token used when naming. Right side bones are created mirrored.",
            group="Naming",
            pre_expose=True,
        )

        self.declare_option(
            name="Size",
            value=1.0,
            description="Scales the default proportions used by Create Bones",
            group="Creation",
        )

        self.declare_option(
            name="Control Size",
            value=1.0,
            description="Scales every control's shape. Shapes stored by Control Visuals take precedence.",
            group="Visuals",
        )

        # -- The outputs declared by set_output during the last build
        self._dynamic_outputs = []

    # ----------------------------------------------------------------------------------
    def option_widget(self, option_name: str):
        if option_name == "Location":
            return aniseed.widgets.LocationSelector(self.config, value=self.option("Location").get())
        return None

    def input_widget(self, requirement_name: str):
        if requirement_name in ("Parent", "Deform Armature"):
            return aniseed.widgets.ObjectSelector(component=self)
        return None

    # ----------------------------------------------------------------------------------
    def on_enter_stack(self):
        """
        Hooks the Parent to the parent component's outputs and creates the
        bones, unless the bone inputs already have values (such as when the
        bones already exist, or the component is being mirrored).
        """
        super().on_enter_stack()

        if not self.input("Parent").get(resolved=False):
            self.input("Parent").hook_to_parent(tags=self.parent_tags)

        if not self.has_bone_values():
            self.create_bones()

    def suggested_label(self):
        label = self.identifier.split(":")[-1].strip()
        location = self.option("Location").get()

        if location and location != self.config.middle:
            label = f"{label} {location}"

        return label

    # ----------------------------------------------------------------------------------
    def attach_bone(self, tag: str) -> str:
        """
        Returns the DEF bone a child component with the given attach tag
        creates its bones beneath, when no DEF bone is selected. By default
        this is the component's last bone.
        """
        bones = self.bones()
        return bones[-1] if bones else ""

    def fallback_parent_bone(self) -> str:
        """
        The DEF bone Create Bones parents the new bones to when no DEF bone is
        selected: the matching bone of the parent component, if it has one.
        """
        if hasattr(self.parent, "attach_bone"):
            return self.parent.attach_bone(self.attach_tag) or ""
        return ""

    def deform_armature(self):
        """
        Returns the deform armature object, or None.
        """
        name = self.input("Deform Armature").get()
        return bpy.data.objects.get(name) if name else armature_lib.find_role(self.rig.label, armature_lib.DEFORM)

    def control_armature(self):
        """
        Returns the control armature object, or None if the rig is editable.
        """
        return armature_lib.find_role(self.rig.label, armature_lib.CONTROL)

    def is_valid(self) -> bool:
        deform = self.deform_armature()
        if deform is None or deform.type != "ARMATURE":
            log.warning(f"{self.label()} : the deform armature could not be found")
            return False

        missing = [bone for bone in self.bones() if bone not in deform.data.bones]
        if missing:
            log.warning(f"{self.label()} : these bones do not exist (use Create Bones): {', '.join(missing)}")
            return False

        if not self.bones():
            log.warning(f"{self.label()} : has no bones (use Create Bones)")
            return False

        return True

    # ----------------------------------------------------------------------------------
    def set_output(self, name: str, value, description: str = "") -> None:
        """
        Sets an output, declaring it first if the component does not have it.
        Use it for outputs whose number varies (one per spine control, say).
        Outputs declared this way are removed at the start of the next build,
        so a build with fewer bones leaves none behind.
        """
        if self.output(name) is None:
            self.declare_output(name=name, description=description)
            self._dynamic_outputs.append(name)

        self.output(name).set(value)

    def clear_dynamic_outputs(self) -> None:
        """
        Removes the outputs set_output declared during the last build.
        """
        for name in self._dynamic_outputs:
            if self.output(name) is not None:
                self.remove_output(name)
        self._dynamic_outputs = []

    def control_parent(self) -> str:
        """
        Returns the control armature bone given by the Parent input, or an
        empty string (no parent) if it is not set or is not a bone in the
        control armature.
        """
        parent = self.input("Parent").get()
        if not parent:
            return ""

        control = self.control_armature()
        if not isinstance(parent, str) or control is None or parent not in control.data.bones:
            log.warning(f"{self.label()} : the Parent ({parent}) is not a control armature bone, so the controls are unparented")
            return ""

        return parent

    def guides_parent(self):
        """
        Returns the rig's guides group (the ORG Empty described "Guides"),
        falling back to the rig object.
        """
        root = armature_lib.rig_object(self.rig.label)
        for obj in root.children:
            try:
                if obj.type == "EMPTY" and self.config.extract_description(obj.name) == "Guides":
                    return obj
            except ValueError:
                continue
        return root


# --------------------------------------------------------------------------------------
class Builder:
    """
    Creates a component's bones in the control armature during its build.
    Making one starts the build, so it also removes the outputs the
    component's last build declared with set_output.

    Bones are created inside ``with builder.editing():``. Everything else
    (constraints, controls, properties) is done after leaving it.
    """

    def __init__(self, component: LimbComponent):
        self.component = component
        self.config = component.config
        self.location = component.option("Location").get()
        self.deform = component.deform_armature()
        self.control = component.control_armature()
        self.control_size = component.option("Control Size").get()
        self._edit_bones = None

        if self.control is None:
            raise RuntimeError("There is no control armature. Is Create Control Armature above this component?")

        component.clear_dynamic_outputs()

    # ----------------------------------------------------------------------------------
    # -- Naming and rest data
    def name(self, classification: str, description: str) -> str:
        return self.config.generate_name(classification, description, self.location)

    def describe(self, deform_bone: str, suffix: str = "") -> str:
        """
        Returns the description of a DEF bone (UpperArm for DEF_UpperArm_01_L)
        with the suffix added, for naming the bones built from it.
        """
        try:
            description = self.config.extract_description(deform_bone)
        except ValueError:
            description = self.config.format_description(deform_bone)
        return description + suffix

    def rest(self, deform_bone: str) -> dict:
        return armature_lib.rest_data(self.deform, deform_bone)

    def side_color(self) -> str:
        for side, color in SIDE_COLORS.items():
            if self.location == getattr(self.config, side):
                return color
        return SIDE_COLORS["middle"]

    # ----------------------------------------------------------------------------------
    # -- Edit mode
    @contextlib.contextmanager
    def editing(self):
        with armature_lib.edit_bones(self.control) as edit_bones:
            self._edit_bones = edit_bones
            try:
                yield edit_bones
            finally:
                self._edit_bones = None

    def copy_bone(
            self,
            deform_bone: str,
            classification: str,
            suffix: str = "",
            parent: str = None,
            length: float = None,
            description: str = None,
    ) -> str:
        """
        Creates a control armature bone matching the DEF bone's rest position
        (optionally with another length). Returns its name.
        """
        data = self.rest(deform_bone)
        tail = data["head"] + data["y_axis"] * (length or data["length"])

        return armature_lib.new_bone(
            self._edit_bones,
            self.name(classification, description or self.describe(deform_bone, suffix)),
            data["head"],
            tail,
            z_axis=data["z_axis"],
            parent=parent or None,
        )

    def copy_chain(self, deform_bones: typing.List[str], classification: str, suffix: str, parent: str = None) -> typing.List[str]:
        """
        Copies a chain of DEF bones, each parented to the previous one (and
        connected where the DEF bones are).
        """
        names = []
        for deform_bone in deform_bones:
            name = self.copy_bone(deform_bone, classification, suffix, parent=names[-1] if names else parent)
            if names and self.deform.data.bones[deform_bone].use_connect:
                self._edit_bones[name].use_connect = True
            names.append(name)
        return names

    def new_bone(self, classification, description, head, tail, z_axis=None, parent=None) -> str:
        return armature_lib.new_bone(
            self._edit_bones,
            self.name(classification, description),
            Vector(head),
            Vector(tail),
            z_axis=z_axis,
            parent=parent or None,
        )

    # ----------------------------------------------------------------------------------
    # -- After edit mode
    def pose_bone(self, name: str):
        return self.control.pose.bones[name]

    def make_control(
            self,
            bone: str,
            shape: str,
            size: float = 1.0,
            color: str = None,
            collection: str = CONTROLS,
            rotation=None,
            translation=None,
    ) -> str:
        """
        Makes the bone a control: gives it a shape, colour and collection.
        """
        pose_bone = self.pose_bone(bone)

        apply_visual(
            self.control,
            self.component.rig.label,
            self.config,
            bone,
            dict(shape=shape, size=[size * self.control_size] * 3, color=color or self.side_color()),
        )

        if rotation is not None:
            pose_bone.custom_shape_rotation_euler = rotation
        if translation is not None:
            pose_bone.custom_shape_translation = translation

        rigging.assign_collection(self.control, bone, collection)
        return bone

    def make_mechanical(self, *bones: str) -> None:
        for bone in bones:
            rigging.assign_collection(self.control, bone, MECHANICS)

    def copy_transforms(self, owner: str, target: str, name: str = "", influence: float = 1.0):
        return rigging.constrain(
            self.pose_bone(owner),
            "COPY_TRANSFORMS",
            name=name,
            target=self.control,
            subtarget=target,
            influence=influence,
        )

    def blend(self, owner: str, fk: str, ik: str, property_bone: str, property_name: str = "ik_fk") -> None:
        """
        Makes owner follow fk, or ik as the property goes from 0 to 1.
        """
        self.copy_transforms(owner, fk, name="Follow FK")
        constraint = self.copy_transforms(owner, ik, name="Follow IK")
        rigging.drive(constraint, "influence", self.control, property_bone, property_name)

    def pole_location(self, upper: str, lower: str, fallback) -> Vector:
        """
        Returns where to put the pole control of a two bone chain of DEF
        bones: out from the middle joint, as far as the upper bone is long.
        """
        upper_rest, lower_rest = self.rest(upper), self.rest(lower)
        return rigging.pole_location(upper_rest, lower_rest, upper_rest["length"], fallback)

    def two_bone_ik(self, lower: str, target: str, pole: str, upper_deform: str, lower_deform: str, pole_location):
        """
        Adds an IK constraint (chain length 2) to the lower bone of an IK
        chain, with the pole angle which keeps the chain at rest.
        """
        return rigging.constrain(
            self.pose_bone(lower),
            "IK",
            name="IK",
            target=self.control,
            subtarget=target,
            pole_target=self.control,
            pole_subtarget=pole,
            pole_angle=rigging.pole_angle(self.rest(upper_deform), self.rest(lower_deform), pole_location),
            chain_count=2,
        )

    def add_property(self, bone: str, name: str, default: float, minimum=None, maximum=None, description=""):
        rigging.add_property(self.pose_bone(bone), name, default, minimum, maximum, description)

    def bind(self, deform_bone: str, control_bone: str) -> None:
        """
        Marks the control armature bone as the one driving the DEF bone, so
        Link Deformation Rig constrains the DEF bone to it.
        """
        self.control.data.bones[control_bone][armature_lib.DRIVES_KEY] = deform_bone


# --------------------------------------------------------------------------------------
def apply_visual(control_armature, rig_label: str, config, bone: str, visual: dict) -> None:
    """
    Applies stored visual data (any of shape, size and color) to a control.

    Args:
        control_armature: The control armature object.
        rig_label: The rig the widgets belong to.
        config: The rig configuration, used to name widget objects.
        bone: The control bone.
        visual: {"shape": library name, "size": [x, y, z],
            "color": a theme name such as "THEME04", or
            {"normal": [r, g, b], "select": [r, g, b], "active": [r, g, b]}}
    """
    pose_bone = control_armature.pose.bones[bone]

    shape = visual.get("shape")
    if shape:
        try:
            pose_bone.custom_shape = widgets.widget(
                rig_label,
                shape,
                config.generate_name(config.widget, shape, config.middle),
            )
        except KeyError:
            log.warning(f"{bone} : there is no shape called {shape!r}")

    size = visual.get("size")
    if size is not None:
        pose_bone.custom_shape_scale_xyz = size if isinstance(size, (list, tuple)) else [size] * 3

    color = visual.get("color")
    if isinstance(color, str):
        pose_bone.color.palette = color

    elif isinstance(color, dict):
        pose_bone.color.palette = "CUSTOM"
        pose_bone.color.custom.normal = color.get("normal", (0, 0, 0))
        pose_bone.color.custom.select = color.get("select", (1, 1, 1))
        pose_bone.color.custom.active = color.get("active", (1, 1, 1))


def read_visual(control_armature, bone: str) -> dict:
    """
    Returns the visual data of a control, as apply_visual takes it.
    """
    pose_bone = control_armature.pose.bones[bone]
    palette = pose_bone.color.palette

    if palette == "CUSTOM":
        color = dict(
            normal=list(pose_bone.color.custom.normal),
            select=list(pose_bone.color.custom.select),
            active=list(pose_bone.color.custom.active),
        )
    else:
        color = palette

    return dict(
        shape=widgets.shape_of(pose_bone.custom_shape),
        size=[round(value, 5) for value in pose_bone.custom_shape_scale_xyz],
        color=color,
    )
