"""
Provides the Blender host for aniseed. It:

    * launches the aniseed app as a Qt window parented to Blender, via qshake
    * adds an "Aniseed" menu to Blender's top bar
    * gives every build a full Blender context and makes it one undo step
    * keeps aniseed's shared rigs in step with undo and with files being
      saved and loaded
    * stores the rig's Empties (groups and guides) and armatures (with their
      bones) with saved recipes, and recreates them when a recipe is loaded

Blender invalidates every python reference to its data whenever a file is
loaded or an undo/redo happens. aniseed's rigs hold their host object, so the
rigs are released at those points and the app is pointed at the new data.
"""
import logging
import contextlib
import webbrowser

import bpy
from bpy.app.handlers import persistent

import qtility
import aniseed
from Qt import QtWidgets, QtGui

try:
    from shiboken6 import isValid

except ImportError:
    from shiboken2 import isValid

log = logging.getLogger(__name__)

# -- The modules dropped (and re-imported) by the Reload menu entry
CRITICAL_MODULES = [
    "aniseed",
    "xstack",
    "crosswalk",
    "qtility",
    "signalling",
    "factories",
]


# --------------------------------------------------------------------------------------
class BlenderHost(aniseed.EmbeddedHost):
    """
    The aniseed host used whenever aniseed runs inside Blender. It is only
    loaded where bpy can be imported, so other applications never see it.
    """

    name = "blender"
    priority = 0

    def __init__(self):
        super().__init__()
        _register_handlers()

    # ----------------------------------------------------------------------------------
    def launch(self) -> bool:
        """
        Shows the aniseed app as a window parented to Blender, reusing the
        window if it is already open.

        Returns True, as the host manages the launch itself.
        """
        # -- qshake makes PySide6 usable in Blender: it owns the QApplication,
        # -- pumps the Qt event loop from a Blender timer (Blender owns the
        # -- main loop, so app.exec() must never be called), and parents
        # -- windows to Blender's main window so they stay above it, minimise
        # -- with it and get no taskbar entry of their own.
        import qshake

        window = BlenderAppWindow.instance()

        if window is None:
            window = BlenderAppWindow()

            # -- Qt opens new windows on whichever screen the mouse is on,
            # -- which may not be the one Blender is on. Start it centred
            # -- over Blender's own window instead. After this, the window
            # -- stays wherever the user moves it.
            handle = qshake.main_window_handle()
            if handle:
                # -- Qt.py does not expose QWindow, so take it from PySide6
                from PySide6.QtGui import QWindow

                blender = QWindow.fromWinId(handle).geometry()
                if blender.isValid():
                    window.move(blender.center() - window.rect().center())

        # -- Parents the window to Blender, shows it, and keeps it alive
        qshake.show(window)
        return True

    # ----------------------------------------------------------------------------------
    def environment_initialization(self):
        """
        Adds the Aniseed menu to Blender's top bar.
        """
        _register_menu()

    # ----------------------------------------------------------------------------------
    def environment_teardown(self):
        """
        Removes everything environment_initialization and this host added to
        Blender. Called when the add-on is disabled, and before a reload.
        """
        _unregister_menu()
        _unregister_handlers()

        window = BlenderAppWindow.instance()
        if window:
            window.close()

    # ----------------------------------------------------------------------------------
    @contextlib.contextmanager
    def build_context(self, rig):
        """
        Runs the build with a full Blender context, as a single undo step.

        A build started from the app runs inside qshake's timer, where Blender
        provides almost no context (there is no window or area), so operators
        such as mode_set would fail. The build is given the main window and
        its largest 3D viewport instead.

        Modes and the selection are left to the rig's components, so each
        stack decides what state the scene is left in.
        """
        _push_undo(f"Before Aniseed Build : {rig.label}")

        with bpy.context.temp_override(**_full_context()):
            yield

        _push_undo(f"Aniseed Build : {rig.label}")

    # ----------------------------------------------------------------------------------
    def on_rig_save(self, rig) -> dict:
        """
        Stores the Empties and armatures beneath the rig object (such as its
        groups, guides and skeleton, with every bone) with the recipe, so
        loading the recipe into an empty scene recreates them. Meshes and
        other objects are not stored.

        An object with a TRANSIENT_KEY custom property set (such as a control
        rig which every build recreates) is not stored, nor is anything
        beneath it.
        """
        root = bpy.data.objects.get(rig.label)
        if root is None:
            return dict()

        # -- Parents always come before their children, so loading can create
        # -- them in order
        objects = sorted(
            (
                obj for obj in root.children_recursive
                if obj.type in _STORED_TYPES and not _is_transient(obj, root)
            ),
            key=_depth,
        )

        return {
            "hierarchy": [_serialise_object(obj, root) for obj in objects],
        }

    # ----------------------------------------------------------------------------------
    def on_rig_load(self, rig, file_data: dict) -> None:
        """
        Recreates the Empties and armatures stored by on_rig_save, skipping
        any which already exist. aniseed calls this before adding the rig's
        components, so the bones exist by the time the components refer to
        them.
        """
        hierarchy = (file_data.get("additional_data") or {}).get("hierarchy") or []
        root = bpy.data.objects.get(rig.label)

        if root is None:
            return

        collection = root.users_collection[0] if root.users_collection else bpy.context.scene.collection

        for entry in hierarchy:
            if entry["name"] not in bpy.data.objects:
                _create_object(entry, root, collection)

    # ----------------------------------------------------------------------------------
    def control_shapes(self) -> list:
        """
        Returns the empty display types, which are the "shapes" a Blender
        control can take without any custom geometry.
        """
        return [item.identifier for item in bpy.types.Object.bl_rna.properties["empty_display_type"].enum_items]


