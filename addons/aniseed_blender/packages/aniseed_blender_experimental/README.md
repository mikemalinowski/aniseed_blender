# aniseed_blender_experimental

An experiment in rigging the Blender way with aniseed: the user owns a
**deform armature** (the skeleton meshes are skinned to and which is
exported), and every build creates a **control armature** which drives it.
Like aniseed_maya, the rig is either *editable* (no control rig, bones free to
move) or *built*.

The package is **on by default**. It can be turned off with **Edit >
Packages...** in the aniseed app.

## Using it

1. Create a rig with **Rig Configuration : Experiment**. This adds the stack
   below, the rig's groups, and an empty deform armature.
2. Add components beneath **Build Rig > Components**, each beneath the one it
   attaches to: **Root**, then **IKFK Spine** beneath it, then **Neck And
   Head**, **Arm** and **Leg** beneath the spine. Each creates its bones as it
   is added, beneath the selected deform bone. With no deform bone selected,
   they go beneath the matching bone of the component above (arms and the
   neck the chest, legs the pelvis). **Right click > Create Bones** works the
   same way. **Singular** is one bone and one control, for anything else (a
   prop beneath an Arm, for example, starts at the end of the hand). Set its
   Description, Location and Shape before adding it.
3. Right click an Arm or Leg > **Mirror** to make the other side, with
   mirrored bones (and foot pivots).
4. Fit the bones to the character in edit mode (right click > **Select
   Bones** takes you there), and move the leg's pivot Empties to the edges of
   the foot.
5. Shape the spine: right click the spine > **Create Guide**, shape the curve,
   then **Remove Guide** to store it (Build Rig also stores any open guide).
6. **Build Rig**. The control armature is left selected in pose mode, ready
   to animate.
7. Tailor the controls in Blender (Bone properties > Viewport Display >
   Custom Shape, and Bone Color), then press **Snapshot** on **Control
   Visuals**. Every build after that re-applies them.
8. **Make Rig Editable** to change the bones again, then **Build Rig**.
9. **Save** the recipe. It holds the deform skeleton (and pivots), so loading
   it into an empty scene recreates the bones before the components are added.

`recipes/biped.json` is a complete biped to start from (regenerate it with
`recipes/generate_biped.py`).

## The stack

```
Rig Configuration : Experiment
Make Rig Editable
    Enter Object Mode            Set Mode (Object): leaves any mode, committing bone edits
    Unlink Deformation Rig       removes the link constraints, resets the pose
    Delete Control Rig           control armature, spline curve, widgets
Build Rig
    Ensure Rig Is Editable       runs Make Rig Editable
    Remove All Guides            stores and removes any open guide
    Create Control Armature
    Components                   <- the limbs go here
    Post Build
        Link Deformation Rig     Copy Transforms (world) on every deform bone
        Control Visuals          re-applies the snapshotted shapes and colours
        Finalise                 hides the Mechanics collection and the deform armature
        Enter Pose Mode          Set Mode (Pose): selects the control armature, pose mode
```

The Blender host leaves modes and the selection alone: whatever the stack
does is what the user is left with. **Set Mode** puts the control or deform
armature (or any object given as its Object input) into object, pose or edit
mode, so each execution block can leave the scene as it needs.

## How it fits together

* **Two armatures**, told apart by a custom property
  (`obj["aniseed_role"]` is `"deform"` or `"control"`), never by name.
* **Inputs are deform bones.** Each limb's inputs name bones in the deform
  armature. The deform hierarchy lives in the armature alone; nothing on the
  component says what its bones are parented to.
* **Building** creates CTL (control) and MECH (mechanical) bones in the
  control armature. Each bone which drives a deform bone carries an
  `aniseed_drives` custom property naming it, and **Link Deformation Rig**
  constrains every deform bone named that way, so nothing needs wiring.
