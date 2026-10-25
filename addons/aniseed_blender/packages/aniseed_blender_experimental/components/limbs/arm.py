"""
Provides "Experiment : Arm": a clavicle, a two bone arm with IK and FK blended
by an "ik_fk" property, a hand, and FK fingers. Mirrorable.
"""
from mathutils import Vector

from aniseed_blender_experimental import base
from aniseed_blender_experimental.lib import rigging
from aniseed_blender_experimental.mixins import BoneSpec, MirrorMixin

UP = Vector((0, 0, 1))

# -- Default finger layouts for a left hand of Size 1: (start, direction,
# -- lengths of each bone)
FINGER_LAYOUT = {
    "Thumb": ((0.72, -0.03, 1.44), (1, -1, 0), (0.035, 0.03, 0.025)),
    "Index": ((0.79, -0.03, 1.45), (1, 0, 0), (0.04, 0.03, 0.025)),
    "Middle": ((0.79, -0.01, 1.45), (1, 0, 0), (0.045, 0.032, 0.025)),
    "Ring": ((0.79, 0.01, 1.45), (1, 0, 0), (0.04, 0.03, 0.025)),
    "Pinky": ((0.79, 0.03, 1.45), (1, 0, 0), (0.032, 0.025, 0.02)),
}


class Arm(base.LimbComponent, MirrorMixin):
    """
    Builds a clavicle control, FK upper arm, forearm and hand controls, an IK
    hand control with a pole, and FK finger controls. The ik_fk property on
    the settings control blends the arm between FK (0) and IK (1).
    """

    identifier = "Experiment : Arm"
    default_description = "Arm"
    default_location = "left"
    attach_tag = "chest"
    parent_tags = ["blended chest", "chest"]
    bone_input_names = ["Clavicle", "Upper Arm", "Forearm", "Hand", "Fingers"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(name="Clavicle", value="", description="The clavicle DEF bone", group="Skeleton")
        self.declare_input(name="Upper Arm", value="", description="The upper arm DEF bone", group="Skeleton")
        self.declare_input(name="Forearm", value="", description="The forearm DEF bone", group="Skeleton")
        self.declare_input(name="Hand", value="", description="The hand DEF bone", group="Skeleton")
        self.declare_input(
            name="Fingers",
            value=[],
            description="The finger DEF bones: a list per finger, each from the knuckle out",
            validate=False,
            group="Skeleton",
        )

        self.declare_option(
            name="Fingers To Create",
            value=list(FINGER_LAYOUT),
            description="Which fingers Create Bones makes",
            group="Creation",
        )

        self.declare_option(
            name="Default IK FK",
            value=0.0,
            description="The starting value of the ik_fk property (0 is FK, 1 is IK)",
            group="Behaviour",
        )

        self.declare_output(name="Clavicle", description="The clavicle control")
        self.declare_output(name="Blended Upper Arm", description="The bone the upper arm DEF bone follows")
        self.declare_output(name="Blended Forearm", description="The bone the forearm DEF bone follows")
        self.declare_output(name="Blended Hand", description="The bone the hand DEF bone follows", is_default=True)
        self.declare_output(name="FK Upper Arm", description="The FK upper arm control")
        self.declare_output(name="FK Forearm", description="The FK forearm control")
        self.declare_output(name="FK Hand", description="The FK hand control")
        self.declare_output(name="IK Hand", description="The IK hand control")
        self.declare_output(name="Pole", description="The IK pole (upvector) control")
        self.declare_output(name="Settings", description="The control holding the ik_fk property")
        # -- The finger controls ("Index 01" outwards) are declared by the
        # -- build, as the fingers vary

    def option_widget(self, option_name):
        if option_name == "Fingers To Create":
            import aniseed
            return aniseed.widgets.TextList()
        return super().option_widget(option_name)

    # ----------------------------------------------------------------------------------
    def bone_layout(self):
        specs = [
            BoneSpec("clavicle", "Clavicle", (), "Clavicle", (0.02, 0, 1.45), (0.17, 0, 1.45), UP),
            BoneSpec("upper", "Upper Arm", (), "Upper Arm", (0.17, 0, 1.45), (0.45, 0.03, 1.45), UP, parent="clavicle", connect=True),
            BoneSpec("forearm", "Forearm", (), "Forearm", (0.45, 0.03, 1.45), (0.70, 0, 1.45), UP, parent="upper", connect=True),
            BoneSpec("hand", "Hand", (), "Hand", (0.70, 0, 1.45), (0.78, 0, 1.45), UP, parent="forearm", connect=True),
        ]

        for finger_index, finger in enumerate(name for name in self.option("Fingers To Create").get() if name in FINGER_LAYOUT):
            start, direction, lengths = FINGER_LAYOUT[finger]
            head = Vector(start)
            direction = Vector(direction).normalized()

            for bone_index, length in enumerate(lengths):
                tail = head + direction * length
                specs.append(BoneSpec(
                    f"{finger}{bone_index}", "Fingers", (finger_index, bone_index), finger,
                    head, tail, UP,
                    parent=f"{finger}{bone_index - 1}" if bone_index else "hand",
                    connect=bool(bone_index),
                ))
                head = tail

        return specs

    def layout_anchor(self):
        # -- The default chest's tail
        return Vector((0, 0, 1.5))

    def attach_bone(self, tag):
        return self.input("Hand").get()

    # ----------------------------------------------------------------------------------
    def run(self):
        builder = base.Builder(self)
        description = self.option("Description").get()

        clavicle = self.input("Clavicle").get()
        arm = [self.input("Upper Arm").get(), self.input("Forearm").get(), self.input("Hand").get()]
        fingers = [finger for finger in self.input("Fingers").get() or [] if finger]

        parent = self.control_parent()

        hand_rest = builder.rest(arm[2])
        pole_location = builder.pole_location(arm[0], arm[1], fallback=(0, 1, 0))
        control_length = builder.rest(arm[0])["length"] * 0.25

        with builder.editing():
            clavicle_control = builder.copy_bone(clavicle, "control", parent=parent)

            fk = builder.copy_chain(arm, "control", "Fk", parent=clavicle_control)
            ik = builder.copy_chain(arm, "mechanical", "Ik", parent=clavicle_control)
            blend = builder.copy_chain(arm, "mechanical", "Blend", parent=clavicle_control)

            hand_ik = builder.copy_bone(arm[2], "control", "Ik", parent=parent)
            pole = builder.new_bone("control", f"{description} Pole", pole_location, pole_location + UP * control_length, parent=parent)

            settings_head = hand_rest["head"] + UP * control_length * 2
            settings = builder.new_bone("control", f"{description} Settings", settings_head, settings_head + UP * control_length, parent=blend[-1])

            finger_controls = [builder.copy_chain(finger, "control", "", parent=blend[-1]) for finger in fingers]

        builder.two_bone_ik(ik[1], hand_ik, pole, arm[0], arm[1], pole_location)

        # -- The IK hand bone sits on the end of the chain, turned by the IK
        # -- hand control
        rigging.constrain(builder.pose_bone(ik[2]), "COPY_ROTATION", target=builder.control, subtarget=hand_ik)

        builder.add_property(settings, "ik_fk", float(self.option("Default IK FK").get()), 0.0, 1.0, "0 is FK, 1 is IK")
        for blend_bone, fk_bone, ik_bone in zip(blend, fk, ik):
            builder.blend(blend_bone, fk_bone, ik_bone, settings)

        # -- Visuals and collections
        builder.make_control(clavicle_control, "core_pinched_circle", size=2.0)
        for bone, size in zip(fk, (0.8, 0.8, 1.6)):
            builder.make_control(bone, "core_circle", size=size, collection=base.FK)
        builder.make_control(hand_ik, "core_cube", size=1.0, collection=base.IK)
        builder.make_control(pole, "core_sphere", size=1.0, collection=base.IK)
        builder.make_control(settings, "core_config", size=1.5, color=base.SECONDARY_COLOR, collection=base.PROPERTIES)
        for chain in finger_controls:
            for bone in chain:
                builder.make_control(bone, "core_circle", size=1.2, color=base.SECONDARY_COLOR, collection=base.FINGERS)
        builder.make_mechanical(*ik, *blend)

        builder.bind(clavicle, clavicle_control)
        for deform_bone, blend_bone in zip(arm, blend):
            builder.bind(deform_bone, blend_bone)
        for finger, chain in zip(fingers, finger_controls):
            for deform_bone, control_bone in zip(finger, chain):
                builder.bind(deform_bone, control_bone)

        self.output("Clavicle").set(clavicle_control)
        for output_name, bone in zip(("Blended Upper Arm", "Blended Forearm", "Blended Hand"), blend):
            self.output(output_name).set(bone)
        for output_name, bone in zip(("FK Upper Arm", "FK Forearm", "FK Hand"), fk):
            self.output(output_name).set(bone)
        self.output("IK Hand").set(hand_ik)
        self.output("Pole").set(pole)
        self.output("Settings").set(settings)
        for finger, chain in zip(fingers, finger_controls):
            name = builder.describe(finger[0])
            for index, bone in enumerate(chain):
                self.set_output(f"{name} {index + 1:02d}", bone, f"A {name.lower()} control, counting from the knuckle")
        return True