# --------------------------------------------------------------------------------------
class BlenderAppWidget(aniseed.AppWidget):
    """
    The aniseed app widget, reporting events in its window's status bar.
    """

    def _notify(self, message: str):
        window = self.window()
        if isinstance(window, QtWidgets.QMainWindow):
            window.statusBar().showMessage(message, 4000)

    def notify_component_added(self, *args, **kwargs):
        self._notify(f"{args[0].label() if args else ''} Component Added")

    def notify_component_removed(self, *args, **kwargs):
        self._notify("Component Removed")

    def notify_build_started(self, *args, **kwargs):
        self._notify("Build Started")

    def notify_build_failed(self, component=None, details="", *args, **kwargs):
        self._notify(f"Build Failed{' : ' + component.label() if component else ''}")

    def notify_build_finished(self, successful=True, *args, **kwargs):
        if successful:
            self._notify("Build Finished")


# --------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class BlenderAppWindow(QtWidgets.QMainWindow):
    """
    The window holding the aniseed app in Blender. There is only ever one.
    """

    OBJECT_NAME = "AniseedBuilderWindow"

    _INSTANCE = None

    def __init__(self):
        super().__init__()
        BlenderAppWindow._INSTANCE = self

        self.setObjectName(self.OBJECT_NAME)
        self.setWindowTitle("Aniseed")
        self.setWindowIcon(QtGui.QIcon(aniseed.resources.get("icon.png")))
        self.resize(450, 850)

        qtility.styling.apply(
            [aniseed.resources.get("style.css")],
            apply_to=self,
            _ITEMHIGHLIGHT_=",".join(str(n) for n in aniseed.AppConfig.item_highlight_color),
        )

        self.app = BlenderAppWidget(
            app_config=aniseed.AppConfig,
            allow_threading=False,
            parent=self,
        )
        self.setCentralWidget(self.app)

    @classmethod
    def instance(cls):
        """
        Returns the open window, or None if there is not one (or Qt has
        already deleted it).
        """
        if cls._INSTANCE is not None and isValid(cls._INSTANCE):
            return cls._INSTANCE

        cls._INSTANCE = None
        return None

    @classmethod
    def refresh(cls):
        """
        Points the open window (if any) at the rigs in the current data.
        """
        window = cls.instance()
        if window:
            window.app.switch_rig()


# --------------------------------------------------------------------------------------
# -- Hierarchy helpers
# --------------------------------------------------------------------------------------
def _depth(obj) -> int:
    """
    Returns how many parents the object has.
    """
    depth = 0
    while obj.parent:
        depth += 1
        obj = obj.parent
    return depth


def _matrix(matrix_class, values):
    """
    Returns a 4x4 matrix from 16 row-major values, or the identity matrix if
    none are given.
    """
    if not values:
        return matrix_class.Identity(4)

    return matrix_class([values[index:index + 4] for index in range(0, 16, 4)])


# -- The object types on_rig_save stores
_STORED_TYPES = ("EMPTY", "ARMATURE")

