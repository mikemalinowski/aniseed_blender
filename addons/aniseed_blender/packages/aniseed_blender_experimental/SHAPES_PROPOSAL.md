# Proposal: per-file control shapes in aniseed_blender_experimental

## Summary

Swap the single pre-converted `lib/shapes.json` for a `resources/shapes/`
folder holding the Maya toolkit's shape files exactly as they are
(`core_*.json`). `lib/widgets.py` then reads the Maya curve format (cvs, knots,
degree, form) directly and gets a function that writes a shape back out in
that same format.

Maya and Blender each keep their own shape folder, and either can grow on its
own; neither one is the master copy. What they share is the file format and
the naming, so you can copy any shape file from one host's folder into the
other's and it just works.

Decisions made:

- Shape names are the file names, as in Maya (`core_circle`, not `circle`).
- No source of truth: the two folders are separate and only share the
  format.
- Writing is a library function only (no operator or UI).

## Current state

| Piece | Maya (`aniseed_toolkit`) | Blender (`aniseed_blender_experimental`) |
|---|---|---|
| Data | `_resources/shapes/core_*.json`, one file per shape (31 files) | `lib/shapes.json`, one file with all 31 shapes |
| Format | `{"node": str, "curves": [{"cvs", "degree", "form", "knots"}]}` | `{name: {"verts": [...], "edges": [...]}}`, already turned into polylines and rounded to 4 dp |
| Reader | `scene/shapes.py` (`shape_data_from_file`, `load_shape`) | `lib/widgets.py` (`library()`, `widget()`) |
| Writer | `scene/shapes.py` (`shape_to_dict`, `save_to_file`) | none |
| Conversion | none | `scripts/convert_maya_shapes.py`: de Boor sampling of degree > 1 curves, 6 samples per span, drops the `core_` prefix |

What uses `widgets.py` today:

- `base.py`: `widgets.widget(rig_label, shape, name)` in `apply_visual`, and
  `widgets.shape_of(...)` in `read_visual`
- `components/basic/singular.py`: `sorted(widgets.library())` for the shape
  picker, and `... not in widgets.library()` to check the option
- `components/structure/control_armature.py`: `widgets.remove_widgets(...)`
- Components ask for shapes by their short name (`"circle"`, `"cube"`,
  `"pinched_circle"`, `"config"`, ...). That name is also stored on each widget
  object (`aniseed_shape`) and in visual snapshots.

What the Maya files contain (I checked all 31):

- Only the keys `curves` and `node`.
- Degree 1 (polylines) and degree 3 curves. Every file is `form` 0 except
  `core_brain`, which is `form` 2 (periodic).
- Knots use Maya's convention: `len(cvs) + degree - 1` knots, without the two
  end knots.

## Proposed changes

### 1. New folder `resources/shapes/`

```
aniseed_blender_experimental/
    resources/
        shapes/
            core_arrow.json
            ...
            core_teardrop.json      (all 31, copied byte for byte)
```

- The files keep their names and their contents (including `"node"`). This
  copy is a one-off starting point; after it the folder grows on its own.
- The library name of a shape is its file name without `.json`, as in Maya's
  `shape_data_from_file`. So `core_circle.json` is `"core_circle"`, and a
  shape saved as `my_shape.json` is `"my_shape"`.

### 2. `lib/widgets.py`, reading

The widget mesh stays a mesh object made of loose edges (unchanged), so
custom shapes, the hidden `<rig>_Widgets` collection, `SHAPE_KEY`/`RIG_KEY`,
`shape_of` and `remove_widgets` do not change.

Proposed API (bpy-free helpers sit next to the bpy ones):

```python
SHAPES_FOLDER = os.path.join(os.path.dirname(__file__), "..", "resources", "shapes")
SAMPLES_PER_SPAN = 6

def library() -> dict:
    """{shape name: shape data as stored in its file}. Loaded once, from SHAPES_FOLDER."""

def shape_path(shape: str) -> str:
    """The file a shape is stored in: SHAPES_FOLDER/<shape>.json."""

def read_shape(shape_file: str) -> dict:
    """Loads one shape file (a library name or an absolute path, .json optional)."""

def polylines(data: dict) -> tuple[list, list]:
    """Turns shape data (curves) into (verts, edges) for a loose edge mesh."""

def widget(rig_label: str, shape: str, name: str):   # unchanged signature
    ...
    verts, edges = polylines(library()[shape])
    mesh.from_pydata(verts, edges, [])
```

- `library()` keeps returning a dict keyed by shape name, so `sorted(...)`,
  `in` and `library()[shape]` (which raises `KeyError`, as `apply_visual`
  expects) all keep working. The values change from `{verts, edges}` to the
  raw curve data. Nothing outside `widgets.py` reads the values.
- The `_de_boor` / `_curve_points` code moves from
  `scripts/convert_maya_shapes.py` into `widgets.py` unchanged (`polylines`
  is the old `convert` loop for a single shape). Degree 1 curves use their
  CVs as they are; higher degrees are sampled, and closed forms get a
  closing edge.
