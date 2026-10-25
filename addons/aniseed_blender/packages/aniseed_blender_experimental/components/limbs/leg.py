"""
Provides "Experiment : Leg": a two bone leg with IK and FK blended by an
"ik_fk" property, a foot and a toe, and a reverse foot rolling around four
pivots. Mirrorable.

The pivots (heel, toe tip, inner and outer bank) are Empties parented to the
DEF foot bone, so they follow the foot when it is moved. Move them to fit the
character's foot.
"""
import math

import bpy
from mathutils import Matrix, Vector

from aniseed_blender_experimental import base
from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import mirroring
from aniseed_blender_experimental.lib import rigging
from aniseed_blender_experimental.mixins import BoneSpec, MirrorMixin

UP = Vector((0, 0, 1))
FORWARD = Vector((0, -1, 0))

# -- The pivot inputs, and where each pivot goes relative to the ankle for a
# -- left leg of Size 1
PIVOTS = {
    "Heel Pivot": (0, 0.04, -0.08),
    "Toe Pivot": (0, -0.21, -0.08),
    "Inner Pivot": (-0.05, -0.11, -0.08),
    "Outer Pivot": (0.05, -0.11, -0.08),
}

# -- The foot roll properties on the IK foot control: (default, min, max)
ROLLS = {
    "heel_roll": (0.0, -90.0, 90.0),
    "ball_roll": (0.0, -90.0, 90.0),
    "toe_roll": (0.0, -90.0, 90.0),
    "bank": (0.0, -90.0, 90.0),
    "swivel": (0.0, -180.0, 180.0),
}