# -- Objects with this custom property set are not stored with the recipe
TRANSIENT_KEY = "aniseed_transient"


def _is_transient(obj, root) -> bool:
    """
    Returns True if the object, or anything above it (up to the rig object),
    is flagged as transient.
    """
    while obj and obj != root:
        if obj.get(TRANSIENT_KEY):
            return True
        obj = obj.parent
    return False


def _flatten(matrix) -> list:
    return [value for row in matrix for value in row]


def _custom_properties(id_data) -> dict:
    """
    Returns the custom properties which are simple values (so can be stored
    as json).
    """
    return {
        key: id_data[key]
        for key in id_data.keys()
        if isinstance(id_data[key], (str, int, float, bool))
    }


def _serialise_object(obj, root) -> dict:
    """
    Returns what on_rig_save stores for an Empty or armature.
    """
    entry = {
        "name": obj.name,
        "type": obj.type,
        # -- None means "directly under the rig object", so the recipe can be
        # -- loaded into a rig with another name
        "parent": None if obj.parent == root else obj.parent.name,
        "parent_type": obj.parent_type,
        "parent_bone": obj.parent_bone,
        "matrix_basis": _flatten(obj.matrix_basis),
        "matrix_parent_inverse": _flatten(obj.matrix_parent_inverse),
        "show_in_front": obj.show_in_front,
        "custom_properties": _custom_properties(obj),
    }

    if obj.type == "EMPTY":
        entry["display_type"] = obj.empty_display_type
        entry["display_size"] = obj.empty_display_size

    elif obj.type == "ARMATURE":
        armature = obj.data
        entry["armature"] = {
            "display_type": armature.display_type,
            "collections": [collection.name for collection in armature.collections_all],
            # -- Parents before children. The Z axis is stored rather than the
            # -- roll, as a bone's roll is only available in edit mode.
            "bones": [
                {
                    "name": bone.name,
                    "head": list(bone.head_local),
                    "tail": list(bone.tail_local),
                    "z_axis": list(bone.matrix_local.col[2].xyz),
                    "parent": bone.parent.name if bone.parent else "",
                    "use_connect": bone.use_connect,
                    "use_deform": bone.use_deform,
                    "collections": [collection.name for collection in bone.collections],
                }
                for bone in sorted(armature.bones, key=_depth)
            ],
        }

    return entry


def _create_object(entry: dict, root, collection):
    """
    Creates an Empty or armature (with its bones) from an entry written by
    _serialise_object. Entries written before armatures were stored have no
    type, and are Empties.
    """
    from mathutils import Matrix

    object_type = entry.get("type", "EMPTY")

    if object_type == "ARMATURE":
        obj = bpy.data.objects.new(entry["name"], bpy.data.armatures.new(entry["name"]))
    else:
        obj = bpy.data.objects.new(entry["name"], None)
        obj.empty_display_type = entry.get("display_type", "PLAIN_AXES")
        obj.empty_display_size = entry.get("display_size", 1.0)

    collection.objects.link(obj)

    obj.parent = bpy.data.objects.get(entry["parent"]) if entry["parent"] else root
    if entry.get("parent_type") == "BONE" and entry.get("parent_bone"):
        obj.parent_type = "BONE"
        obj.parent_bone = entry["parent_bone"]

    obj.matrix_parent_inverse = _matrix(Matrix, entry.get("matrix_parent_inverse"))
    obj.matrix_basis = _matrix(Matrix, entry.get("matrix_basis"))
    obj.show_in_front = entry.get("show_in_front", False)

    for key, value in (entry.get("custom_properties") or {}).items():
        obj[key] = value

    if object_type == "ARMATURE":
        _create_bones(obj, entry.get("armature") or {})

    return obj