- Vertex values are no longer rounded to 4 dp, so widgets can move by up to
  0.00005 compared with today's meshes. You won't see this, and nothing
  compares positions that closely.

### 3. `lib/widgets.py`, writing

```python
def shape_data(obj) -> dict:
    """
    Reads a Blender object into shape data ({"node", "curves": [...]}) in
    the Maya format, in the object's local space.

    - CURVE objects: one entry per spline.
        POLY   -> degree 1, cvs = points, knots 0..n-1
        NURBS  -> degree = order - 1, cvs = points (xyz, weight dropped),
                  knots in Maya form (clamped if use_endpoint_u, else
                  uniform); use_cyclic_u -> form 2 with the first `degree`
                  cvs repeated at the end
        BEZIER -> degree 3, cvs = knot/handle points, knots with
                  multiplicity 3 at each segment (an exact conversion)
    - MESH objects (for example an existing widget): the loose edges are
      walked into chains, and each chain becomes a degree 1 curve (a
      closed loop repeats its first cv, as core_cube does), form 0.
    """

def write_shape(filepath: str, data: dict) -> dict:
    """
    Writes shape data to filepath as Maya does (json, indent=4,
    sort_keys=True) and returns it. If the file is in SHAPES_FOLDER, the
    library cache is cleared so the shape shows up.
    """

def save_shape(obj, filepath: str) -> dict:
    """write_shape(filepath, shape_data(obj)); writes nothing and returns {} if obj has no curves/edges."""
```

These follow Maya's `shape_to_dict` / `save_to_file` pair, so a shape file
saved in Blender can be copied into Maya's shapes folder and loaded with
`load_shape`, and the other way round.

They are library functions only, with no operator or UI.

### 4. Renaming shapes to their file names

Every shape name used in code changes to the file name:

| File | Change |
|---|---|
| `components/limbs/arm.py` | `pinched_circle`, `circle` (x2), `cube`, `sphere`, `config` → `core_...` |
| `components/limbs/leg.py` | `circle`, `foot_paddle`, `sphere`, `config` → `core_...` |
| `components/limbs/ikfk_spine.py` | `rounded_square`, `half_circle`, `circle`, `cube`, `config` → `core_...` |
| `components/limbs/neck_head.py` | `circle` (x2) → `core_circle` |
| `components/limbs/root.py` | `circle` (x2) → `core_circle` |
| `components/basic/singular.py` | `Shape` option default `"cube"` → `"core_cube"` |
| `tests/run_build.py` | Singular options `"sphere"`, `"teardrop"` → `core_...` |
| `README.md` | "the "config" shape" → `core_config` |

What this does to existing data:

- **Widget object names** come from
  `config.generate_name(config.widget, shape, config.middle)`, so they pick
  up the prefix. Something like `WGT_Circle_M` would become something like
  `WGT_CoreCircle_M`, depending on how `generate_name` handles the
  underscore. The widgets are rebuilt on every build, so this is cosmetic.
- **Old names stop resolving.** Any Singular component in a saved recipe
  with `Shape` set to the old short name, and any Control Visuals data
  stored with old names, would fail the lookup. Singular already refuses to
  build with "there is no shape called ...", and `apply_visual` logs a
  warning and leaves the bone's shape as it is.
  - Proposed: no aliasing. The package is experimental, and
    `recipes/biped.json` stores no shape names (I checked).
  - The fallback, if you want it: Control Visuals has a `version` key, so
    stored version 1 data could be migrated by adding the prefix to its
    shape names.

### 5. Removals and docs

- Delete `lib/shapes.json`.
- Delete `scripts/convert_maya_shapes.py`, since its logic now lives in
  `widgets.py`. That leaves `scripts/` empty, so remove the folder too.
- Update the `widgets.py` module docstring and the README:
  - "Control shapes" bullet: shapes are one file per shape in
    `resources/shapes/`, in the same format as aniseed_toolkit, so a file
    can be copied between the hosts; `widgets.save_shape` writes new ones.
  - "Layout" block: add `resources/`, and drop `shapes.json` and
    `convert_maya_shapes.py`.

## Verification plan

1. bpy-free check (plain `python -B`): for every shape,
   `polylines(library()["core_" + old_name])` matches the old `shapes.json`
   entry: same edge lists, verts within 1e-4. Run this before deleting
   `shapes.json`.
2. Round trip in Blender 4.2 and 5.1 (background): build each widget, then
   `shape_data` on the widget mesh, then `write_shape` to the scratchpad, then
   reload, and check the polylines match.
   Also a NURBS, a poly and a Bezier curve object through `save_shape`, then
   `polylines`, against Blender's own evaluated curve.
3. Cross-host check: load a shape file written by `save_shape` in mayapy with
   `aniseed_toolkit` `load_shape`, to confirm Maya accepts it.
4. `tests/run_build.py` on both Blender versions: the biped builds, and the
   visual checks and save/load pass.
5. Grep for any bare shape names left over (`"circle"`, `"cube"`, ...).

## Open question

1. **Old short names.** Proposed: no aliasing, so old names fail with the
   existing warnings. The alternative is migrating stored Control Visuals
   version 1 data by adding the `core_` prefix (see section 4).
