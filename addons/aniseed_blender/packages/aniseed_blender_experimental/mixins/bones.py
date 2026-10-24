"""
CreateBonesMixin gives a component the deform (DEF) bones it builds from: it
creates them in default proportions when the component is added (if its bone
inputs are empty), and adds "Create Bones", "Select Bones" and "Delete Bones"
to the component's menu.

A component using it provides:

    bone_input_names        The inputs holding DEF bone names, in order. An
                            input holds one name, a list of names, or a list
                            of lists of names.
    bone_layout()           A list of BoneSpec describing the bones to create,
                            for a left (or middle) side component. Right side
                            components get the layout mirrored.
    layout_anchor()         Where the layout expects its parent bone's tail to
                            be (the layout is moved so that point sits on the
                            actual parent bone's tail). None to never move it.
    deform_armature()       The armature object to create the bones in.

and may re-implement:

    fallback_parent_bone()  The DEF bone the new bones are parented to when
                            no DEF bone is selected.
    create_extras(names)    Called once the bones exist, to create anything
                            else, such as guide Empties. names maps each
                            BoneSpec key to the created bone.
    extra_objects()         Objects (by name) Delete Bones also removes.

The new bones are parented to the selected DEF bone (the active bone of the
deform armature, if it is selected), or, if there is none, to
fallback_parent_bone().
"""
import typing
import logging

import bpy
from mathutils import Vector

from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import mirroring
from aniseed_blender_experimental.lib.context import action_context, full_context

log = logging.getLogger(__name__)


class BoneSpec:
    """
    Describes one bone to create.

    Args:
        key: A name for the bone within the layout, used to refer to it as a
            parent and in create_extras.
        input_name: The input the bone's name is written to.
        path: Where in the input the name goes: () for an input holding one
            name, (index,) for a list, (index, index) for a list of lists.
        description: The description used in the bone's name.
        head: Where the bone starts, for a component of Size 1 on the left.
        tail: Where the bone ends.
        z_axis: The direction its Z axis points.
        parent: The key of the parent bone in the layout, or None for the
            bone the component's bones are created beneath.
        connect: Whether the head is locked to the parent's tail.
    """

    def __init__(self, key, input_name, path, description, head, tail, z_axis=(0, 0, 1), parent=None, connect=False):
        self.key = key
        self.input_name = input_name
        self.path = tuple(path)
        self.description = description
        self.head = Vector(head)
        self.tail = Vector(tail)
        self.z_axis = Vector(z_axis)
        self.parent = parent
        self.connect = connect


