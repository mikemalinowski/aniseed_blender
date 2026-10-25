"""
Builds a full biped with the experiment components in a new, empty file and
checks the result. Run it in background Blender with aniseed initialised (see
recipes/generate_biped.py for how the add-on is started), for example:

    blender -b --factory-startup --python <this file>

It checks that:
    * adding the components creates their bones, and mirroring creates
      mirrored bones
    * the rig builds, and at rest every deform bone stays exactly where it is
    * the controls move the deform bones (FK, IK, spine IK, foot roll)
    * the spine guide can be created and stored
    * snapshotted control visuals survive Make Rig Editable and a rebuild
    * the recipe can be saved and loaded into an empty scene, recreating the
      skeleton, and that rig builds the same way

Prints a line per check and exits with 1 if any failed.
"""
import os
import sys
import math
import tempfile
import traceback

import bpy
from mathutils import Vector

import aniseed

RESULTS = []


def check(name: str, condition: bool, detail: str = ""):
    RESULTS.append(condition)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{' : ' + detail if detail else ''}")
    return condition


def update():
    bpy.context.view_layer.update()


def set_property(armature, bone: str, name: str, value):
    """
    Sets a custom property on a pose bone and re-evaluates the rig. Setting a
    custom property from Python does not tell Blender anything changed (the
    UI does), so the drivers using it would not update without the tag.
    """
    armature.pose.bones[bone][name] = value
    armature.update_tag()
    update()


def deform_armature(rig):
    return next(obj for obj in bpy.data.objects[rig.label].children_recursive if obj.get("aniseed_role") == "deform")


def control_armature(rig):
    return next((obj for obj in bpy.data.objects[rig.label].children_recursive if obj.get("aniseed_role") == "control"), None)


def world_head(armature, bone):
    return armature.matrix_world @ armature.pose.bones[bone].head


def rest_drift(armature) -> float:
    """
    Returns the largest difference between any pose bone's matrix and its
    rest matrix.
    """
    update()
    drift = 0.0
    for pose_bone in armature.pose.bones:
        difference = pose_bone.matrix - pose_bone.bone.matrix_local
        drift = max(drift, max(abs(value) for row in difference for value in row))
    return drift


def build(rig) -> bool:
    result = rig.build(build_below=rig.get_component_by_label("Build Rig"))
    failed = [component.label() for component in rig.components() if component.status() == "failed"]
    return check("Build Rig succeeds", bool(result) and not failed, f"failed: {failed}" if failed else "")


def make_editable(rig):
    return rig.build(build_below=rig.get_component_by_label("Make Rig Editable"))


def clear_selection():
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = None


def select_bone(armature, bone: str):
    """
    Selects the armature and makes the bone its selected, active bone, as a
    user clicking it in pose mode would.
    """
    clear_selection()
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    armature.data.bones.active = armature.data.bones[bone]

    # -- Blender 5 moved bone selection outside edit mode to the pose bone
    pose_bone = armature.pose.bones[bone]
    (pose_bone if hasattr(pose_bone, "select") else armature.data.bones[bone]).select = True


