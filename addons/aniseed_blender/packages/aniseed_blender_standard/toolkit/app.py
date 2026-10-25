"""
The toolkit window: an xstack app showing a ToolkitStack, set up so the user
can run tools and set their options, but cannot change the stack.

    * the structure is read only (no dragging, adding, removing or renaming)
    * double clicking a tool runs it, and double clicking an organiser
      expands or collapses it
    * the right click menu only offers running the tool itself, never a
      build of the whole stack (or of everything up to a tool), and adding
      it to (or removing it from) the favourites
    * a Run button beneath the options runs the selected tool

Each toolkit's config gives the window its own icon and stack background.
"""
import qtility
import xstack
import aniseed
from Qt import QtWidgets, QtGui

try:
    from shiboken6 import isValid

except ImportError:
    from shiboken2 import isValid

from xstack.app import tree
from xstack.app import delegate
from xstack.constants import Status

from . import core

# -- The open toolkit windows, by toolkit name
_WINDOWS = dict()


# --------------------------------------------------------------------------------------
class ToolkitDelegate(delegate.ComponentItemDelegate):
    """
    Draws a tool's name alone. The stack's default delegate follows it with
    the component type, which for a tool is its name again.
    """

    def paint_text(self, component, painter, option, index):
        painter.setFont(self.text_font)
        painter.setPen(self.text_pen)
        painter.drawText(
            option.rect.x() + self.item_size + self.bfr + self.STATUS_WIDTH + self.bfr,
            option.rect.y() + (25 * self.factor),
            component.label(),
        )


# --------------------------------------------------------------------------------------
class ToolkitTree(tree.BuildTreeWidget):
    """
    The toolkit's tree, where double clicking runs a tool.
    """

    def __init__(self, stack, app_config, app=None):
        super().__init__(stack, app_config, app=app)

        self._delegate = ToolkitDelegate(stack, app_config)
        self.setItemDelegateForColumn(0, self._delegate)

    # ----------------------------------------------------------------------------------
    def on_item_double_clicked(self, item, column):
        """
        Runs a tool, or expands/collapses an organiser.
        """
        if not self.allow_interaction:
            return

        component = getattr(item, "component", None)
        if component is None:
            return

        if isinstance(component, core.Organiser):
            item.setExpanded(not item.isExpanded())
            return

        self.app.build(build_only=component)


# --------------------------------------------------------------------------------------
class ToolkitConfig(aniseed.AppConfig):
    """
    The app configuration for a toolkit. Each toolkit subclasses it, giving
    its name (matched against Tool.toolkit) and label.
    """

    # -- The name of the toolkit
    toolkit = ""

    label = "Toolkit"
    component_label = "Tool"
    execute_label = "Run"

    show_menu_bar = False
    show_tree_header = False
    forced_orientation = "vertical"

    read_only_structure = True
    component_build_actions = ("only",)
    show_stack_build_actions = False
    tree_widget = ToolkitTree

    log_logger_names = aniseed.AppConfig.log_logger_names + [
        "aniseed_blender_standard",
        "aniseed_riggers_toolkit",
        "aniseed_animators_toolkit",
    ]

    settings_id = "aniseed_toolkit_settings"


