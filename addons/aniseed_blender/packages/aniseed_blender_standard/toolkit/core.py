"""
The toolkit's tools, organisers and the stack holding them.

A toolkit (such as the Riggers Toolkit) is an xstack stack which the user
never edits. It is built from the tools: every Tool whose toolkit matches,
found in the tools folder of any active aniseed package, grouped beneath an
Organiser per category. Running a tool builds just that component.

Tools only have options, which are remembered (per toolkit) between sessions.

Right clicking a tool adds it to (or removes it from) the toolkit's
favourites. The Favourites organiser is always first, and shows the favourite
tools as well as their own organisers.
"""
import os
import sys
import logging
import contextlib

import bpy
import xstack
import aniseed
import scribble

log = logging.getLogger(__name__)

# -- The category a tool without any categories is shown under
GENERAL = "General"

# -- The organiser holding the favourite tools, which is always first
FAVOURITES = "Favourites"


# --------------------------------------------------------------------------------------
class Tool(xstack.Component):
    """
    A toolkit tool. Declare its options in __init__ and do its work in run(),
    which acts on the current Blender selection. Use is_valid to check the
    selection, logging why it cannot run.

    Tools only have options: declaring an input or an output raises.

    Tool modules must import this module (not the classes in it), as the
    factory finds every Tool in a tool module's namespace.
    """

    # -- The toolkit the tool shows in, such as "Riggers" or "Animators"
    toolkit = ""

    # -- The organisers the tool shows under. Without any it shows under General
    categories = []

    # ----------------------------------------------------------------------------------
    def declare_input(self, *args, **kwargs):
        raise TypeError(f"{self.identifier} : toolkit tools only have options, not inputs")

    # ----------------------------------------------------------------------------------
    def declare_output(self, *args, **kwargs):
        raise TypeError(f"{self.identifier} : toolkit tools only have options, not outputs")

    # ----------------------------------------------------------------------------------
    def user_functions(self) -> dict:
        """
        Offers adding the tool to the toolkit's favourites, or removing it if
        it is one. Subclasses adding their own actions should include these.
        """
        if not isinstance(self.stack, ToolkitStack):
            return dict()

        identifier = self.identifier
        stack = self.stack

        # -- Qt passes the action's checked state, which these ignore
        if stack.is_favourite(identifier):
            return {"Remove From Favourites": lambda *_: stack.remove_favourite(identifier)}

        return {"Add To Favourites": lambda *_: stack.add_favourite(identifier)}


# --------------------------------------------------------------------------------------
class Organiser(Tool):
    """
    Groups tools in a toolkit. Running it does nothing.
    """

    identifier = "Toolkit : Organiser"

    def user_functions(self) -> dict:
        return dict()

    # -- aniseed's own organiser icon
    icon = os.path.join(os.path.dirname(aniseed.__file__), "components", "agnostic", "organiser", "organiser.png")