def create_biped():
    bpy.ops.wm.read_homefile(use_empty=True)

    rig = aniseed.Rig(label="ExperimentRig", configuration="Rig Configuration : Experiment")
    components = rig.get_component_by_label("Components")

    # -- New bones go beneath the selected DEF bone, so start with nothing
    # -- selected, so each component falls back to its parent component
    clear_selection()

    root = rig.add_component("Experiment : Root", "Root", parent=components)
    spine = rig.add_component("Experiment : IKFK Spine", "Spine", parent=root)
    neck = rig.add_component("Experiment : Neck And Head", "Neck", parent=spine)
    arm = rig.add_component("Experiment : Arm", "Arm L", parent=spine)
    leg = rig.add_component("Experiment : Leg", "Leg L", parent=spine)

    # -- A prop held in the hand, mirrored with the arm
    rig.add_component(
        "Experiment : Singular",
        "Prop L",
        options={"Description": "Prop", "Location": "L", "Shape": "core_sphere"},
        parent=arm,
    )

    # -- A hat: its bone is created beneath the selected head bone, while its
    # -- control is under the spine (the component it is added beneath), so
    # -- the control hierarchy differs from the deform one
    select_bone(deform_armature(rig), neck.input("Head").get())
    rig.add_component(
        "Experiment : Singular",
        "Hat",
        options={"Description": "Hat", "Shape": "core_teardrop"},
        parent=spine,
    )
    clear_selection()

    # -- A space switch on the IK hand, added with no settings: it hooks to the
    # -- arm's IK control and starts with Parent and World spaces. It is
    # -- beneath the arm, so mirroring the arm mirrors it too.
    rig.add_component("Experiment : Space Switch", "Hand Space L", parent=arm)

    # -- An orientation only switch on the head, between the neck and the world
    space_switch = rig.component_library.request("Experiment : Space Switch")
    space_switch.add_to(
        neck,
        "Head Space",
        driven="[Neck].[output].[Head]",
        default_space="Neck",
        spaces=[("Neck", "[Neck].[output].[Neck 01]"), ("World", "[Root].[output].[Offset Control]")],
    )
    head_space = rig.get_component_by_label("Head Space")
    head_space.set_orientation_only(True)

    arm.mirror()
    leg.mirror()

    # -- Give the spine a natural S curve, as a user fitting it to a character
    # -- would, so the Spline IK is tested on a chain which is not straight
    deform = deform_armature(rig)
    bpy.context.view_layer.objects.active = deform
    bpy.ops.object.mode_set(mode="EDIT")
    for bone, offset in zip(spine.input("Spine").get(), (-0.03, -0.01, 0.025)):
        deform.data.edit_bones[bone].tail.y += offset
    bpy.ops.object.mode_set(mode="OBJECT")

    return rig