def _create_bones(obj, data: dict):
    """
    Creates the stored bones in a new armature. Bones can only be created in
    edit mode, which only works on the active object, so the armature is
    made active (and the only selected object) while they are created.
    """
    from mathutils import Vector

    armature = obj.data
    armature.display_type = data.get("display_type", "OCTAHEDRAL")

    for name in data.get("collections") or []:
        if not armature.collections_all.get(name):
            armature.collections.new(name)

    bones = data.get("bones") or []
    if not bones:
        return

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_selection = [each for each in view_layer.objects if each.select_get()]

    with bpy.context.temp_override(**_full_context()):
        if previous_active and previous_active.mode != "OBJECT":
            with bpy.context.temp_override(active_object=previous_active, object=previous_active):
                bpy.ops.object.mode_set(mode="OBJECT")

        for each in view_layer.objects:
            each.select_set(each == obj)
        view_layer.objects.active = obj

        with bpy.context.temp_override(active_object=obj, object=obj):
            bpy.ops.object.mode_set(mode="EDIT")

            for bone_data in bones:
                bone = armature.edit_bones.new(bone_data["name"])
                bone.head = Vector(bone_data["head"])
                bone.tail = Vector(bone_data["tail"])
                bone.align_roll(Vector(bone_data["z_axis"]))
                bone.use_deform = bone_data.get("use_deform", True)

                if bone_data.get("parent"):
                    bone.parent = armature.edit_bones[bone_data["parent"]]
                    bone.use_connect = bone_data.get("use_connect", False)

            bpy.ops.object.mode_set(mode="OBJECT")

        for each in view_layer.objects:
            each.select_set(each in previous_selection)
        view_layer.objects.active = previous_active

    for bone_data in bones:
        for name in bone_data.get("collections") or []:
            armature.collections_all[name].assign(armature.bones[bone_data["name"]])


# --------------------------------------------------------------------------------------
# -- Context
# --------------------------------------------------------------------------------------
def _full_context() -> dict:
    """
    Returns the keyword arguments for bpy.context.temp_override which give
    the main window, its screen, and its largest 3D viewport (with that
    viewport's main region). Anything which cannot be found is left out.
    """
    context = dict()

    # -- In background mode (blender -b) nothing is ever drawn. Blender may
    # -- still list a window, but its regions have never been set up, and
    # -- giving one to an operator such as transform.translate crashes
    # -- Blender 4.2. Operators work without them in the background.
    if bpy.app.background:
        return context

    window = bpy.context.window or (bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None)
    if window is None:
        return context

    context["window"] = window
    context["screen"] = window.screen

    areas = [area for area in window.screen.areas if area.type == "VIEW_3D"]
    if areas:
        area = max(areas, key=lambda each: each.width * each.height)
        context["area"] = area

        regions = [region for region in area.regions if region.type == "WINDOW"]
        if regions:
            context["region"] = regions[0]

    return context


def _push_undo(message: str):
    """
    Adds an undo step with the given name, so the changes made since the last
    step can be undone in one go.
    """
    try:
        with bpy.context.temp_override(**_full_context()):
            bpy.ops.ed.undo_push(message=message)

    except RuntimeError:
        log.debug(f"Could not push the undo step {message!r}", exc_info=True)


# --------------------------------------------------------------------------------------
# -- Scene and undo handlers
# --------------------------------------------------------------------------------------
@persistent
def _aniseed_flush_rigs(*args):
    """
    Writes any outstanding recipe changes into the data, while the rigs'
    references to it are still valid.
    """
    aniseed.Rig.flush_all()


@persistent
def _aniseed_release_rigs(*args):
    """
    Releases the shared rigs, as their references to Blender data are about
    to stop being valid (or already have).
    """
    aniseed.Rig.clear_registry()


@persistent
def _aniseed_release_and_refresh(*args):
    """
    Releases the shared rigs and points the app at the rigs in the new data.
    """
    aniseed.Rig.clear_registry()
    BlenderAppWindow.refresh()


# -- Each handler list, and the handlers aniseed adds to it, in order
_HANDLERS = {
    "save_pre": [_aniseed_flush_rigs],
    "load_pre": [_aniseed_release_rigs],
    "load_post": [_aniseed_release_and_refresh],
    # -- Flushing before an undo means a rig never has unwritten changes when
    # -- it is released afterwards, so releasing it never touches the data
    # -- the undo has just replaced
    "undo_pre": [_aniseed_flush_rigs],
    "undo_post": [_aniseed_release_and_refresh],
    "redo_pre": [_aniseed_flush_rigs],
    "redo_post": [_aniseed_release_and_refresh],
}


def _register_handlers():
    """
    Adds the handlers, first removing any added by an earlier load of this
    module (such as before a reload), which Blender would otherwise keep.
    """
    _unregister_handlers()

    for handler_name, functions in _HANDLERS.items():
        getattr(bpy.app.handlers, handler_name).extend(functions)


