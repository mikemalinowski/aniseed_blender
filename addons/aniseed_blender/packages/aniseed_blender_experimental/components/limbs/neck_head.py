"""
Provides "Experiment : Neck And Head": neck bones and a head, each driven by
an FK control.
"""
from mathutils import Vector

from aniseed_blender_experimental import base
from aniseed_blender_experimental.mixins import BoneSpec

FORWARD = Vector((0, -1, 0))


class NeckAndHead(base.LimbComponent):
    """
    Builds an FK control for each neck bone and one for the head.
    """

    identifier = "Experiment : Neck And Head"
    default_description = "Neck"
    attach_tag = "chest"
    parent_tags = ["blended chest", "chest"]
    bone_input_names = ["Neck", "Head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(name="Neck", value=[], description="The neck DEF bones, from the bottom up", group="Skeleton")
        self.declare_input(name="Head", value="", description="The head DEF bone", group="Skeleton")

        self.declare_option(
            name="Neck Bones",
            value=1,
            description="How many neck bones Create Bones makes",
            group="Creation",
            pre_expose=True,
        )

        # -- The neck controls ("Neck 01" upwards) are declared by the build,
        # -- as there is one per neck bone
        self.declare_output(name="Head", description="The head control", is_default=True)

    def option_widget(self, option_name):
        if option_name == "Neck Bones":
            import aniseed
            return aniseed.widgets.LimitedInteger(minimum=1, maximum=8)
        return super().option_widget(option_name)

    def bone_layout(self):
        count = max(1, self.option("Neck Bones").get())
        bottom, top = 1.5, 1.62
        step = (top - bottom) / count

        specs = []
        for index in range(count):
            specs.append(BoneSpec(
                f"neck{index}", "Neck", (index,), "Neck",
                head=(0, 0, bottom + step * index),
                tail=(0, 0, bottom + step * (index + 1)),
                z_axis=FORWARD,
                parent=f"neck{index - 1}" if index else None,
                connect=bool(index),
            ))

        specs.append(BoneSpec("head", "Head", (), "Head", (0, 0, top), (0, 0, 1.82), z_axis=FORWARD, parent=f"neck{count - 1}", connect=True))
        return specs

    def layout_anchor(self):
        # -- The default chest's tail
        return Vector((0, 0, 1.5))

    def attach_bone(self, tag):
        return self.input("Head").get()

    def run(self):
        builder = base.Builder(self)

        neck = self.input("Neck").get()
        head = self.input("Head").get()

        with builder.editing():
            chain = builder.copy_chain(neck + [head], "control", "", parent=self.control_parent())

        for bone in chain[:-1]:
            builder.make_control(bone, "circle", size=2.5, collection=base.FK)
        builder.make_control(chain[-1], "circle", size=1.5, collection=base.FK, translation=(0, builder.rest(head)["length"] * 0.5, 0))

        for deform_bone, control_bone in zip(neck + [head], chain):
            builder.bind(deform_bone, control_bone)

        for index, bone in enumerate(chain[:-1]):
            self.set_output(f"Neck {index + 1:02d}", bone, "A neck control, counting from the bottom")
        self.output("Head").set(chain[-1])
        return True