def main():
    aniseed.packages.set_enabled("aniseed_blender_experimental", True, persist=False)

    # -- Creating bones
    rig = create_biped()
    deform = deform_armature(rig)

    labels = [component.label() for component in rig.components()]
    check("Mirroring adds Arm R and Leg R", "Arm R" in labels and "Leg R" in labels, str(labels))

    bone_count = len(deform.data.bones)
    # -- root, pelvis + 3 spine, neck + head, 2 x (4 arm + 15 fingers), 2 x 4 leg,
    # -- 2 props, hat
    check("Every component created its bones", bone_count == 1 + 4 + 2 + 38 + 8 + 2 + 1, f"{bone_count} bones")

    arm_l = rig.get_component_by_label("Arm L")
    arm_r = rig.get_component_by_label("Arm R")
    asymmetry = max(
        (deform.data.bones[left].head_local - _mirror(deform.data.bones[right].head_local)).length
        + (deform.data.bones[left].tail_local - _mirror(deform.data.bones[right].tail_local)).length
        for left, right in zip(arm_l.bones(), arm_r.bones())
    )
    check("Arm R bones mirror Arm L", asymmetry < 1e-5, f"largest difference {asymmetry:.6f}")

    rolls_mirrored = max(
        (deform.data.bones[left].matrix_local.col[2].xyz - _mirror(deform.data.bones[right].matrix_local.col[2].xyz)).length
        for left, right in zip(arm_l.bones(), arm_r.bones())
    )
    check("Arm R bone rolls mirror Arm L", rolls_mirrored < 1e-4, f"largest difference {rolls_mirrored:.6f}")

    check("Arm R bones are named _R", all(name.endswith("_R") for name in arm_r.bones()), str(arm_r.bones()[:4]))
    chest = rig.get_component_by_label("Spine").input("Spine").get()[-1]
    clavicle_parents = [deform.data.bones[arm.input("Clavicle").get()].parent for arm in (arm_l, arm_r)]
    check(
        "Both clavicles are created beneath the chest",
        all(parent is not None and parent.name == chest for parent in clavicle_parents),
        str([parent.name if parent else None for parent in clavicle_parents]),
    )

    hat = rig.get_component_by_label("Hat").input("Bone").get()
    head = rig.get_component_by_label("Neck").input("Head").get()
    hat_parent = deform.data.bones[hat].parent
    check(
        "Hat : its bone is created beneath the selected head bone",
        hat_parent is not None and hat_parent.name == head,
        f"{hat} is under {hat_parent.name if hat_parent else None}",
    )

    # -- Each component's Parent is hooked to its parent component's outputs
    expected_parents = {
        "Root": "",
        "Spine": "[Root].[output].[Offset Control]",
        "Neck": "[Spine].[output].[Blended Chest]",
        "Arm L": "[Spine].[output].[Blended Chest]",
        "Arm R": "[Spine].[output].[Blended Chest]",
        "Leg L": "[Spine].[output].[Blended Pelvis]",
        "Leg R": "[Spine].[output].[Blended Pelvis]",
        "Prop L": "[Arm L].[output].[Blended Hand]",
        "Prop R": "[Arm R].[output].[Blended Hand]",
        "Hat": "[Spine].[output].[Blended Chest]",
    }
    actual_parents = {label: rig.get_component_by_label(label).input("Parent").get(resolved=False) for label in expected_parents}
    check("Every Parent is hooked to the parent component's output", actual_parents == expected_parents, str(actual_parents))

    leg_r = rig.get_component_by_label("Leg R")
    check(
        "Leg R has its own pivots",
        all(leg_r.input(pivot).get().endswith("_R") and leg_r.input(pivot).get() in bpy.data.objects for pivot in ("Heel Pivot", "Toe Pivot", "Inner Pivot", "Outer Pivot")),
    )

    # -- Spine guide
    spine = rig.get_component_by_label("Spine")
    guide = spine.create_guide()
    check("Create Guide makes a curve", guide is not None and guide.type == "CURVE")
    spine.remove_guide()
    stored = spine.option("_Guide Curve").get()
    check("Remove Guide stores the curve", bool(stored.get("points")) and spine.guide_object() is None, f"{len(stored.get('points', []))} points")

    # -- Building
    if not build(rig):
        return

    control = control_armature(rig)
    check("The control armature exists", control is not None)

    drift = rest_drift(deform)
    check("At rest the deform bones do not move", drift < 1e-4, f"largest drift {drift:.6f}")

    linked = sum(1 for pose_bone in deform.pose.bones if any(c.name == "aniseed_link" for c in pose_bone.constraints))
    check("Every deform bone is linked", linked == bone_count, f"{linked} of {bone_count}")
    check(
        "The build leaves the control armature in pose mode",
        bpy.context.view_layer.objects.active == control and control.mode == "POSE",
        control.mode,
    )

    _check_arm(rig, deform, control, "Arm L")
    _check_arm(rig, deform, control, "Arm R")
    _check_leg(rig, deform, control, "Leg L")
    _check_leg(rig, deform, control, "Leg R")
    _check_spine(rig, deform, control)
    _check_outputs(rig, control)
    _check_singular(rig, deform, control, "Prop L", arm_l.input("Hand").get())
    _check_singular(rig, deform, control, "Prop R", arm_r.input("Hand").get())
    _check_singular(rig, deform, control, "Hat", head)
    _check_space_switches(rig, deform, control)

    drivers = control.animation_data.drivers if control.animation_data else []
    complex_drivers = [fcurve.data_path for fcurve in drivers if not fcurve.driver.is_simple_expression]
    check(
        "Every driver is a simple expression (works without Python auto-run)",
        drivers and not complex_drivers,
        f"{len(drivers)} drivers{', complex: ' + str(complex_drivers) if complex_drivers else ''}",
    )

    # -- Pointing the Parent at another output re-parents the controls
    output_names = {component.label(): [output.name() for output in component.outputs()] for component in rig.components()}
    parent_input = arm_l.input("Parent")
    parent_input.set("[Spine].[output].[Chest IK]")
    build(rig)
    control = control_armature(rig)
    chest_ik = spine.output("Chest IK").get()
    parents = {output_name: control.data.bones[arm_l.output(output_name).get()].parent for output_name in ("Clavicle", "Pole")}
    check(
        "Arm L : a new Parent re-parents its controls",
        all(parent is not None and parent.name == chest_ik for parent in parents.values()),
        str({name: parent.name if parent else None for name, parent in parents.items()}),
    )
    check("Arm L : at rest with the new Parent", rest_drift(deform) < 1e-4)
    parent_input.set("[Spine].[output].[Blended Chest]")
    build(rig)
    control = control_armature(rig)

    rebuilt_names = {component.label(): [output.name() for output in component.outputs()] for component in rig.components()}
    check("Rebuilding gives the same outputs (none duplicated)", rebuilt_names == output_names)

    # -- Visuals
    visuals = rig.get_component_by_label("Control Visuals")
    hand_ik = rig.get_component_by_label("Arm L").output("IK Hand").get()
    control.pose.bones[hand_ik].custom_shape_scale_xyz = (3, 3, 3)
    control.pose.bones[hand_ik].color.palette = "THEME06"
    stored_count = visuals.snapshot()
    check("Snapshot stores every control", stored_count > 50, f"{stored_count} controls")

    # -- Snapshot Selected only updates the selected control (selection moved
    # -- from the bone to the pose bone in Blender 5)
    selectable = control.pose.bones[hand_ik] if hasattr(control.pose.bones[hand_ik], "select") else control.data.bones[hand_ik]
    for pose_bone in control.pose.bones:
        (pose_bone if hasattr(pose_bone, "select") else pose_bone.bone).select = False
    selectable.select = True
    control.pose.bones[hand_ik].color.palette = "THEME07"
    selected_count = visuals.snapshot_selected()
    check(
        "Snapshot Selected stores only the selected control",
        selected_count == 1 and visuals.visuals()[hand_ik]["color"] == "THEME07",
        f"{selected_count} stored",
    )
    control.pose.bones[hand_ik].color.palette = "THEME06"
    visuals.snapshot_selected()

    make_editable(rig)
    check("Make Rig Editable removes the control armature", control_armature(rig) is None)
    check("Make Rig Editable unlinks", not any(pose_bone.constraints for pose_bone in deform.pose.bones))

    build(rig)
    control = control_armature(rig)
    scale = tuple(control.pose.bones[hand_ik].custom_shape_scale_xyz)
    palette = control.pose.bones[hand_ik].color.palette
    check("Snapshotted visuals survive a rebuild", scale == (3, 3, 3) and palette == "THEME06", f"{scale} {palette}")

    # -- Saving and loading into an empty scene
    path = os.path.join(tempfile.gettempdir(), "aniseed_experiment_biped.json")
    make_editable(rig)
    rig.save(path)

    bone_data = {bone.name: (bone.head_local.copy(), bone.tail_local.copy(), bone.matrix_local.col[2].xyz.copy()) for bone in deform.data.bones}
    pivots = {name: bpy.data.objects[name].matrix_world.translation.copy() for name in bpy.data.objects.keys() if name.startswith("GDE_")}

    bpy.ops.wm.read_homefile(use_empty=True)
    aniseed.Rig.clear_registry()

    loaded = aniseed.Rig(label="ExperimentRig")
    loaded.deserialize(path)

    deform = deform_armature(loaded)
    difference = max(
        (deform.data.bones[name].head_local - head).length
        + (deform.data.bones[name].tail_local - tail).length
        + (deform.data.bones[name].matrix_local.col[2].xyz - z_axis).length
        for name, (head, tail, z_axis) in bone_data.items()
    ) if all(name in deform.data.bones for name in bone_data) else float("inf")
    check("Loading the recipe recreates the skeleton", difference < 1e-4, f"{len(deform.data.bones)} bones, largest difference {difference:.6f}")

    update()
    pivot_difference = max(
        (bpy.data.objects[name].matrix_world.translation - position).length if name in bpy.data.objects else float("inf")
        for name, position in pivots.items()
    )
    check(
        "Loading the recipe recreates the pivots on the foot bones",
        pivot_difference < 1e-4 and all(bpy.data.objects[name].parent_type == "BONE" for name in pivots if name in bpy.data.objects),
        f"largest difference {pivot_difference:.6f}",
    )

    check("Loading the recipe creates no extra bones", len(deform.data.bones) == len(bone_data), f"{len(deform.data.bones)} bones")

    if build(loaded):
        check("The loaded rig is at rest after building", rest_drift(deform) < 1e-4)
        control = control_armature(loaded)
        scale = tuple(control.pose.bones[hand_ik].custom_shape_scale_xyz)
        check("The loaded rig keeps the snapshotted visuals", scale == (3, 3, 3), str(scale))