# --------------------------------------------------------------------------------------
class ToolkitAppWidget(xstack.app.AppWidget):
    """
    The xstack app, with a Run button beneath the tool's options which runs
    the selected tool, reporting how each tool run went in the window's status
    bar.
    """

    def __init__(self, *args, **kwargs):
        self.run_button = None
        super().__init__(*args, **kwargs)

    # ----------------------------------------------------------------------------------
    def build_layout(self):
        super().build_layout()

        # -- Give the options a fair share of the window
        self.splitter.setSizes([550, 450])

        self.run_button = QtWidgets.QPushButton(self.app_config.execute_label)
        self.run_button.setMinimumHeight(30)
        self.run_button.clicked.connect(self.run_selected_tool)
        self.stack_layout().addWidget(self.run_button)

        self.tree_widget.currentItemChanged.connect(self.update_run_button)
        self.update_run_button()

    # ----------------------------------------------------------------------------------
    def selected_tool(self):
        """
        Returns the selected tool, or None if an organiser (or nothing) is
        selected.
        """
        component = self.tree_widget.current_component() if self.tree_widget else None

        if component is None or isinstance(component, core.Organiser):
            return None

        return component

    # ----------------------------------------------------------------------------------
    def update_run_button(self, *args, **kwargs):
        if self.run_button is not None:
            tool = self.selected_tool()
            self.run_button.setEnabled(tool is not None)
            self.run_button.setText(f"{self.app_config.execute_label} {tool.label()}" if tool else self.app_config.execute_label)

    # ----------------------------------------------------------------------------------
    def run_selected_tool(self):
        tool = self.selected_tool()
        if tool is not None:
            self.build(build_only=tool)

    # ----------------------------------------------------------------------------------
    def build(self, build_up_to=None, build_only=None, build_below=None, validate_only=False):
        super().build(
            build_up_to=build_up_to,
            build_only=build_only,
            build_below=build_below,
            validate_only=validate_only,
        )

        component = build_only or build_below or build_up_to
        window = self.window()

        if component is None or not isinstance(window, QtWidgets.QMainWindow):
            return

        status = component.status()

        if status == Status.Success:
            message = f"{component.label()} : done"

        elif status == Status.Invalid:
            message = f"{component.label()} : could not run (see the Log tab)"

        else:
            message = f"{component.label()} : failed (see the Log tab)"

        window.statusBar().showMessage(message, 6000)


# --------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class ToolkitWindow(QtWidgets.QMainWindow):
    """
    The window holding one toolkit. There is only ever one per toolkit.
    """

    def __init__(self, config):
        super().__init__()

        self.config = config

        self.setObjectName(f"Aniseed{config.toolkit}ToolkitWindow")
        self.setWindowTitle(config.label)
        self.setWindowIcon(QtGui.QIcon(config.icon))
        self.resize(380, 700)

        qtility.styling.apply(
            [aniseed.resources.get("style.css")],
            apply_to=self,
            _ITEMHIGHLIGHT_=",".join(str(n) for n in config.item_highlight_color),
        )

        self.stack = core.ToolkitStack(config.toolkit)
        self.stack.populate()

        self.app = ToolkitAppWidget(
            app_config=config,
            allow_threading=False,
            parent=self,
        )
        self.app.set_active_stack(self.stack)
        self.setCentralWidget(self.app)


# --------------------------------------------------------------------------------------
def window(toolkit: str):
    """
    Returns the open window of the given toolkit, or None.
    """
    existing = _WINDOWS.get(toolkit)

    if existing is not None and isValid(existing):
        return existing

    _WINDOWS.pop(toolkit, None)
    return None


def launch(config) -> ToolkitWindow:
    """
    Shows the window of the toolkit the config describes, reusing it if it is
    already open.
    """
    # -- See BlenderHost.launch: qshake runs Qt inside Blender, and parents
    # -- the window to Blender's
    import qshake

    toolkit_window = window(config.toolkit)

    if toolkit_window is None:
        toolkit_window = ToolkitWindow(config)
        _WINDOWS[config.toolkit] = toolkit_window

        # -- Start it centred over Blender's window, rather than on whichever
        # -- screen the mouse is on
        handle = qshake.main_window_handle()
        if handle:
            from PySide6.QtGui import QWindow

            blender = QWindow.fromWinId(handle).geometry()
            if blender.isValid():
                toolkit_window.move(blender.center() - toolkit_window.rect().center())

    qshake.show(toolkit_window)
    return toolkit_window


def close_all() -> None:
    """
    Closes every open toolkit window.
    """
    for toolkit in list(_WINDOWS):
        toolkit_window = window(toolkit)
        if toolkit_window is not None:
            toolkit_window.close()

    _WINDOWS.clear()