def _unregister_handlers():
    """
    Removes every aniseed handler, matching them by name so handlers from an
    earlier load of this module are removed too.
    """
    names = {function.__name__ for functions in _HANDLERS.values() for function in functions}

    for handler_name in _HANDLERS:
        handlers = getattr(bpy.app.handlers, handler_name)
        for function in list(handlers):
            if getattr(function, "__name__", "") in names:
                handlers.remove(function)


# --------------------------------------------------------------------------------------
# -- Menu
# --------------------------------------------------------------------------------------
class ANISEED_OT_launch(bpy.types.Operator):
    """Open the Aniseed rig builder"""
    bl_idname = "aniseed.launch"
    bl_label = "Aniseed Builder"

    def execute(self, context):
        aniseed.app.launch()
        return {"FINISHED"}


class ANISEED_OT_website(bpy.types.Operator):
    """Open the Aniseed website"""
    bl_idname = "aniseed.website"
    bl_label = "Website"

    def execute(self, context):
        webbrowser.open(aniseed.constants.website)
        return {"FINISHED"}


class ANISEED_OT_reload(bpy.types.Operator):
    """Reload aniseed, its components and its packages from disk"""
    bl_idname = "aniseed.reload"
    bl_label = "Reload"

    def execute(self, context):
        # -- Deferred, as reloading unregisters this operator's class
        bpy.app.timers.register(_reload, first_interval=0.0)
        return {"FINISHED"}


class ANISEED_OT_about(bpy.types.Operator):
    """Show the versions of aniseed and its packages"""
    bl_idname = "aniseed.about"
    bl_label = "About"

    def execute(self, context):
        lines = [f"aniseed : {aniseed.__version__}"]
        lines.extend(
            f"{package.name} : {package.version or 'No Version Data'}"
            for package in aniseed.packages.discover()
        )

        def draw(menu, _context):
            for line in lines:
                menu.layout.label(text=line)

        context.window_manager.popup_menu(draw, title="About Aniseed", icon="INFO")
        return {"FINISHED"}


class ANISEED_MT_menu(bpy.types.Menu):
    bl_idname = "ANISEED_MT_menu"
    bl_label = "Aniseed"

    def draw(self, context):
        layout = self.layout
        layout.operator(ANISEED_OT_launch.bl_idname, icon="ARMATURE_DATA")
        layout.separator()
        layout.operator(ANISEED_OT_website.bl_idname, icon="URL")
        layout.separator()
        layout.operator(ANISEED_OT_reload.bl_idname, icon="FILE_REFRESH")
        layout.separator()
        layout.operator(ANISEED_OT_about.bl_idname, icon="INFO")


_CLASSES = (
    ANISEED_OT_launch,
    ANISEED_OT_website,
    ANISEED_OT_reload,
    ANISEED_OT_about,
    ANISEED_MT_menu,
)


def _draw_top_bar_menu(self, context):
    self.layout.menu(ANISEED_MT_menu.bl_idname)


def _register_menu():
    """
    Registers the operators and adds the Aniseed menu to the top bar.
    """
    _unregister_menu()

    for class_ in _CLASSES:
        bpy.utils.register_class(class_)

    bpy.types.TOPBAR_MT_editor_menus.append(_draw_top_bar_menu)


def _unregister_menu():
    """
    Removes the Aniseed menu and its operators, including any registered by
    an earlier load of this module.
    """
    # -- Remove the draw function by name, as a reload gives a new function
    for draw in list(getattr(bpy.types.TOPBAR_MT_editor_menus.draw, "_draw_funcs", [])):
        if getattr(draw, "__name__", "") == _draw_top_bar_menu.__name__:
            bpy.types.TOPBAR_MT_editor_menus.remove(draw)

    for class_ in reversed(_CLASSES):
        registered = getattr(bpy.types, class_.__name__, None)
        if registered is not None:
            bpy.utils.unregister_class(registered)


def _reload():
    """
    Drops aniseed, its dependencies and every aniseed package, then imports
    aniseed again and re-initialises it, so changes on disk are picked up.
    """
    import blackout

    host = aniseed.host.get()
    host.environment_teardown()

    aniseed.Rig.clear_factory_cache()
    aniseed.Rig.clear_registry()

    package_names = [package.name for package in aniseed.packages.discover()]
    for module_name in CRITICAL_MODULES + package_names:
        blackout.drop(module_name)

    import aniseed as reloaded
    reloaded.environment.initialize()
    log.info("Aniseed reloaded")

    # -- Returning None stops the timer repeating
    return None
