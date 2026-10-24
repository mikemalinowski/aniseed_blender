"""
The Aniseed add-on for Blender. Everything aniseed needs is bundled inside
this folder, so it works as soon as it is installed:

    vendor/     aniseed, and the modules it depends on (xstack, crosswalk,
                qtility, factories, signalling, scribble) plus qshake, which
                runs Qt inside Blender
    packages/   the aniseed packages for Blender: aniseed_blender_standard
                (the Blender host) and aniseed_blender_experimental
                (rigging components)

The one thing not bundled is PySide6, as it is large and specific to each
Blender version. The first time the add-on is enabled, the Aniseed menu (and
the add-on's preferences) offer to install it, which downloads the right
build for the running Blender with qshake.install_pyside(). Aniseed then
starts straight away, without restarting Blender.
"""
bl_info = {
    "name": "Aniseed",
    "description": "Modular rigging framework",
    "author": "Michael Malinowski",
    "version": (0, 2, 0),
    "blender": (4, 2, 0),
    "location": "Top bar > Aniseed",
    "doc_url": "https://github.com/mikemalinowski/aniseed",
    "support": "COMMUNITY",
    "category": "Rigging",
}

import os
import sys
import logging

import bpy

log = logging.getLogger(__name__)

# -- realpath, so the add-on finds its own folders when it is linked into
# -- Blender's add-ons folder rather than copied there
HERE = os.path.dirname(os.path.realpath(__file__))

VENDOR = os.path.join(HERE, "vendor")
PACKAGES = os.path.join(HERE, "packages")

# -- The environment variable aniseed reads extra package locations from
PACKAGE_PATHS_ENVVAR = "ANISEED_PACKAGE_PATHS"


class PySideNotInstalled(RuntimeError):
    """
    Raised by initialise when PySide6 has not been installed yet.
    """


# --------------------------------------------------------------------------------------
# -- Public functions, also used to run aniseed in background Blender
# --------------------------------------------------------------------------------------
def setup_paths():
    """
    Makes the bundled modules importable, and tells aniseed where the bundled
    packages are. Must run before aniseed is imported, as aniseed finds its
    packages when it is first imported.
    """
    # -- At the front, so the bundled modules are used even if another copy of
    # -- aniseed (or one of its dependencies) is also on the path
    if VENDOR not in sys.path:
        sys.path.insert(0, VENDOR)

    package_paths = [path for path in os.environ.get(PACKAGE_PATHS_ENVVAR, "").split(";") if path]
    if PACKAGES not in package_paths:
        package_paths.append(PACKAGES)
    os.environ[PACKAGE_PATHS_ENVVAR] = ";".join(package_paths)


def pyside_installed() -> bool:
    """
    Returns True if qshake has a PySide6 build for this Blender, and is ready.
    """
    setup_paths()
    import qshake

    try:
        # -- Creates (or returns) the QApplication, and raises if there is no
        # -- PySide6 build for this Blender
        qshake.application()
        return True

    except RuntimeError:
        return False


def install_pyside() -> bool:
    """
    Downloads PySide6 for this Blender into the bundled qshake. Blender is
    unresponsive while it downloads (usually under a minute); pip's progress
    is shown in the system console.

    Returns:
        True once qshake is ready to use.
    """
    setup_paths()
    import qshake

    return qshake.install_pyside()


def initialise():
    """
    Imports aniseed and starts its Blender host, which adds the Aniseed menu.

    Raises:
        PySideNotInstalled: If PySide6 has not been installed yet. Call
            install_pyside first.
    """
    # -- qshake must be ready before aniseed is imported. It puts PySide6 (and
    # -- its bundled Qt.py, which aniseed imports) on the path.
    if not pyside_installed():
        raise PySideNotInstalled(
            "PySide6 is not installed for this Blender. Use Aniseed > Install PySide6, "
            "or call aniseed_blender.install_pyside()."
        )

    import aniseed

    aniseed.environment.initialize()

    host = aniseed.host.get()
    if host.name != "blender":
        log.warning(f"Aniseed : expected the blender host, but got {host.name!r}")


# --------------------------------------------------------------------------------------
# -- First run: installing PySide6
# --------------------------------------------------------------------------------------
class ANISEED_OT_install_pyside(bpy.types.Operator):
    """Download PySide6 for this Blender, which Aniseed needs for its interface. Blender is unresponsive while it downloads"""
    bl_idname = "aniseed.install_pyside"
    bl_label = "Install PySide6"

    def execute(self, context):
        try:
            ready = install_pyside()

        except Exception as error:
            log.exception("Aniseed : PySide6 could not be installed")
            self.report({"ERROR"}, f"PySide6 could not be installed: {error}. See the system console.")
            return {"CANCELLED"}

        if not ready:
            self.report({"ERROR"}, "PySide6 was installed, but qshake could not start. See the system console.")
            return {"CANCELLED"}

        # -- Swap the setup menu for the real one
        _remove_setup_menu()
        _start()

        self.report({"INFO"}, "PySide6 is installed and Aniseed is ready. Open it from the Aniseed menu.")
        return {"FINISHED"}


class ANISEED_MT_setup(bpy.types.Menu):
    """
    The Aniseed menu shown until PySide6 has been installed.
    """
    bl_idname = "ANISEED_MT_setup"
    bl_label = "Aniseed"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Aniseed needs PySide6 for its interface.", icon="INFO")
        layout.operator(ANISEED_OT_install_pyside.bl_idname, icon="IMPORT")


class AniseedPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout

        if "aniseed" in sys.modules:
            import aniseed
            layout.label(text=f"Aniseed {aniseed.__version__} is ready. Open it from the Aniseed menu.", icon="CHECKMARK")

        else:
            layout.label(text="Aniseed needs PySide6 for its interface, which is downloaded once per Blender version.", icon="INFO")
            layout.operator(ANISEED_OT_install_pyside.bl_idname, icon="IMPORT")


def _draw_setup_menu(self, context):
    self.layout.menu(ANISEED_MT_setup.bl_idname)


def _add_setup_menu():
    bpy.types.TOPBAR_MT_editor_menus.append(_draw_setup_menu)


def _remove_setup_menu():
    # -- Only remove it if it was added (it is not when PySide6 was already
    # -- installed when the add-on was enabled)
    if _draw_setup_menu in getattr(bpy.types.TOPBAR_MT_editor_menus.draw, "_draw_funcs", []):
        bpy.types.TOPBAR_MT_editor_menus.remove(_draw_setup_menu)


def _start():
    """
    Starts aniseed, logging (rather than raising) any failure, so a problem
    never stops Blender from starting.
    """
    try:
        initialise()
        return True

    except Exception:
        log.exception("Aniseed failed to initialise")
        return False


# --------------------------------------------------------------------------------------
# -- Registration
# --------------------------------------------------------------------------------------
_CLASSES = (
    ANISEED_OT_install_pyside,
    ANISEED_MT_setup,
    AniseedPreferences,
)


def register():
    for class_ in _CLASSES:
        bpy.utils.register_class(class_)

    setup_paths()

    if pyside_installed():
        _start()

    else:
        log.warning("Aniseed : PySide6 is not installed yet. Use Aniseed > Install PySide6.")
        _add_setup_menu()


def unregister():
    _remove_setup_menu()

    aniseed = sys.modules.get("aniseed")
    if aniseed is not None:
        host = aniseed.host.get()
        if hasattr(host, "environment_teardown"):
            host.environment_teardown()

    for class_ in reversed(_CLASSES):
        bpy.utils.unregister_class(class_)