class CreateBonesMixin:

    bone_input_names: typing.List[str] = []

    # ----------------------------------------------------------------------------------
    # xstack integration
    # ----------------------------------------------------------------------------------
    def mixin_functions(self):
        return {
            "Create Bones": self.create_bones,
            "Select Bones": self.select_bones,
            "Delete Bones": self.delete_bones,
        }

    # ----------------------------------------------------------------------------------
    # Declarative surface
    # ----------------------------------------------------------------------------------
    def bone_layout(self) -> typing.List[BoneSpec]:
        return []

    def layout_anchor(self) -> typing.Optional[Vector]:
        return None

    def fallback_parent_bone(self) -> str:
        return ""

    def create_extras(self, names: typing.Dict[str, str]) -> None:
        return None

    def extra_objects(self) -> typing.List[str]:
        return []

    # ----------------------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------------------
    def bones(self) -> typing.List[str]:
        """
        Returns every DEF bone named in the bone inputs, in order.
        """
        result = []
        for input_name in self.bone_input_names:
            result.extend(_flatten(self.input(input_name).get()))
        return result

    def has_bone_values(self) -> bool:
        """
        True if any of the bone inputs has a value.
        """
        return any(self.input(input_name).get(resolved=False) for input_name in self.bone_input_names)

    def create_bones(self) -> typing.Dict[str, str]:
        """
        Creates the component's DEF bones in default proportions, parented to
        the selected DEF bone (or fallback_parent_bone()), and writes their
        names to the bone inputs.

        Returns:
            The created bone for each BoneSpec key.
        """
        # -- Read before the action changes the mode or selection
        parent_bone = self.creation_parent_bone()

        with action_context(f"Create Bones : {self.label()}", rig=self.rig):
            return self._create_bones(parent_bone)

    def creation_parent_bone(self) -> str:
        """
        Returns the DEF bone new bones are parented to: the selected bone of
        the deform armature, or, if nothing in it is selected,
        fallback_parent_bone().
        """
        deform = self.deform_armature()

        with bpy.context.temp_override(**full_context()):
            selected = armature_lib.selected_bone(deform)

        return selected or self.fallback_parent_bone()

    def select_bones(self) -> None:
        """
        Enters edit mode on the deform armature with this component's bones
        selected, so the user can fit them.
        """
        # -- Not an action_context, as that would put the user's selection and
        # -- mode back afterwards, which is the opposite of what is wanted
        deform = self.deform_armature()
        names = set(self.bones())

        with bpy.context.temp_override(**full_context()):
            view_layer = bpy.context.view_layer
            current = view_layer.objects.active

            if current and current.mode != "OBJECT":
                with bpy.context.temp_override(active_object=current, object=current):
                    bpy.ops.object.mode_set(mode="OBJECT")

            deform.hide_set(False)
            for obj in view_layer.objects:
                obj.select_set(obj == deform)
            view_layer.objects.active = deform

            with bpy.context.temp_override(active_object=deform, object=deform):
                bpy.ops.object.mode_set(mode="EDIT")

            # -- Selected as edit bones, as Blender 5 no longer has selection
            # -- on bones outside edit mode
            for bone in deform.data.edit_bones:
                bone.select = bone.select_head = bone.select_tail = bone.name in names

    def delete_bones(self, confirm: bool = True) -> None:
        """
        Removes this component's DEF bones (and extra objects, such as guide
        Empties) and clears the bone inputs.
        """
        if confirm and not bpy.app.background:
            import qtility
            if not qtility.request.confirmation(
                title="Delete Bones",
                message=f"Delete the bones of {self.label()}?",
            ):
                return

        with action_context(f"Delete Bones : {self.label()}", rig=self.rig):
            for name in self.extra_objects():
                obj = bpy.data.objects.get(name) if name else None
                if obj is not None:
                    bpy.data.objects.remove(obj, do_unlink=True)

            deform = self.deform_armature()
            names = [name for name in self.bones() if name in deform.data.bones]

            if names:
                with armature_lib.edit_bones(deform) as edit_bones:
                    for name in names:
                        edit_bones.remove(edit_bones[name])

            for input_name in self.bone_input_names:
                current = self.input(input_name).get(resolved=False)
                self.input(input_name).set([] if isinstance(current, list) else "")

    # ----------------------------------------------------------------------------------
    # Implementation
    # ----------------------------------------------------------------------------------
    def _create_bones(self, parent_bone: str) -> typing.Dict[str, str]:
        deform = self.deform_armature()
        if deform is None:
            log.warning(f"{self.label()} : there is no deform armature to create bones in")
            return {}

        location = self.option("Location").get()
        mirrored = location == self.config.right
        size = self.option("Size").get() if self.option("Size") else 1.0

        if parent_bone and parent_bone not in deform.data.bones:
            log.warning(f"{self.label()} : the parent bone {parent_bone!r} does not exist, so the bones are unparented")
            parent_bone = ""

        # -- Move the layout so it attaches to the actual parent bone
        shift = Vector()
        anchor = self.layout_anchor()
        if anchor is not None and parent_bone:
            anchor = Vector(anchor) * size
            if mirrored:
                anchor = mirroring.mirror_point(anchor)
            shift = deform.data.bones[parent_bone].tail_local - anchor

        names = dict()
        values = dict()

        with armature_lib.edit_bones(deform) as edit_bones:
            for spec in self.bone_layout():
                head, tail, z_axis = spec.head * size, spec.tail * size, spec.z_axis

                if mirrored:
                    head, tail, z_axis = mirroring.mirror_bone(head, tail, z_axis)

                parent = names.get(spec.parent) if spec.parent else parent_bone

                names[spec.key] = armature_lib.new_bone(
                    edit_bones,
                    self.config.generate_name(self.config.joint, spec.description, location),
                    head + shift,
                    tail + shift,
                    z_axis=z_axis,
                    parent=parent or None,
                    connect=spec.connect,
                    deform=True,
                )

                _set_path(values, spec.input_name, spec.path, names[spec.key])

        for input_name, value in values.items():
            self.input(input_name).set(value)

        self.create_extras(names)

        log.info(f"{self.label()} : created {len(names)} bone(s) in {deform.name}")
        return names


def _set_path(values: dict, input_name: str, path: tuple, name: str) -> None:
    """
    Writes name into values[input_name] at the given path, growing lists as
    needed.
    """
    if not path:
        values[input_name] = name
        return

    container = values.setdefault(input_name, [])
    for depth, index in enumerate(path):
        while len(container) <= index:
            container.append([] if depth < len(path) - 1 else "")

        if depth == len(path) - 1:
            container[index] = name
        else:
            container = container[index]


def _flatten(value) -> typing.List[str]:
    """
    Returns the names in a value which is a name, a list of names, or a list
    of lists of names.
    """
    if not value:
        return []
    if isinstance(value, str):
        return [value]

    result = []
    for item in value:
        result.extend(_flatten(item))
    return result