def _mirror(vector):
    return Vector((-vector.x, vector.y, vector.z))


def _check_arm(rig, deform, control, label):
    arm = rig.get_component_by_label(label)
    hand = arm.input("Hand").get()
    upper = arm.input("Upper Arm").get()
    settings = arm.output("Settings").get()
    hand_ik = arm.output("IK Hand").get()
    fk_upper = arm.output("FK Upper Arm").get()

    # -- FK: rotating the FK upper arm moves the hand
    set_property(control, settings, "ik_fk", 0.0)
    before = world_head(deform, hand)
    control.pose.bones[fk_upper].rotation_mode = "XYZ"
    control.pose.bones[fk_upper].rotation_euler = (0, 0, math.radians(45))
    update()
    moved = (world_head(deform, hand) - before).length
    control.pose.bones[fk_upper].rotation_euler = (0, 0, 0)
    check(f"{label} : FK moves the hand", moved > 0.05, f"moved {moved:.3f}")

    # -- IK: moving the IK hand control drags the hand with it
    set_property(control, settings, "ik_fk", 1.0)
    update()
    at_rest = rest_drift(deform)
    check(f"{label} : switching to IK keeps the arm at rest", at_rest < 1e-4, f"drift {at_rest:.6f}")

    control.pose.bones[hand_ik].location = (0, 0, 0)
    update()
    target_before = world_head(deform, hand)
    control.pose.bones[hand_ik].location = (0, -0.1, 0)  # -- back along the bone, towards the shoulder
    update()
    ik_target = control.matrix_world @ control.pose.bones[hand_ik].head
    distance = (world_head(deform, hand) - ik_target).length
    moved = (world_head(deform, hand) - target_before).length
    check(f"{label} : the hand follows the IK control", distance < 1e-3 and moved > 0.05, f"{distance:.5f} from the control, moved {moved:.3f}")

    control.pose.bones[hand_ik].location = (0, 0, 0)
    set_property(control, settings, "ik_fk", arm.option("Default IK FK").get())
    update()
    drivers = [bone.name for bone in control.data.bones if bone.get("aniseed_drives") == upper]
    check(
        f"{label} : the upper arm is driven by its blended bone",
        drivers == [arm.output("Blended Upper Arm").get()] and drivers[0].startswith("MECH_UpperArmBlend"),
        str(drivers),
    )


