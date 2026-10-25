"""
Provides "Experiment : IKFK Spine": a pelvis and a chain of spine bones,
driven by an FK chain or by Blender's Spline IK, blended by an "ik_fk"
property.

The Spline IK curve comes from the component's guide. Right click > Create
Guide shows the curve so it can be shaped, and Remove Guide stores it on the
component. The build rebuilds the stored curve in the control rig and hooks
its points to the hips, mid and chest IK controls.
"""
import logging

import bpy
from mathutils import Vector

from aniseed_blender_experimental import base
from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import curves
from aniseed_blender_experimental.lib import rigging
from aniseed_blender_experimental.mixins import BoneSpec, GuideMixin

log = logging.getLogger(__name__)

UP = Vector((0, 0, 1))
FORWARD = Vector((0, -1, 0))


class IKFKSpine(base.LimbComponent, GuideMixin):
    """
    Builds a torso control, FK controls for the pelvis and each spine bone,
    and hips, mid and chest IK controls which shape a Spline IK curve. The
    ik_fk property on the settings control blends between them (1 is IK).
    """

    identifier = "Experiment : IKFK Spine"
    default_description = "Spine"
    bone_input_names = ["Pelvis", "Spine"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(name="Pelvis", value="", description="The pelvis DEF bone", group="Skeleton")
        self.declare_input(name="Spine", value=[], description="The spine DEF bones, from the bottom up. The last is the chest.", group="Skeleton")

        self.declare_option(
            name="Spine Bones",
            value=3,
            description="How many spine bones Create Bones makes",
            group="Creation",
            pre_expose=True,
        )

        self.declare_option(
            name="Stretch",
            value=False,
            description="If on, the spine stretches to fill the curve. If off, the bones keep their length.",
            group="Behaviour",
        )

        self.declare_option(
            name="Default IK FK",
            value=1.0,
            description="The starting value of the ik_fk property (0 is FK, 1 is IK)",
            group="Behaviour",
        )

        self.declare_option(
            name=self.guide_option,
            value=dict(),
            hidden=True,
            description="The Spline IK curve, stored by Remove Guide, in the deform armature's space",
        )

        # -- Everything else has an output of its own. The FK spine controls ("Spine FK 01" upwards) and the blended
        # -- spine bones ("Blended Spine 01" upwards) are declared by the
        # -- build, as there is one per spine bone
        self.declare_output(name="Torso", description="The torso (centre of gravity) control")
        self.declare_output(name="Blended Pelvis", description="The bone the pelvis DEF bone follows")
        self.declare_output(name="Blended Chest", description="The bone the chest (last spine) DEF bone follows", is_default=True)
        self.declare_output(name="Pelvis FK", description="The FK pelvis control")
        self.declare_output(name="Hips IK", description="The hips IK control")
        self.declare_output(name="Mid IK", description="The mid IK control")
        self.declare_output(name="Chest IK", description="The chest IK control")
        self.declare_output(name="Settings", description="The control holding the ik_fk property")

    def option_widget(self, option_name):
        if option_name == "Spine Bones":
            import aniseed
            return aniseed.widgets.LimitedInteger(minimum=2, maximum=12)
        return super().option_widget(option_name)

    # ----------------------------------------------------------------------------------
    def bone_layout(self):
        count = max(2, self.option("Spine Bones").get())
        bottom, top = 1.1, 1.5
        step = (top - bottom) / count

        specs = [BoneSpec("pelvis", "Pelvis", (), "Pelvis", (0, 0, 1.0), (0, 0, bottom), z_axis=FORWARD)]

        for index in range(count):
            specs.append(BoneSpec(
                f"spine{index}", "Spine", (index,), "Chest" if index == count - 1 else "Spine",
                head=(0, 0, bottom + step * index),
                tail=(0, 0, bottom + step * (index + 1)),
                z_axis=FORWARD,
                parent="pelvis" if index == 0 else f"spine{index - 1}",
                connect=True,
            ))

        return specs

    def attach_bone(self, tag):
        if tag == "hips":
            return self.input("Pelvis").get()
        spine = self.input("Spine").get()
        return spine[-1] if spine else ""

    # ----------------------------------------------------------------------------------
    def default_guide_data(self) -> dict:
        """
        A curve through the spine bones, in the deform armature's space.
        """
        deform = self.deform_armature()
        spine = [bone for bone in self.input("Spine").get() if deform and bone in deform.data.bones]

        if not spine:
            return {}

        points = [deform.data.bones[bone].head_local for bone in spine]
        points.append(deform.data.bones[spine[-1]].tail_local)
        return curves.through(points, spline_type="POLY")

    # ----------------------------------------------------------------------------------
    def run(self):
        builder = base.Builder(self)
        description = self.option("Description").get()

        pelvis = self.input("Pelvis").get()
        spine = self.input("Spine").get()

        pelvis_rest = builder.rest(pelvis)
        start = builder.rest(spine[0])["head"]
        end = builder.rest(spine[-1])["tail"]
        length = (end - start).length
        control_length = length * 0.25

        with builder.editing():
            torso = builder.new_bone("control", f"{description} Torso", pelvis_rest["head"], pelvis_rest["head"] + UP * control_length, FORWARD, parent=self.control_parent())

            # -- FK
            pelvis_fk = builder.copy_bone(pelvis, "control", "Fk", parent=torso)
            spine_fk = builder.copy_chain(spine, "control", "Fk", parent=torso)

            # -- IK controls, upright so their shapes lie flat
            hips_ik = builder.new_bone("control", f"{description} Hips Ik", start, start + UP * control_length, FORWARD, parent=torso)
            middle = _point_along(builder, spine, 0.5)
            mid_ik = builder.new_bone("control", f"{description} Mid Ik", middle, middle + UP * control_length, FORWARD, parent=torso)
            chest_ik = builder.new_bone("control", f"{description} Chest Ik", end, end + UP * control_length, FORWARD, parent=torso)

            pelvis_ik = builder.copy_bone(pelvis, "mechanical", "Ik", parent=hips_ik)
            spine_ik = builder.copy_chain(spine, "mechanical", "Ik", parent=hips_ik)

            # -- What the deform bones follow
            pelvis_blend = builder.copy_bone(pelvis, "mechanical", "Blend", parent=torso)
            spine_blend = builder.copy_chain(spine, "mechanical", "Blend", parent=torso)

            side = Vector((length * 0.6, 0, 0))
            settings = builder.new_bone("control", f"{description} Settings", end + side, end + side + UP * control_length * 0.5, FORWARD, parent=torso)

        # -- The Spline IK curve, rebuilt from the guide data and hooked to the
        # -- IK controls
        curve = self._create_curve(builder, [(0.0, hips_ik), (0.5, mid_ik), (1.0, chest_ik)])

        rigging.constrain(
            builder.pose_bone(spine_ik[-1]),
            "SPLINE_IK",
            target=curve,
            chain_count=len(spine_ik),
            use_curve_radius=False,
            y_scale_mode="FIT_CURVE" if self.option("Stretch").get() else "BONE_ORIGINAL",
            xz_scale_mode="NONE",
        )

        builder.add_property(settings, "ik_fk", float(self.option("Default IK FK").get()), 0.0, 1.0, "0 is FK, 1 is IK")

        builder.blend(pelvis_blend, pelvis_fk, pelvis_ik, settings)
        for blend, fk, ik in zip(spine_blend, spine_fk, spine_ik):
            builder.blend(blend, fk, ik, settings)

        # -- Visuals and collections
        builder.make_control(torso, "core_rounded_square", size=5.0)
        builder.make_control(pelvis_fk, "core_half_circle", size=3.0, collection=base.FK)
        for bone in spine_fk:
            builder.make_control(bone, "core_circle", size=2.5, collection=base.FK)
        for bone in (hips_ik, mid_ik, chest_ik):
            builder.make_control(bone, "core_cube", size=1.6, collection=base.IK)
        builder.make_control(settings, "core_config", size=1.5, color=base.SECONDARY_COLOR, collection=base.PROPERTIES)
        builder.make_mechanical(pelvis_ik, pelvis_blend, *spine_ik, *spine_blend)

        builder.bind(pelvis, pelvis_blend)
        for deform_bone, blend in zip(spine, spine_blend):
            builder.bind(deform_bone, blend)

        self.output("Torso").set(torso)
        self.output("Blended Pelvis").set(pelvis_blend)
        self.output("Blended Chest").set(spine_blend[-1])
        self.output("Pelvis FK").set(pelvis_fk)
        for index, (fk, blend) in enumerate(zip(spine_fk, spine_blend)):
            self.set_output(f"Spine FK {index + 1:02d}", fk, "An FK spine control, counting from the bottom")
            self.set_output(f"Blended Spine {index + 1:02d}", blend, "The bone a spine DEF bone follows, counting from the bottom")
        self.output("Hips IK").set(hips_ik)
        self.output("Mid IK").set(mid_ik)
        self.output("Chest IK").set(chest_ik)
        self.output("Settings").set(settings)
        return True

    def _create_curve(self, builder, hooks):
        """
        Creates the Spline IK curve from the guide data, parented to the
        control armature, and hooks each of its points to the nearest of the
        given (position along the curve, control) pairs.
        """
        data = self.guide_data()
        control = builder.control

        curve = curves.create(
            builder.name("mechanical", f"{self.option('Description').get()} Curve"),
            data,
            space_object=builder.deform,
            parent=control,
        )
        curve[armature_lib.ROLE_KEY] = armature_lib.CONTROL_CURVE

        point_count = len(data["points"])
        assignments = {bone: [] for _, bone in hooks}

        for index in range(point_count):
            position = index / max(1, point_count - 1)
            nearest = min(hooks, key=lambda hook: abs(hook[0] - position))[1]
            assignments[nearest].append(index)

        bpy.context.view_layer.update()

        for bone, indices in assignments.items():
            if not indices:
                continue

            modifier = curve.modifiers.new(name=f"Hook {bone}", type="HOOK")
            modifier.object = control
            modifier.subtarget = bone
            modifier.vertex_indices_set(indices)

            # -- The inverse of where the bone is now, so the points stay put
            # -- until the control moves (the same as Blender's Hook > Reset)
            target = control.matrix_world @ control.data.bones[bone].matrix_local
            modifier.matrix_inverse = target.inverted() @ curve.matrix_world

        # -- Hidden in the view layer rather than in the viewport, as a curve
        # -- hidden in the viewport is not evaluated, and Spline IK needs it
        curve.hide_set(True)
        curve.hide_render = True
        return curve


def _point_along(builder, chain, fraction: float) -> Vector:
    """
    Returns the point the given fraction of the way along a chain of DEF
    bones.
    """
    rests = [builder.rest(bone) for bone in chain]
    total = sum(rest["length"] for rest in rests)
    remaining = total * fraction

    for rest in rests:
        if remaining <= rest["length"]:
            return rest["head"] + (rest["tail"] - rest["head"]).normalized() * remaining
        remaining -= rest["length"]

    return rests[-1]["tail"]
