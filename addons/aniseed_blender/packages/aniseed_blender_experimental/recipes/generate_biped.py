"""
Creates the biped rig (root, spine, neck and head, and both arms and legs)
in a new, empty file and saves its recipe to biped.json beside this file. The
recipe holds the deform skeleton, so loading it into an empty scene recreates
the bones.

You only need this if you change the components and want to update the
recipe. To try the components, load biped.json instead.

From Blender's Python Console (with the Aniseed add-on enabled). This
replaces the open file, so save your work first:

    import runpy
    runpy.run_path(r"<path to this file>", run_name="generate_biped")

From the command line:

    blender --background --factory-startup --python generate_biped.py -- [output path]
"""
import os
import sys


def build_biped_rig():
    """
    Starts a new, empty file and creates the biped rig in it, with its bones.
    The rig is left editable (not built).

    Returns:
        The aniseed.Rig
    """
    import bpy
    import aniseed

    # -- In case the user has turned the package off, turn it on for this
    # -- session only, so their own choice (Edit > Packages) is left alone
    aniseed.packages.set_enabled("aniseed_blender_experimental", True, persist=False)

    bpy.ops.wm.read_homefile(use_empty=True)

    # -- Creating the rig with the configuration sets up the Make Rig
    # -- Editable and Build Rig blocks, the groups and the deform armature
    rig = aniseed.Rig(label="BipedRig", configuration="Rig Configuration : Experiment")
    components = rig.get_component_by_label("Components")

    # -- Each component creates its bones as it is added, attached to the
    # -- component above it
    root = rig.add_component("Experiment : Root", "Root", parent=components)
    spine = rig.add_component("Experiment : IKFK Spine", "Spine", parent=root)
    neck = rig.add_component("Experiment : Neck And Head", "Neck And Head", parent=spine)
    arm = rig.add_component("Experiment : Arm", "Arm L", parent=spine)
    leg = rig.add_component("Experiment : Leg", "Leg L", parent=spine)

    add_space_switches(rig, root, spine, neck, arm, leg)

    # -- Mirroring the limbs mirrors their space switches too
    arm.mirror()
    leg.mirror()

    return rig


def add_space_switches(rig, root, spine, neck, arm, leg):
    """
    Adds space switches to the IK hand and foot controls, their poles and the
    head, with the same spaces and defaults as aniseed_maya's arm and leg.
    "Parent" is the limb's own Parent input, so it follows the limb if it is
    re-parented.
    """
    space_switch = rig.component_library.request("Experiment : Space Switch")
    world = root.output("Offset Control").address()

    space_switch.add_to(
        arm,
        "Hand Space L",
        driven=arm.output("IK Hand").address(),
        default_space="World",
        spaces=[
            ("World", world),
            ("Parent", arm.input("Parent").address()),
            ("Shoulder", arm.output("Clavicle").address()),
        ],
    )

    space_switch.add_to(
        arm,
        "Arm Pole Space L",
        driven=arm.output("Pole").address(),
        default_space="Hand",
        spaces=[
            ("World", world),
            ("Parent", arm.input("Parent").address()),
            ("Shoulder", arm.output("Clavicle").address()),
            ("Hand", arm.output("IK Hand").address()),
        ],
    )

    space_switch.add_to(
        leg,
        "Foot Space L",
        driven=leg.output("IK Foot").address(),
        default_space="World",
        spaces=[
            ("World", world),
            ("Parent", leg.input("Parent").address()),
        ],
    )

    space_switch.add_to(
        leg,
        "Leg Pole Space L",
        driven=leg.output("Pole").address(),
        default_space="Foot",
        spaces=[
            ("World", world),
            ("Parent", leg.input("Parent").address()),
            ("Foot", leg.output("IK Foot").address()),
        ],
    )

    # -- The head keeps following the neck's position, and switches only
    # -- which space it takes its rotation from
    head_space = space_switch.add_to(
        neck,
        "Head Space",
        driven=neck.output("Head").address(),
        default_space="Neck",
        spaces=[
            ("Neck", f"[{neck.label()}].[output].[Neck 01]"),
            ("Chest", spine.output("Blended Chest").address()),
            ("World", world),
        ],
    )
    head_space.set_orientation_only(True)


def save_biped(path=None):
    """
    Creates the biped rig and saves its recipe.

    Returns:
        The path the recipe was saved to.
    """
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "biped.json")

    rig = build_biped_rig()
    rig.save(path)

    return path


def _initialise_background_blender():
    """
    Makes aniseed importable in a background Blender (where the add-on is not
    enabled). This file lives in aniseed_blender/packages/<package>/recipes,
    so the folder holding the add-on is four levels up.
    """
    addons = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
    sys.path.insert(0, addons)

    import aniseed_blender

    aniseed_blender.install_pyside()
    aniseed_blender.initialise()


if __name__ == "__main__":
    _initialise_background_blender()
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    print(f"Saved {save_biped(arguments[0] if arguments else None)}")

elif __name__ == "generate_biped":
    print(f"Saved {save_biped()}")