def _check_leg(rig, deform, control, label):
    leg = rig.get_component_by_label(label)
    foot_ik = leg.output("IK Foot").get()
    toe = leg.input("Toe").get()
    foot = leg.input("Foot").get()

    before_toe = world_head(deform, toe)
    before_ankle = world_head(deform, foot)

    set_property(control, foot_ik, "heel_roll", 30.0)
    update()
    lifted = (world_head(deform, toe) - before_toe).z
    check(f"{label} : heel roll lifts the toes", lifted > 0.01, f"toe rose {lifted:.3f}")
    set_property(control, foot_ik, "heel_roll", 0.0)

    set_property(control, foot_ik, "ball_roll", 30.0)
    update()
    lifted = (world_head(deform, foot) - before_ankle).z
    check(f"{label} : ball roll lifts the heel", lifted > 0.01, f"ankle rose {lifted:.3f}")
    set_property(control, foot_ik, "ball_roll", 0.0)

    set_property(control, foot_ik, "bank", 20.0)
    update()
    banked = (world_head(deform, foot) - before_ankle).length
    check(f"{label} : bank tilts the foot", banked > 0.005, f"ankle moved {banked:.3f}")
    set_property(control, foot_ik, "bank", 0.0)

    control.pose.bones[foot_ik].location = (0, 0, 0.1)
    update()
    raised = (world_head(deform, foot) - before_ankle).z
    check(f"{label} : the IK foot control lifts the leg", raised > 0.05, f"ankle rose {raised:.3f}")
    control.pose.bones[foot_ik].location = (0, 0, 0)
    update()

    drift = rest_drift(deform)
    check(f"{label} : the leg returns to rest", drift < 1e-4, f"drift {drift:.6f}")


