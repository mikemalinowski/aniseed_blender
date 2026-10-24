"""
The control shape library. Blender draws a control bone with a "custom shape"
object, so each shape in shapes.json is built (once per rig) as a mesh object
of loose edges, kept in a hidden collection.

The shapes come from the Maya aniseed_toolkit library (see
scripts/convert_maya_shapes.py), so both hosts share shape names. A shape is
drawn in the bone's space, where Y runs along the bone, and is scaled by the
bone's length.
"""
import os
import json

import bpy

# -- Custom properties identifying a widget object, so a snapshot can tell
# -- which shape a control uses
SHAPE_KEY = "aniseed_shape"
RIG_KEY = "aniseed_widget_rig"

_LIBRARY = None


def library() -> dict:
    """
    Returns the shape library: {shape name: {"verts": [...], "edges": [...]}}.
    """
    global _LIBRARY

    if _LIBRARY is None:
        with open(os.path.join(os.path.dirname(__file__), "shapes.json"), "r") as handle:
            _LIBRARY = json.load(handle)

    return _LIBRARY


def collection_name(rig_label: str) -> str:
    return f"{rig_label}_Widgets"


def widget_collection(rig_label: str, create: bool = True):
    """
    Returns the rig's (hidden) widget collection, creating it beneath the rig
    object's collection if needed.
    """
    name = collection_name(rig_label)
    collection = bpy.data.collections.get(name)

    if collection is None and create:
        collection = bpy.data.collections.new(name)
        collection.hide_viewport = True
        collection.hide_render = True

        root = bpy.data.objects.get(rig_label)
        parent = root.users_collection[0] if root and root.users_collection else bpy.context.scene.collection
        parent.children.link(collection)

    return collection


def widget(rig_label: str, shape: str, name: str):
    """
    Returns the rig's widget object for the shape, creating it if needed.

    Args:
        rig_label: The rig the widget belongs to.
        shape: The shape's name in the library.
        name: The name to give the object if it has to be created.

    Raises:
        KeyError: If the shape is not in the library.
    """
    collection = widget_collection(rig_label)

    for obj in collection.objects:
        if obj.get(SHAPE_KEY) == shape:
            return obj

    data = library()[shape]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(vertex) for vertex in data["verts"]], [tuple(edge) for edge in data["edges"]], [])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj[SHAPE_KEY] = shape
    obj[RIG_KEY] = rig_label
    collection.objects.link(obj)

    return obj


def shape_of(widget_object) -> str:
    """
    Returns the library name of a widget object, or an empty string if it is
    not one of the library's widgets.
    """
    if widget_object is None:
        return ""
    return widget_object.get(SHAPE_KEY, "")


def remove_widgets(rig_label: str) -> None:
    """
    Removes the rig's widget collection, its objects and their meshes.
    """
    collection = widget_collection(rig_label, create=False)
    if collection is None:
        return

    for obj in list(collection.objects):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and not mesh.users:
            bpy.data.meshes.remove(mesh)

    bpy.data.collections.remove(collection)