* **Parent** is the control armature bone everything a limb builds is
  parented to, IK controls and poles included, normally an address of
  another component's output. When a limb is added beneath another, its
  Parent is hooked to that component's outputs (with `hook_to_parent`, as in
  aniseed_maya): arms and the neck to the spine's **Blended Chest**, legs to
  its **Blended Pelvis**, otherwise the parent's default output. Point it at
  any other output (such as the spine's **Chest IK**) to re-parent the
  controls. The control hierarchy is therefore free to differ from the
  deform one.
* **Outputs.** Every control a limb creates has an output of its own, so any
  of them can be another component's Parent. Mechanical bones other
  components may find useful have outputs too, such as the blended bones
  (what the deform bones follow). Where the number of controls varies (spine,
  neck and finger controls), the build declares numbered outputs, such as
  "Spine FK 01" or "Index 02", so they appear once the rig has been built.
* **IK/FK** limbs build an FK chain, an IK chain and a blend chain (which the
  deform bones follow). An `ik_fk` property on the limb's settings control
  (the `core_config` shape) blends between them: 0 is FK, 1 is IK. The leg's foot
  roll properties (`heel_roll`, `ball_roll`, `toe_roll`, `bank`, `swivel`, in
  degrees) are on the IK foot control. Every driver is a simple expression, so
  rigs work without "Auto Run Python Scripts".
* **Naming** is `TYPE_ObjectDescription_##_LOCATION` (`DEF_UpperArm_01_L`,
  `CTL_HandIk_01_R`, `MECH_SpineBlend_02_M`), unique across the file's objects
  and the rig's bones. `L` / `R` as the last part means Blender's own Paste
  Pose Flipped and X-Axis Mirror recognise the sides.
* **Control shapes** are json files in `resources/shapes`, one per shape,
  named by their file name (`core_circle`). They store NURBS curves the same
  way as the Maya toolkit's shapes, so a shape file can be copied from one
  host's shapes folder to the other's. `lib/widgets.py` reads them (sampling
  curves above degree 1) and writes them (`save_shape` turns a curve or mesh
  object into a shape file). Each rig gets its widget meshes in a hidden
  `<rig>_Widgets` collection.
* **The skeleton in the recipe** is stored by the Blender host (in
  aniseed_blender_standard), which saves every Empty and armature beneath the
  rig, with their bones and bone parenting. Objects with an
  `aniseed_transient` custom property (the control armature) are left out.
* **Space switching.** Add **Space Switch** beneath the component whose
  control it switches (after any component providing a space). Added beneath
  an Arm or Leg it picks the IK control, and starts with a **Parent** space
  (where that component's controls go) and a **World** space (the root offset
  control); edit the spaces in its option panel, as in aniseed_maya. The
  build gives the control a mechanical `Space` bone as its parent, which
  follows the chosen space through an Armature constraint, and adds a
  `space` drop down property to the control (or the Attribute Host). The
  control's own values never change when switching, though it jumps to the
  new space. **Position Only** or **Orientation Only** add a second
  mechanical `Switch` bone: the space bone keeps following the control's
  original parent and copies only the switch bone's location or rotation.

## Notes and limitations

* The spine's Spline IK curve defaults to a **poly** curve through the spine
  joints, which matches the bones exactly at rest. A NURBS curve bends more
  smoothly but cannot pass through every joint, so on a curved spine the
  deform bones visibly move away from their rest pose. Convert the guide with
  **Set Spline Type** before Remove Guide if you prefer smoothness.
* The spine has no twist from the chest control yet, and there is no
  stretch, twist bones or IK/FK snapping.
* Switching space is not yet matched (the control jumps to the new space),
  and the space switch has no per space Snap To or Include Scale (an
  Armature constraint always includes scale).
* The IK hand control is aligned to the hand bone (there is no world aligned
  option yet).
* Mirroring creates the other side's bones from the original's. If the other
  side's bones already exist (the user built a symmetric skeleton) and no
  other component uses them, they are used instead.

## Layout

```
base.py         LimbComponent (shared by the limbs) and the Builder they use
lib/            plain bpy helpers: armatures, context, curves, mirroring,
                rigging, widgets
mixins/         CreateBonesMixin, GuideMixin, MirrorMixin
components/     config, structure (control armature, linking, guides, modes,
                finalise), visuals, limbs, basic (singular), augments
                (space switch)
recipes/        biped.json and the script which generates it
resources/      shapes: the control shape library, one json file per shape
tests/          run_build.py: builds the biped in background Blender and
                checks it (bones, mirroring, rest pose, FK, IK, foot roll,
                spine, space switches, visuals, save and load)
```

Component modules import `base` as a module (`from aniseed_blender_experimental
import base`), never `LimbComponent` by name: the component factory registers
every RigComponent subclass it finds in a module's namespace.