class Leg(base.LimbComponent, MirrorMixin):
    """
    Builds FK thigh, shin, foot and toe controls, an IK foot control with a
    pole, and a reverse foot. Roll the foot with the heel_roll, ball_roll,
    toe_roll, bank and swivel properties (in degrees) on the IK foot control.
    The ik_fk property on the settings control blends the leg between FK (0)
    and IK (1).
    """

    identifier = "Experiment : Leg"
    default_description = "Leg"
    default_location = "left"
    attach_tag = "hips"
    parent_tags = ["blended pelvis", "pelvis", "hip"]
    bone_input_names = ["Thigh", "Shin", "Foot", "Toe"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(name="Thigh", value="", description="The thigh DEF bone", group="Skeleton")
        self.declare_input(name="Shin", value="", description="The shin DEF bone", group="Skeleton")
        self.declare_input(name="Foot", value="", description="The foot DEF bone", group="Skeleton")
        self.declare_input(name="Toe", value="", description="The toe DEF bone", group="Skeleton")

        for pivot in PIVOTS:
            self.declare_input(name=pivot, value="", description=f"The Empty marking the {pivot.lower()}", group="Pivots")

        self.declare_option(
            name="Default IK FK",
            value=1.0,
            description="The starting value of the ik_fk property (0 is FK, 1 is IK)",
            group="Behaviour",
        )

        self.declare_output(name="Blended Thigh", description="The bone the thigh DEF bone follows")
        self.declare_output(name="Blended Shin", description="The bone the shin DEF bone follows")
        self.declare_output(name="Blended Foot", description="The bone the foot DEF bone follows", is_default=True)
        self.declare_output(name="Blended Toe", description="The bone the toe DEF bone follows")
        self.declare_output(name="FK Thigh", description="The FK thigh control")
        self.declare_output(name="FK Shin", description="The FK shin control")
        self.declare_output(name="FK Foot", description="The FK foot control")
        self.declare_output(name="FK Toe", description="The FK toe control")
        self.declare_output(name="IK Foot", description="The IK foot control, which holds the foot roll properties")
        self.declare_output(name="Pole", description="The IK pole (upvector) control")
        self.declare_output(name="Settings", description="The control holding the ik_fk property")

    def input_widget(self, requirement_name):
        if requirement_name in PIVOTS:
            import aniseed
            return aniseed.widgets.ObjectSelector(component=self)
        return super().input_widget(requirement_name)

    # ----------------------------------------------------------------------------------
    def bone_layout(self):
        return [
            BoneSpec("thigh", "Thigh", (), "Thigh", (0.1, 0, 0.95), (0.1, -0.03, 0.52), FORWARD),
            BoneSpec("shin", "Shin", (), "Shin", (0.1, -0.03, 0.52), (0.1, 0.02, 0.08), FORWARD, parent="thigh", connect=True),
            BoneSpec("foot", "Foot", (), "Foot", (0.1, 0.02, 0.08), (0.1, -0.1, 0.02), UP, parent="shin", connect=True),
            BoneSpec("toe", "Toe", (), "Toe", (0.1, -0.1, 0.02), (0.1, -0.18, 0.02), UP, parent="foot", connect=True),
        ]

    def layout_anchor(self):
        # -- The default pelvis's tail
        return Vector((0, 0, 1.1))

    def attach_bone(self, tag):
        return self.input("Foot").get()

    def create_extras(self, names):
        """
        Creates the pivot Empties around the new foot.
        """
        deform = self.deform_armature()
        ankle = deform.data.bones[names["foot"]].head_local
        size = self.option("Size").get()
        mirrored = self.option("Location").get() == self.config.right

        for pivot, offset in PIVOTS.items():
            offset = Vector(offset) * size
            if mirrored:
                offset = mirroring.mirror_point(offset)

            self.input(pivot).set(self._create_pivot(pivot, names["foot"], ankle + offset))

    def extra_objects(self):
        return [self.input(pivot).get() for pivot in PIVOTS]

    def is_valid(self):
        if not super().is_valid():
            return False

        for pivot in PIVOTS:
            if self.input(pivot).get() not in bpy.data.objects:
                return False

        return True

    # ----------------------------------------------------------------------------------
    def mirror_mixin_mirror_extras(self, mirrored_from, bone_map):
        """
        Gives the mirrored leg pivots of its own, reflected from the
        original's, unless the mirrored pivots already exist.
        """
        deform = self.deform_armature()
        foot = self.input("Foot").get()

        for pivot in PIVOTS:
            original = bpy.data.objects.get(mirrored_from.input(pivot).get())
            if original is None:
                continue

            counterpart = self.mirror_mixin_mirrored_name(original.name)
            if counterpart != original.name and counterpart in bpy.data.objects:
                self.input(pivot).set(counterpart)
                continue

            position = mirroring.mirror_point(armature_lib.world_to_armature(deform, original.matrix_world.translation))
            self.input(pivot).set(self._create_pivot(pivot, foot, position))

    def _create_pivot(self, pivot: str, foot: str, position) -> str:
        """
        Creates a pivot Empty at the position (in the deform armature's
        space), parented to the foot bone. Returns its name.
        """
        deform = self.deform_armature()

        obj = bpy.data.objects.new(
            self.config.generate_name(self.config.guide, pivot, self.option("Location").get()),
            None,
        )
        (deform.users_collection[0] if deform.users_collection else bpy.context.scene.collection).objects.link(obj)

        obj.empty_display_type = "SPHERE"
        obj.empty_display_size = 0.015 * self.option("Size").get()
        obj.show_in_front = True

        obj.parent = deform
        obj.parent_type = "BONE"
        obj.parent_bone = foot

        bpy.context.view_layer.update()
        obj.matrix_world = Matrix.Translation(deform.matrix_world @ Vector(position))

        return obj.name

    # ----------------------------------------------------------------------------------
    def run(self):
        builder = base.Builder(self)
        description = self.option("Description").get()

        leg = [self.input(name).get() for name in self.bone_input_names]
        thigh, shin, foot, toe = leg

        parent = self.control_parent()

        bpy.context.view_layer.update()
        to_control = builder.control.matrix_world.inverted()
        pivots = {pivot: to_control @ bpy.data.objects[self.input(pivot).get()].matrix_world.translation for pivot in PIVOTS}

        foot_rest = builder.rest(foot)
        forward = pivots["Toe Pivot"] - pivots["Heel Pivot"]
        forward.z = 0
        forward = forward.normalized() if forward.length > 1e-5 else FORWARD.copy()

        pivot_length = foot_rest["length"] * 0.3
        pole_location = builder.pole_location(thigh, shin, fallback=FORWARD)
        control_length = builder.rest(thigh)["length"] * 0.2

        def flat(classification, name, position, parent_bone, length=pivot_length):
            # -- A bone lying flat, pointing forward
            return builder.new_bone(classification, name, position, position + forward * length, UP, parent=parent_bone)

        with builder.editing():
            fk = builder.copy_chain(leg, "control", "Fk", parent=parent)
            ik = builder.copy_chain(leg, "mechanical", "Ik", parent=parent)
            blend = builder.copy_chain(leg, "mechanical", "Blend", parent=parent)

            # -- The reverse foot: each pivot rolls everything after it. The
            # -- IK foot control runs from the heel to the toe tip.
            foot_length = (pivots["Toe Pivot"] - pivots["Heel Pivot"]).length
            foot_ik = flat("control", f"{builder.describe(foot)} Ik", pivots["Heel Pivot"], parent, length=foot_length)

            heel = flat("mechanical", f"{description} Heel Roll", pivots["Heel Pivot"], foot_ik)
            outer = flat("mechanical", f"{description} Outer Bank", pivots["Outer Pivot"], heel)
            inner = flat("mechanical", f"{description} Inner Bank", pivots["Inner Pivot"], outer)
            tip = flat("mechanical", f"{description} Toe Roll", pivots["Toe Pivot"], inner)
            ball = flat("mechanical", f"{description} Ball Roll", foot_rest["tail"], tip)

            foot_target = builder.copy_bone(foot, "mechanical", "IkTarget", parent=ball)
            toe_target = builder.copy_bone(toe, "mechanical", "IkTarget", parent=tip)

            pole = builder.new_bone("control", f"{description} Pole", pole_location, pole_location + UP * control_length, parent=parent)

            settings_head = foot_rest["head"] + Vector((0, 0.1, 0.1)) * (foot_rest["length"] / 0.13)
            settings = builder.new_bone("control", f"{description} Settings", settings_head, settings_head + UP * control_length * 0.5, parent=blend[1])

        builder.two_bone_ik(ik[1], foot_target, pole, thigh, shin, pole_location)
        rigging.constrain(builder.pose_bone(ik[2]), "COPY_ROTATION", target=builder.control, subtarget=foot_target)
        rigging.constrain(builder.pose_bone(ik[3]), "COPY_ROTATION", target=builder.control, subtarget=toe_target)

        # -- Foot roll properties, in degrees, driving the pivots
        for name, (default, minimum, maximum) in ROLLS.items():
            builder.add_property(foot_ik, name, default, minimum, maximum, f"Foot {name.replace('_', ' ')}, in degrees")

        for bone in (heel, outer, inner, tip, ball):
            builder.pose_bone(bone).rotation_mode = "XYZ"

        # -- The pivots point forward with Z up, so X pitches the foot, Y
        # -- banks it and Z swivels it. Banking lifts the side away from the
        # -- pivot, whose direction depends on the side.
        lateral = forward.cross(UP)
        side = 1.0 if (pivots["Inner Pivot"] - pivots["Outer Pivot"]).dot(lateral) > 0 else -1.0

        drive = builder.control
        rigging.drive(builder.pose_bone(heel), "rotation_euler", drive, foot_ik, "heel_roll", "radians(var)", index=0)
        rigging.drive(builder.pose_bone(heel), "rotation_euler", drive, foot_ik, "swivel", "radians(var)", index=2)
        rigging.drive(builder.pose_bone(ball), "rotation_euler", drive, foot_ik, "ball_roll", "radians(-var)", index=0)
        rigging.drive(builder.pose_bone(tip), "rotation_euler", drive, foot_ik, "toe_roll", "radians(-var)", index=0)
        rigging.drive(builder.pose_bone(outer), "rotation_euler", drive, foot_ik, "bank", f"radians({-side} * max(var, 0))", index=1)
        rigging.drive(builder.pose_bone(inner), "rotation_euler", drive, foot_ik, "bank", f"radians({-side} * min(var, 0))", index=1)

        builder.add_property(settings, "ik_fk", float(self.option("Default IK FK").get()), 0.0, 1.0, "0 is FK, 1 is IK")
        for blend_bone, fk_bone, ik_bone in zip(blend, fk, ik):
            builder.blend(blend_bone, fk_bone, ik_bone, settings)

        # -- Visuals and collections
        for bone, size in zip(fk, (0.6, 0.5, 1.2, 1.6)):
            builder.make_control(bone, "core_circle", size=size, collection=base.FK)

        # -- The paddle is drawn upright (around the bone), so it is turned to
        # -- lie on the ground, and moved forward to sit under the foot
        builder.make_control(
            foot_ik, "core_foot_paddle", size=0.5, collection=base.IK,
            rotation=(math.radians(90), 0, 0), translation=(0, foot_length * 0.5, 0),
        )
        builder.make_control(pole, "core_sphere", size=1.0, collection=base.IK)
        builder.make_control(settings, "core_config", size=1.5, color=base.SECONDARY_COLOR, collection=base.PROPERTIES)
        builder.make_mechanical(*ik, *blend, heel, outer, inner, tip, ball, foot_target, toe_target)

        for deform_bone, blend_bone in zip(leg, blend):
            builder.bind(deform_bone, blend_bone)

        for output_name, bone in zip(("Blended Thigh", "Blended Shin", "Blended Foot", "Blended Toe"), blend):
            self.output(output_name).set(bone)
        for output_name, bone in zip(("FK Thigh", "FK Shin", "FK Foot", "FK Toe"), fk):
            self.output(output_name).set(bone)
        self.output("IK Foot").set(foot_ik)
        self.output("Pole").set(pole)
        self.output("Settings").set(settings)
        return True
