"""
MirrorMixin adds a "Mirror" action to a RigComponent, which duplicates the
component (and all of its children) onto the other side, along with its deform
bones. It is the Blender counterpart of aniseed_maya_standard's MirrorMixin,
and its component side (planning the subtree, copying data, search and
replace, re-pointing addresses, swapping Location, the hooks) is the same.

The component is expected to have a "Location" option. Only the config's
left and right are mirrorable.

Mirroring happens in this order:

    1. Plan: the subtree is gathered (parents first), each component's bones
       are recorded, and the label of every mirrored component is worked out.
    2. For each component, parent before child: the mirrored component is
       added with its data copied, search-and-replaced, its addresses
       re-pointed at the other mirrored components and its Location swapped.
       Its bones are then mirrored: if the other side already has bones of
       its own (with the mirrored names, which no other component uses),
       they are used as they are. Otherwise the bones are created by
       reflecting the original bones across X. Then its on_enter_stack runs,
       which does not create bones, as its bone inputs are already filled.

A mirrorable component (which also uses CreateBonesMixin) may re-implement:

    mirror_mixin_prepare(mirrored_from)       Called on the mirrored component
                                              after its data is wrangled and
                                              before its bones are mirrored.
    mirror_mixin_mirror_extras(mirrored_from, bone_map)
                                              Mirrors anything other than the
                                              bones, such as guide Empties.
                                              bone_map maps each original bone
                                              to the bone it became.
    mirror_mixin_post_mirror(mirrored_from)   Called once the whole subtree is
                                              mirrored.
    can_mirror()                              To add further preconditions.
"""
import re
import logging

from xstack import address

from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import mirroring
from aniseed_blender_experimental.lib.context import action_context

log = logging.getLogger(__name__)


