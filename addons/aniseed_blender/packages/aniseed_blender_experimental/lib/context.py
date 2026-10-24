"""
Gives right click actions (such as Create Bones) what a build gets from the
Blender host: a full context and a single undo step.

Right click actions run from the Qt timer which pumps the aniseed window,
where Blender provides almost no context (no window or area), so operators
such as mode_set fail. The host's build_context solves this for builds; this
does the same for actions, without touching the host.
"""
import logging
import contextlib

import bpy

log = logging.getLogger(__name__)

# -- How many action_context calls are currently open, so nested calls (such as
# -- Mirror creating bones) only set things up once
_DEPTH = 0


@contextlib.contextmanager
def action_context(label: str, rig=None):
    """
    Runs the body with a full Blender context, as one undo step, and puts the
    user's mode, active object and selection back afterwards.

    Does nothing extra when nested inside another action_context, or when the
    rig is building (the host's build_context already provides all of this).

    Args:
        label: The name of the undo step.
        rig: The rig the action belongs to, if any.
    """
    global _DEPTH

    if _DEPTH or (rig is not None and rig.is_building()):
        yield
        return

    _DEPTH += 1

    view_layer = bpy.context.view_layer
    active = view_layer.objects.active
    active_name = active.name if active else None
    active_mode = active.mode if active else "OBJECT"
    selected_names = [obj.name for obj in view_layer.objects if obj.select_get()]

    _push_undo(f"Before {label}")

    try:
        with bpy.context.temp_override(**full_context()):
            try:
                yield

            finally:
                _restore(view_layer, active_name, active_mode, selected_names)

    finally:
        _DEPTH -= 1

    # -- aniseed writes the recipe a moment after a change. Write it now, so
    # -- the undo step holds the stack as it is after the action (such as a
    # -- newly added component) alongside the scene changes the action made.
    if rig is not None:
        rig.serialise()

    _push_undo(label)


def full_context() -> dict:
    """
    Returns the keyword arguments for bpy.context.temp_override which give the
    main window, its screen, and its largest 3D viewport (with that viewport's
    main region). Anything which cannot be found is left out.

    In background mode nothing is returned, as giving a never-drawn region to
    some operators crashes Blender, and operators work without one there.
    """
    context = dict()

    if bpy.app.background:
        return context

    window_manager = bpy.context.window_manager
    window = bpy.context.window or (window_manager.windows[0] if window_manager.windows else None)
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


def _restore(view_layer, active_name, active_mode, selected_names):
    """
    Returns to object mode, then restores the selection, the active object and
    (if it still exists) the mode it was in.
    """
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    for obj in view_layer.objects:
        obj.select_set(obj.name in selected_names)

    active = view_layer.objects.get(active_name) if active_name else None
    view_layer.objects.active = active

    if active and active_mode != "OBJECT":
        try:
            with bpy.context.temp_override(active_object=active, object=active):
                bpy.ops.object.mode_set(mode=active_mode)

        except RuntimeError:
            log.debug(f"Could not return {active_name} to {active_mode} mode", exc_info=True)


def _push_undo(message: str):
    """
    Adds an undo step with the given name.
    """
    try:
        with bpy.context.temp_override(**full_context()):
            bpy.ops.ed.undo_push(message=message)

    except RuntimeError:
        log.debug(f"Could not push the undo step {message!r}", exc_info=True)
