# aniseed_blender_standard

An aniseed package holding the standard Blender content for aniseed. It is
the Blender counterpart of `aniseed_maya_standard`, and currently holds just
the Blender host, in `hosts/blender.py`. It:

* launches the aniseed app as a Qt window parented to Blender, through
  qshake (bundled in the add-on's `vendor` folder), which owns the
  QApplication and pumps Qt from a Blender timer
* adds an **Aniseed** menu to the top bar (Builder, Website, Reload, About)
* runs every build with a full Blender context (window, screen, 3D viewport),
  as one undo step, and puts the user's selection and active object back
  afterwards
* flushes rig recipes before saves and undos, and releases rigs after undo,
  redo and file loads, as Blender invalidates every python reference to its
  data at those points
* stores the rig's Empties (groups and guides) with saved recipes, and
  recreates them when a recipe is loaded

The host is only loaded where `bpy` can be imported, so other applications
never see it. It is found through `ANISEED_PACKAGE_PATHS`, which the Aniseed
add-on sets to its `packages` folder. See the README at the root of the
repository for installing.