class MirrorMixin:

    # -- Scribble key used to remember the last-used search:replace expression
    # -- for each direction of mirroring
    _SCRIBBLE_KEY = "aniseed_blender_mirror_expression"

    # -- Appended to a mirrored component's label when the search and replace
    # -- does not give it a label of its own
    _MIRRORED_LABEL_SUFFIX = " (Mirrored)"

    # ----------------------------------------------------------------------------------
    # xstack integration
    # ----------------------------------------------------------------------------------
    def mixin_functions(self):
        if self.can_mirror():
            return {"Mirror": self._invoke_mirror_from_ui}
        return {}

    # ----------------------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------------------
    def can_mirror(self) -> bool:
        """
        True when the component's Location is the config's left or right.
        """
        location_option = self.option("Location")
        if location_option is None:
            return False
        return location_option.get() in (self.config.left, self.config.right)

    def mirror(self, search_for: str = None, replace_with: str = None):
        """
        Duplicates this component and its children onto the other side, with
        mirrored bones.

        Args:
            search_for: Regex applied to the mirrored components' labels,
                inputs and options. Defaults to the location as a whole token
                (so "L" matches "DEF_Hand_01_L" and "Arm L", but not "Leg").
            replace_with: The replacement. Defaults to the other location.

        Returns:
            The mirrored version of this component, or None if this component
            is not on a mirrorable side.
        """
        target_location = self._mirror_target_location()
        if not target_location or not self.can_mirror():
            return None

        default_search, default_replace = self._default_mirror_expression()
        search_for = default_search if search_for is None else search_for
        replace_with = default_replace if replace_with is None else replace_with

        with action_context(f"Mirror : {self.label()}", rig=self.rig):
            return self._mirror_subtree(
                expression=re.compile(search_for),
                replace_with=replace_with,
                original_location=self.option("Location").get(),
                target_location=target_location,
            )

    # ----------------------------------------------------------------------------------
    # Hooks
    # ----------------------------------------------------------------------------------
    def mirror_mixin_prepare(self, mirrored_from) -> None:
        return None

    def mirror_mixin_mirror_extras(self, mirrored_from, bone_map: dict) -> None:
        return None

    def mirror_mixin_post_mirror(self, mirrored_from) -> None:
        return None

    # ----------------------------------------------------------------------------------
    # Helpers for use from the hooks, during a mirror
    # ----------------------------------------------------------------------------------
    def mirror_mixin_mirrored_name(self, name: str) -> str:
        """
        Returns the name with the mirror's search and replace applied.
        """
        context = getattr(self, "_mirror_context", None)
        if not context or not name:
            return name
        return context["expression"].sub(context["replace_with"], name)

    def mirror_mixin_counterparts_exist(self, original_bones: list) -> bool:
        """
        True when every original bone has a counterpart (its mirrored name)
        in the deform armature which differs from it and which no other
        component uses - so the user built the other side themselves.
        """
        deform = self.deform_armature()
        original_bones = [bone for bone in original_bones if bone]

        if not original_bones or deform is None:
            return False

        mirrored = [self.mirror_mixin_mirrored_name(bone) for bone in original_bones]

        for original, counterpart in zip(original_bones, mirrored):
            if counterpart == original or counterpart not in deform.data.bones:
                return False

        claimed = set(mirrored)
        for other in self.stack.components():
            if other is self or not hasattr(other, "bones"):
                continue
            if claimed & set(other.bones()):
                return False

        return True

    # ----------------------------------------------------------------------------------
    # UI entry point
    # ----------------------------------------------------------------------------------
    def _invoke_mirror_from_ui(self):
        """
        Asks for the search:replace expression, then mirrors.
        """
        import qtility
        import scribble

        original_location = self.option("Location").get()
        target_location = self._mirror_target_location()
        if not target_location:
            return None

        default_expression = ":".join(self._default_mirror_expression())

        # -- Remember the last expression for each direction separately
        user_data = scribble.get(self._SCRIBBLE_KEY)
        direction_key = f"{original_location}:{target_location}"
        prior = user_data.get(direction_key, default_expression)

        response = qtility.request.text(
            title="Mirror Component",
            message=(
                "Enter a search-and-replace expression to apply to the "
                "mirrored component's data.\n\n"
                "Format: search:replace  (the search is treated as a regex)\n\n"
                f"Default swaps the location token: \"{default_expression}\""
            ),
            text=prior,
        )

        if not response:
            return None

        if ":" not in response:
            qtility.request.message(title="Mirror Component", message="Could not parse the search:replace expression.")
            return None

        search_for, replace_with = response.split(":", 1)

        try:
            re.compile(search_for)
        except re.error as error:
            qtility.request.message(title="Mirror Component", message=f"The search is not a valid regular expression: {error}")
            return None

        user_data[direction_key] = response
        user_data.save()

        return self.mirror(search_for=search_for, replace_with=replace_with)

    # ----------------------------------------------------------------------------------
    # Implementation
    # ----------------------------------------------------------------------------------
    def _mirror_target_location(self) -> str:
        location_option = self.option("Location")
        if location_option is None:
            return ""

        location = location_option.get()
        if location == self.config.left:
            return self.config.right
        if location == self.config.right:
            return self.config.left
        return ""

    def _default_mirror_expression(self) -> tuple:
        """
        Returns the default (search, replace) pair: the location as a whole
        token (not touching any other letter or digit) and the other location.
        """
        original_location = self.option("Location").get()
        search_for = rf"(?<![A-Za-z0-9]){re.escape(original_location)}(?![A-Za-z0-9])"
        return search_for, self._mirror_target_location()

    def _mirror_subtree(self, expression, replace_with, original_location, target_location):
        stack = self.stack

        # -- 1. Plan
        originals = self._subtree(self)
        mirrored_labels = self._plan_mirrored_labels(originals, expression, replace_with)

        label_map = dict()
        for original in originals:
            label_map[original.label()] = mirrored_labels[original]
            label_map[expression.sub(replace_with, original.label())] = mirrored_labels[original]

        # -- 2. Create the mirrored components, parent before child
        mirrored_components = dict()
        bone_map = dict()

        for original in originals:
            mirrored = stack.add_component(
                component_type=original.identifier,
                label=mirrored_labels[original],
                suppress_events=True,
            )

            mirrored.copy(original)
            mirrored.search_and_replace(search_for=expression.pattern, replace_with=replace_with)
            mirrored.set_label(mirrored_labels[original])

            self._retarget_addresses(mirrored, label_map)

            location_option = mirrored.option("Location")
            if location_option is not None and location_option.get(resolved=False) == original_location:
                location_option.set(target_location)

            if isinstance(mirrored, MirrorMixin):
                mirrored._mirror_context = dict(expression=expression, replace_with=replace_with)
                mirrored.mirror_mixin_prepare(original)
                mirrored._mirror_bones_from(original, bone_map)
                mirrored.mirror_mixin_mirror_extras(original, bone_map)

            mirrored.set_parent(parent=mirrored_components.get(original.parent, original.parent))
            mirrored.on_enter_stack()

            stack.component_added.emit(mirrored)
            stack.changed.emit()

            mirrored_components[original] = mirrored

        for original in originals:
            mirrored = mirrored_components[original]
            if isinstance(mirrored, MirrorMixin):
                mirrored.mirror_mixin_post_mirror(original)

        for mirrored in mirrored_components.values():
            if hasattr(mirrored, "_mirror_context"):
                del mirrored._mirror_context

        return mirrored_components[self]

    def _mirror_bones_from(self, original, bone_map: dict) -> None:
        """
        Gives this (mirrored) component bones of its own: the counterparts if
        the user already built the other side, otherwise new bones reflected
        from the original's. Updates bone_map with what each original bone
        became, and writes the bones into this component's inputs.
        """
        deform = self.deform_armature()
        original_bones = [bone for bone in original.bones() if bone in deform.data.bones]

        if not original_bones:
            return

        if self.mirror_mixin_counterparts_exist(original_bones):
            for bone in original_bones:
                bone_map[bone] = self.mirror_mixin_mirrored_name(bone)

        else:
            # -- Create parents before children
            ordered = sorted(original_bones, key=lambda name: _depth(deform.data.bones[name]))
            rest = {name: armature_lib.rest_data(deform, name) for name in ordered}
            flags = {name: (deform.data.bones[name].use_connect, deform.data.bones[name].use_deform) for name in ordered}
            location = self.option("Location").get()

            with armature_lib.edit_bones(deform) as edit_bones:
                for name in ordered:
                    data = rest[name]
                    head, tail, z_axis = mirroring.mirror_bone(data["head"], data["tail"], data["z_axis"])

                    new_name = self.mirror_mixin_mirrored_name(name)
                    if new_name == name or new_name in edit_bones:
                        description = self._description_of(name)
                        new_name = self.config.generate_name(self.config.joint, description, location)

                    parent = data["parent"]
                    parent = bone_map.get(parent) or self._mirrored_existing(parent, edit_bones)

                    bone_map[name] = armature_lib.new_bone(
                        edit_bones,
                        new_name,
                        head,
                        tail,
                        z_axis=z_axis,
                        parent=parent or None,
                        connect=flags[name][0],
                        deform=flags[name][1],
                    )

        # -- Point the inputs at the mirrored bones
        for input_name in self.bone_input_names:
            self.input(input_name).set(_remap(original.input(input_name).get(), bone_map))

    def _mirrored_existing(self, name: str, bones) -> str:
        """
        Returns the mirrored name of the bone if such a bone exists, otherwise
        the bone itself (such as a middle spine bone).
        """
        if not name:
            return ""
        mirrored = self.mirror_mixin_mirrored_name(name)
        return mirrored if mirrored in bones else name

    def _description_of(self, name: str) -> str:
        try:
            return self.config.extract_description(name)
        except ValueError:
            return name

    @staticmethod
    def _subtree(component) -> list:
        result = [component]
        for child in list(component.children):
            result.extend(MirrorMixin._subtree(child))
        return result

    def _plan_mirrored_labels(self, originals, expression, replace_with) -> dict:
        """
        Works out a unique label for the mirrored version of every component.
        """
        taken = {component.label() for component in self.stack.components()}
        labels = dict()

        for original in originals:
            label = expression.sub(replace_with, original.label())

            if label == original.label() or label in taken:
                label += self._MIRRORED_LABEL_SUFFIX

            candidate = label
            counter = 2
            while candidate in taken:
                candidate = f"{label} {counter}"
                counter += 1

            taken.add(candidate)
            labels[original] = candidate

        return labels

    @classmethod
    def _retarget_addresses(cls, component, label_map) -> None:
        for attribute in component.inputs() + component.options():
            value = attribute.get(resolved=False)
            retargeted = cls._retargeted_value(value, label_map)
            if retargeted != value:
                attribute.set(retargeted)

    @classmethod
    def _retargeted_value(cls, value, label_map):
        if isinstance(value, str):
            if address.is_address(value):
                label = address.get_label(value)
                if label in label_map:
                    return f"[{label_map[label]}]" + value[len(label) + 2:]
            return value

        if isinstance(value, list):
            return [cls._retargeted_value(item, label_map) for item in value]

        if isinstance(value, dict):
            return {key: cls._retargeted_value(item, label_map) for key, item in value.items()}

        return value


def _depth(bone) -> int:
    depth = 0
    while bone.parent:
        depth += 1
        bone = bone.parent
    return depth


def _remap(value, mapping: dict):
    """
    Returns the value (a name, list or list of lists) with every name swapped
    for the one it maps to.
    """
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_remap(item, mapping) for item in value]
    return value