def _check_outputs(rig, control):
    """
    Checks every limb filled each of its outputs with one control armature
    bone, that every control has an output, and that the controls are
    parented to their Parent.
    """
    bad = []
    values = set()

    for component in rig.components():
        if not hasattr(component, "bone_input_names"):
            continue

        for output in component.outputs():
            value = output.get()
            if not isinstance(value, str) or value not in control.data.bones:
                bad.append(f"{component.label()}.{output.name()} = {value!r}")
            values.add(value)

    # -- Every control (a bone with a shape) should be some component's output
    without_output = [bone.name for bone in control.pose.bones if bone.custom_shape and bone.name not in values]

    check("Every limb output is a single control armature bone", not bad, f"bad: {bad}" if bad else "")
    check("Every control has an output", not without_output, f"missing: {without_output}" if without_output else "")

    spine = rig.get_component_by_label("Spine")
    expected_dynamic = {
        "Spine": ["Spine FK 01", "Spine FK 02", "Spine FK 03", "Blended Spine 01", "Blended Spine 03"],
        "Neck": ["Neck 01"],
        "Arm L": ["Thumb 01", "Index 03", "Pinky 03"],
    }
    missing = [f"{label}.{name}" for label, names in expected_dynamic.items() for name in names if rig.get_component_by_label(label).output(name) is None]
    check("Each control of a varying chain has its own output", not missing, f"missing: {missing}" if missing else "")

    # -- The arms' IK hands have space switches, so are under their space bones
    checks = (
        ("Arm L", ("Clavicle", "Pole")),
        ("Arm R", ("Clavicle", "Pole")),
        ("Leg L", ("FK Thigh", "IK Foot", "Pole")),
        ("Neck", ("Neck 01",)),
    )
    for label, output_names in checks:
        component = rig.get_component_by_label(label)
        expected = component.input("Parent").get()
        parents = {name: control.data.bones[component.output(name).get()].parent for name in output_names}
        check(
            f"{label} : its controls (IK included) are parented to its Parent",
            all(parent is not None and parent.name == expected for parent in parents.values()),
            f"Parent is {expected}: " + str({name: parent.name if parent else None for name, parent in parents.items()}),
        )

    root_offset = rig.get_component_by_label("Root").output("Offset Control").get()
    torso = control.data.bones[spine.output("Torso").get()].parent
    check("Spine : the torso is parented to the root offset", torso is not None and torso.name == root_offset)