# --------------------------------------------------------------------------------------
class ToolkitStack(xstack.Stack):
    """
    The stack behind a toolkit. Call populate to fill it with the toolkit's
    tools. It is never saved as a stack file.

    Args:
        toolkit: The name of the toolkit, matched against Tool.toolkit.
    """

    def __init__(self, toolkit: str):
        super().__init__(
            label=toolkit,
            component_paths=aniseed.packages.tool_paths(),
            component_base_class=Tool,
        )
        self.toolkit = toolkit
        self.component_library.register(Organiser)

        # -- Set while one copy of a tool passes its option values to the
        # -- others (such as its copy under Favourites)
        self._syncing = False

    # ----------------------------------------------------------------------------------
    def settings_id(self) -> str:
        return f"aniseed_{self.toolkit.lower()}_toolkit_options"

    # ----------------------------------------------------------------------------------
    def favourites_settings_id(self) -> str:
        return f"aniseed_{self.toolkit.lower()}_toolkit_favourites"

    # ----------------------------------------------------------------------------------
    def tools(self) -> list:
        """
        Returns the tool classes in this toolkit, sorted by identifier.
        """
        return sorted(
            (
                tool for tool in self.component_library.plugins()
                if tool is not Organiser and tool.toolkit == self.toolkit
            ),
            key=lambda tool: tool.identifier,
        )

    # ----------------------------------------------------------------------------------
    def populate(self) -> None:
        """
        Fills the stack with the Favourites organiser, then an organiser per
        category (alphabetically, with General last) holding the toolkit's
        tools in that category, and applies the option values remembered
        from earlier sessions.
        """
        for component in list(self.root_components):
            self.remove_component(component)

        tools = self.tools()
        categories = sorted({category for tool in tools for category in (tool.categories or [GENERAL])})
        if GENERAL in categories:
            categories.remove(GENERAL)
            categories.append(GENERAL)

        favourites = self.add_component(Organiser.identifier, FAVOURITES)
        for tool in tools:
            if self.is_favourite(tool.identifier):
                self._add_tool(tool.identifier, favourites)

        for category in categories:
            organiser = self.add_component(Organiser.identifier, category)

            for tool in tools:
                if category in (tool.categories or [GENERAL]):
                    self._add_tool(tool.identifier, organiser)

    # ----------------------------------------------------------------------------------
    def _add_tool(self, identifier: str, organiser, child_index=None):
        """
        Adds the tool beneath the organiser, with its remembered option values,
        and remembers any changes to them.
        """
        component = self.add_component(identifier, identifier, parent=organiser, child_index=child_index)
        if component is None:
            return None

        remembered = scribble.get(self.settings_id()).get(identifier) or {}
        for name, value in remembered.items():
            option = component.option(name)
            if option is not None:
                option.set(value)

        for option in component.options():
            option.value_changed.connect(lambda component=component: self._remember(component))

        return component

    # ----------------------------------------------------------------------------------
    def _remember(self, component) -> None:
        """
        Stores the tool's option values, so they are restored next time, and
        gives them to the tool's other copies (such as under Favourites).
        """
        if self._syncing:
            return

        values = {option.name(): option.get(resolved=False) for option in component.options()}

        settings = scribble.get(self.settings_id())
        settings[component.identifier] = values
        settings.save()

        self._syncing = True
        try:
            for other in self.components():
                if other is component or other.identifier != component.identifier:
                    continue

                for name, value in values.items():
                    if other.option(name).get(resolved=False) != value:
                        other.option(name).set(value)

        finally:
            self._syncing = False

    # ----------------------------------------------------------------------------------
    def favourites(self) -> list:
        """
        Returns the identifiers of the favourite tools.
        """
        return list(scribble.get(self.favourites_settings_id()).get("tools") or [])

    # ----------------------------------------------------------------------------------
    def is_favourite(self, identifier: str) -> bool:
        return identifier in self.favourites()

    # ----------------------------------------------------------------------------------
    def favourites_organiser(self):
        return next(
            (
                component for component in self.root_components
                if isinstance(component, Organiser) and component.label() == FAVOURITES
            ),
            None,
        )

    # ----------------------------------------------------------------------------------
    def add_favourite(self, identifier: str) -> None:
        """
        Makes the tool a favourite, adding it beneath the Favourites organiser
        (in alphabetical order).
        """
        if self.is_favourite(identifier):
            return

        self._store_favourites(self.favourites() + [identifier])

        organiser = self.favourites_organiser()
        if organiser is None:
            return

        index = len([child for child in organiser.children if child.identifier < identifier])
        self._add_tool(identifier, organiser, child_index=index)

    # ----------------------------------------------------------------------------------
    def remove_favourite(self, identifier: str) -> None:
        """
        Stops the tool being a favourite, removing it from beneath the
        Favourites organiser. It stays under its own organisers.
        """
        self._store_favourites([each for each in self.favourites() if each != identifier])

        organiser = self.favourites_organiser()
        if organiser is None:
            return

        for child in list(organiser.children):
            if child.identifier == identifier:
                self.remove_component(child)

    # ----------------------------------------------------------------------------------
    def _store_favourites(self, identifiers: list) -> None:
        settings = scribble.get(self.favourites_settings_id())
        settings["tools"] = identifiers
        settings.save()

    # ----------------------------------------------------------------------------------
    def build(self, *args, **kwargs) -> bool:
        """
        Builds as xstack does, with a full Blender context and as one undo
        step named after the tool being run.
        """
        if self.is_building():
            return super().build(*args, **kwargs)

        target = kwargs.get("build_only") or kwargs.get("build_below") or kwargs.get("build_up_to")
        label = f"{self.toolkit} Toolkit : {target.label() if target else 'All'}"
        host = _host_module()
        host.push_undo(f"Before {label}")

        with _context(host):
            result = super().build(*args, **kwargs)

        host.push_undo(label)
        return result


# --------------------------------------------------------------------------------------
def _host_module():
    """
    Returns the module the Blender host is defined in, which gives the full
    context and undo helpers rig builds use.
    """
    return sys.modules[type(aniseed.host.get()).__module__]


@contextlib.contextmanager
def _context(host):
    with bpy.context.temp_override(**host.full_context()):
        yield
