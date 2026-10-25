# aniseed_blender_standard

An aniseed package holding the standard Blender content for aniseed. It is
the Blender counterpart of `aniseed_maya_standard`, and holds the Blender
host (`hosts/blender.py`) and the framework the toolkits are built on
(`toolkit/`).

The host:

* launches the aniseed app as a Qt window parented to Blender, through
  qshake (bundled in the add-on's `vendor` folder), which owns the
  QApplication and pumps Qt from a Blender timer
* adds an **Aniseed** menu to the top bar (Builder, an entry per active
  toolkit, Website, Reload, About)
* runs every build with a full Blender context (window, screen, 3D viewport),
  as one undo step, and puts the user's selection and active object back
  afterwards
* flushes rig recipes before saves and undos, and releases rigs after undo,
  redo and file loads, as Blender invalidates every python reference to its
  data at those points
* stores the rig's Empties (groups and guides) with saved recipes, and
  recreates them when a recipe is loaded

The toolkit framework:

* `toolkit/core.py`: `Tool` (an xstack component with options only),
  `Organiser`, and `ToolkitStack`, which fills itself with a toolkit's tools
  (from every active package's `tools` folder) under an organiser per
  category, with a Favourites organiser first. It runs each tool as one undo
  step with a full Blender context, and remembers option values and
  favourites between sessions. Every tool offers Add To / Remove From
  Favourites on its right click menu (`Tool.user_functions`)
* `toolkit/app.py`: the toolkit window, an xstack app with a read only
  structure, where double clicking a tool (or the Run button beneath its
  options) runs it and only the tool itself can be run (never the whole
  stack). Each toolkit's config gives it its own icon and stack background
* `toolkit/scene.py`: selection and control helpers for tools

A toolkit is an aniseed package with a `"toolkit"` entry in its
`aniseed_package.json` and a `launch()` function (see
`aniseed_riggers_toolkit`).

The host is only loaded where `bpy` can be imported, so other applications
never see it. It is found through `ANISEED_PACKAGE_PATHS`, which the Aniseed
add-on sets to its `packages` folder. See the README at the root of the
repository for installing.