def _check_singular(rig, deform, control, label, deform_parent):
    singular = rig.get_component_by_label(label)
    bone = singular.input("Bone").get()
    ctl = singular.output("Control").get()

    check(
        f"{label} : its bone starts at the tail of {deform_parent}, parented to it",
        bone in deform.data.bones
        and deform.data.bones[bone].parent is not None
        and deform.data.bones[bone].parent.name == deform_parent
        and (deform.data.bones[bone].head_local - deform.data.bones[deform_parent].tail_local).length < 1e-5,
        bone,
    )

    parent = control.data.bones[ctl].parent
    check(
        f"{label} : its control is under its Parent",
        parent is not None and parent.name == singular.input("Parent").get(),
        f"{ctl} is under {parent.name if parent else None}",
    )

    before = world_head(deform, bone)
    control.pose.bones[ctl].location = (0, 0.05, 0)
    update()
    moved = (world_head(deform, bone) - before).length
    control.pose.bones[ctl].location = (0, 0, 0)
    update()
    check(f"{label} : the control drives the bone", abs(moved - 0.05) < 1e-4, f"moved {moved:.4f}")


def _world(control, bone):
    return control.matrix_world @ control.pose.bones[bone].matrix


def _check_space_switches(rig, deform, control):
    hand_space = rig.get_component_by_label("Hand Space L")
    data = hand_space.get_data()
    check(
        "Space switch : hooks to the IK hand and starts with Parent and World spaces",
        hand_space.input("To Be Driven").get(resolved=False) == "[Arm L].[output].[IK Hand]"
        and [(space["label"], space["target"]) for space in data["spaces"]]
        == [("Parent", "[Spine].[output].[Blended Chest]"), ("World", "[Root].[output].[Offset Control]")],
        str([(space["label"], space["target"]) for space in data["spaces"]]),
    )

    mirrored = rig.get_component_by_label("Hand Space R")
    check(
        "Space switch : mirroring the arm mirrors its space switch",
        mirrored is not None and mirrored.input("To Be Driven").get(resolved=False) == "[Arm R].[output].[IK Hand]",
        mirrored.input("To Be Driven").get(resolved=False) if mirrored else "missing",
    )

    arm = rig.get_component_by_label("Arm L")
    hand_ik = arm.output("IK Hand").get()
    settings = arm.output("Settings").get()
    space_bone = hand_space.output("Space Bone").get()
    pose_bone = control.pose.bones[hand_ik]

    check("Space switch : the control is parented to its space bone", control.data.bones[hand_ik].parent.name == space_bone)

    items = [item[1] for item in pose_bone.id_properties_ui("space").as_dict().get("items", [])]
    check("Space switch : the space property is a drop down of the spaces", pose_bone["space"] == 0 and items == ["Parent", "World"], f"{pose_bone['space']} {items}")

    spine = rig.get_component_by_label("Spine")
    chest_ik = spine.output("Chest IK").get()
    root_offset = rig.get_component_by_label("Root").output("Offset Control").get()

    set_property(control, settings, "ik_fk", 1.0)

    # -- Parent space: the IK hand follows the chest
    before = _world(control, hand_ik).translation.copy()
    control.pose.bones[chest_ik].location = (0.1, 0, 0)
    update()
    followed = (_world(control, hand_ik).translation - before).length
    control.pose.bones[chest_ik].location = (0, 0, 0)
    update()
    check("Space switch : in the Parent space the IK hand follows the chest", followed > 0.02, f"moved {followed:.3f}")

    # -- Switching keeps the control's own values, and at rest moves nothing
    pose_bone.location = (0, -0.05, 0)
    update()
    basis = pose_bone.matrix_basis.copy()
    set_property(control, hand_ik, "space", 1)
    check("Space switch : switching space leaves the control's values alone", pose_bone.matrix_basis == basis)
    pose_bone.location = (0, 0, 0)
    update()
    drift = rest_drift(deform)
    check("Space switch : at rest, switching space moves nothing", drift < 1e-4, f"drift {drift:.6f}")

    # -- World space: the chest no longer moves it, the root offset does
    before = _world(control, hand_ik).translation.copy()
    control.pose.bones[chest_ik].location = (0.1, 0, 0)
    update()
    after_chest = (_world(control, hand_ik).translation - before).length
    control.pose.bones[chest_ik].location = (0, 0, 0)
    control.pose.bones[root_offset].location = (0, 0.1, 0)
    update()
    after_root = (_world(control, hand_ik).translation - before).length
    control.pose.bones[root_offset].location = (0, 0, 0)
    update()
    check(
        "Space switch : in the World space the chest does not move the IK hand, the root does",
        after_chest < 1e-4 and abs(after_root - 0.1) < 1e-3,
        f"chest moved it {after_chest:.5f}, root moved it {after_root:.4f}",
    )

    set_property(control, hand_ik, "space", 0)
    set_property(control, settings, "ik_fk", arm.option("Default IK FK").get())

    # -- Orientation only: in the World space the head keeps its rotation
    # -- when the neck turns, but still moves with it
    neck = rig.get_component_by_label("Neck")
    head = neck.output("Head").get()
    neck_control = neck.output("Neck 01").get()
    neck_pose = control.pose.bones[neck_control]
    neck_pose.rotation_mode = "XYZ"

    def turn_neck():
        start = _world(control, head)
        neck_pose.rotation_euler = (math.radians(30), 0, 0)
        update()
        end = _world(control, head)
        neck_pose.rotation_euler = (0, 0, 0)
        update()
        turned = start.to_quaternion().rotation_difference(end.to_quaternion()).angle
        return turned, (end.translation - start.translation).length

    turned, _ = turn_neck()
    check("Space switch : orientation only, in the Neck space the head turns with the neck", turned > 0.3, f"turned {math.degrees(turned):.1f} degrees")

    set_property(control, head, "space", 1)
    turned, moved = turn_neck()
    check(
        "Space switch : orientation only, in the World space the head keeps its rotation but moves with the neck",
        turned < 1e-4 and moved > 0.005,
        f"turned {math.degrees(turned):.4f} degrees, moved {moved:.3f}",
    )
    set_property(control, head, "space", 0)


def _check_spine(rig, deform, control):
    spine = rig.get_component_by_label("Spine")
    chest = spine.input("Spine").get()[-1]
    chest_ik = spine.output("Chest IK").get()

    def chest_tip():
        return deform.matrix_world @ deform.pose.bones[chest].tail

    before = chest_tip()
    control.pose.bones[chest_ik].location = (0.1, 0, 0)
    update()
    moved = (chest_tip() - before).length
    check("Spine : moving the chest IK control bends the spine", moved > 0.02, f"chest moved {moved:.3f}")
    control.pose.bones[chest_ik].location = (0, 0, 0)
    update()

    # -- FK: rotating the first FK spine control bends everything above it
    settings = next(bone for bone in control.data.bones.keys() if bone.startswith("CTL_SpineSettings"))
    first_fk = next(bone for bone in control.data.bones.keys() if bone.startswith("CTL_SpineFk"))
    set_property(control, settings, "ik_fk", 0.0)
    check("Spine : switching to FK keeps the spine at rest", rest_drift(deform) < 1e-4)

    control.pose.bones[first_fk].rotation_mode = "XYZ"
    control.pose.bones[first_fk].rotation_euler = (math.radians(20), 0, 0)
    update()
    moved = (chest_tip() - before).length
    check("Spine : the FK controls bend the spine", moved > 0.05, f"chest moved {moved:.3f}")

    control.pose.bones[first_fk].rotation_euler = (0, 0, 0)
    set_property(control, settings, "ik_fk", spine.option("Default IK FK").get())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        RESULTS.append(False)

    failed = RESULTS.count(False)
    print(f"\n{len(RESULTS) - failed} passed, {failed} failed")
    sys.stdout.flush()
    os._exit(1 if failed or not RESULTS else 0)
