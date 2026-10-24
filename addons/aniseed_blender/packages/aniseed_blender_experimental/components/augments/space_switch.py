"""
Provides "Experiment : Space Switch", which lets a control follow one of
several spaces (other control rig bones), chosen with a drop down property on
a control. It is the Blender counterpart of aniseed_maya's "Augment : Space
Switch", and keeps its data and its editing UI (SpaceList, OptionsBlock and
SpaceSwitchUi).

Where Maya constrains the control's org group, here the control is given a
mechanical "space" bone as its parent, which plays the same part: the space
bone moves, and the control's own values never change when switching. A pose
bone's values are relative to its own rest pose, so the new parent does not
change what they mean either.

The space bone follows the spaces through an Armature constraint, with a
target per space whose weight is driven by the property. An Armature
constraint moves its bone by how far each target has moved from its rest
pose, so no offsets need capturing and the rig is unchanged at rest.

Position Only and Orientation Only (which apply to every space) need a second
mechanical bone: the "switch" bone carries the Armature constraint, and the
space bone, still following the control's original parent, copies only its
location or only its rotation.
"""
import uuid
import logging
import collections

import qtility
import aniseed

from Qt import QtCore, QtWidgets

from aniseed_blender_experimental import base
from aniseed_blender_experimental.lib import armature as armature_lib
from aniseed_blender_experimental.lib import rigging

log = logging.getLogger(__name__)


class SpaceSwitch(aniseed.RigComponent):
    """
    Adds a drop down property to a control (the Attribute Host) and makes the
    driven control follow whichever space it names.

    Add it beneath the component whose control it switches, after any
    component providing a space, so they are all built first.
    """

    identifier = "Experiment : Space Switch"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_input(
            name="To Be Driven",
            value="",
            description="The control which switches space, normally another component's output",
            validate=True,
            group="Required Entries",
        )

        self.declare_input(
            name="Attribute Host",
            value="",
            description="The control to put the space property on. Defaults to the driven control.",
            validate=False,
            group="Required Entries",
        )

        self.declare_option(
            name="Property Name",
            value="space",
            description="The name of the drop down property on the attribute host",
            group="Behaviour",
        )

        self.declare_option(
            name="_Data",
            value=None,
            description=(
                "The spaces (label, target, position / orientation only) and the default "
                "space. Edited with the space switch UI."
            ),
            group="Behaviour",
        )

        self.declare_output(name="Space Bone", description="The mechanical bone the driven control is now parented to")

    def option_widget(self, option_name: str):
        if option_name == "_Data":
            return SpaceSwitchUi(self)
        return None

    def input_widget(self, requirement_name: str):
        if requirement_name in ("To Be Driven", "Attribute Host"):
            return aniseed.widgets.ObjectSelector(component=self)
        return None

    # ----------------------------------------------------------------------------------
    def on_enter_stack(self):
        """
        Hooks the driven control to the parent component (its IK control, if
        it has one) and, if there are no spaces yet, starts with a "Parent"
        space (where the parent component's controls are parented) and a
        "World" space (the root offset control).
        """
        super().on_enter_stack()

        if not self.input("To Be Driven").get(resolved=False):
            self.input("To Be Driven").hook_to_parent(tags=["ik"])

        if self.get_data()["spaces"]:
            return

        spaces = []

        parent_input = self.parent.input("Parent") if self.parent else None
        if parent_input is not None and parent_input.get(resolved=False):
            spaces.append(("Parent", parent_input.get(resolved=False)))

        for component in self.rig.components():
            if component.identifier == "Experiment : Root" and component.output("Offset Control"):
                spaces.append(("World", component.output("Offset Control").address()))
                break

        if spaces:
            self.option("_Data").set(self.data_for(spaces[0][0], spaces))

    # ----------------------------------------------------------------------------------
    def is_valid(self) -> bool:
        data = self.get_data()
        spaces = data.get("spaces", list())

        if not spaces:
            log.warning(f"{self.label()} : No spaces have been defined")
            return False

        labels = list()
        for space in spaces:
            label = space.get("label")

            if not label:
                log.warning(f"{self.label()} : A space has no label")
                return False

            if not space.get("target"):
                log.warning(f"{self.label()} : The space {label!r} has no target")
                return False

            if label in labels:
                log.warning(f"{self.label()} : More than one space is labelled {label!r}")
                return False

            labels.append(label)

        default_space = data.get("default_space")
        if default_space and default_space not in labels:
            log.warning(f"{self.label()} : The default space {default_space!r} is not one of the spaces ({', '.join(labels)})")
            return False

        if any(space.get("position_only") for space in spaces) and any(space.get("orientation_only") for space in spaces):
            log.warning(f"{self.label()} : A space switch can be position only or orientation only, not both")
            return False

        return True

    def run(self):
        """
        Data takes the form of:

        {
            "default_space": "Parent",
            "spaces": [
                {
                    "label": "Parent",
                    "target": "[Spine].[output].[Blended Chest]",
                    "position_only": False,
                    "orientation_only": False,
                    "uuid_": "...",
                }
            ]
        }
        """
        control = armature_lib.find_role(self.rig.label, armature_lib.CONTROL)
        if control is None:
            log.warning(f"{self.label()} : there is no control armature. Is Create Control Armature above this component?")
            return False

        data = self.get_data()
        driven = self.input("To Be Driven").get()
        host = self.input("Attribute Host").get() or driven
        property_name = self.option("Property Name").get() or "space"

        spaces = [dict(space, target=self._resolve(space["target"])) for space in data["spaces"]]
        labels = [space["label"] for space in spaces]

        missing = [
            f"{name} ({value})" for name, value in [("To Be Driven", driven), ("Attribute Host", host)]
            + [(f"space {space['label']}", space["target"]) for space in spaces]
            if not isinstance(value, str) or value not in control.data.bones
        ]
        if missing:
            log.warning(f"{self.label()} : these are not control armature bones (are they built yet?): {', '.join(missing)}")
            return False

        if property_name in control.pose.bones[host]:
            log.warning(f"{self.label()} : {host} already has a {property_name!r} property. Give this space switch another Property Name.")
            return False

        position_only = any(space.get("position_only") for space in spaces)
        orientation_only = any(space.get("orientation_only") for space in spaces)
        default_index = labels.index(data["default_space"]) if data.get("default_space") in labels else 0

        space_bone, switch_bone = self._create_bones(control, driven, partial=position_only or orientation_only)

        # -- The switch bone follows the spaces, each target's weight being 1
        # -- only while the property names its space
        rigging.add_property(
            control.pose.bones[host],
            property_name,
            default_index,
            0,
            len(spaces) - 1,
            f"The space {driven} follows",
            items=labels,
        )

        constraint = rigging.constrain(control.pose.bones[switch_bone], "ARMATURE", name="Space Switch")
        for index, space in enumerate(spaces):
            target = constraint.targets.new()
            target.target = control
            target.subtarget = space["target"]
            target.weight = 1.0 if index == default_index else 0.0

            rigging.drive(target, "weight", control, host, property_name, f"var == {index}")

        if position_only:
            rigging.constrain(control.pose.bones[space_bone], "COPY_LOCATION", name="Space Switch", target=control, subtarget=switch_bone)
        elif orientation_only:
            rigging.constrain(control.pose.bones[space_bone], "COPY_ROTATION", name="Space Switch", target=control, subtarget=switch_bone)

        for bone in {space_bone, switch_bone}:
            rigging.assign_collection(control, bone, base.MECHANICS)

        self.output("Space Bone").set(space_bone)
        return True

    def _create_bones(self, control, driven: str, partial: bool):
        """
        Creates the space bone (and, for a partial switch, the switch bone) at
        the driven control's rest position, and parents the control to the
        space bone. Returns the names of the space and switch bones, which
        are the same bone for a full switch.
        """
        try:
            description = self.config.extract_description(driven)
            location = self.config.extract_location(driven)
        except ValueError:
            description, location = driven, self.config.middle

        with armature_lib.edit_bones(control) as edit_bones:
            bone = edit_bones[driven]
            original_parent = bone.parent.name if bone.parent else None

            # -- Read before any bone is added, as adding edit bones can
            # -- invalidate references to the existing ones
            head, tail, z_axis = bone.head.copy(), bone.tail.copy(), bone.z_axis.copy()

            def copy(suffix, parent):
                return armature_lib.new_bone(
                    edit_bones,
                    self.config.generate_name(self.config.mechanical, description + suffix, location),
                    head,
                    tail,
                    z_axis=z_axis,
                    parent=parent,
                )

            # -- An Armature constraint expects its bone to have no parent, so
            # -- a full switch's space bone has none. A partial one keeps
            # -- following the original parent, and copies part of the switch.
            space_bone = copy("Space", original_parent if partial else None)
            switch_bone = copy("Switch", None) if partial else space_bone

            bone = edit_bones[driven]
            bone.use_connect = False
            bone.parent = edit_bones[space_bone]

        return space_bone, switch_bone

    def _resolve(self, value):
        """
        Returns the value of the attribute the given value addresses, or the
        value itself if it is not an address.
        """
        if not value:
            return value

        attribute = self.rig.resolve_attribute(value)
        return attribute.get() if attribute else value

    # ----------------------------------------------------------------------------------
    @classmethod
    def add_to(cls, component, label: str, driven: str, default_space: str, spaces: list):
        """
        Adds a Space Switch component beneath the given component. The driven
        control also hosts the property.

        Other components can reach this without importing this module, via
        ``self.rig.component_library.request("Experiment : Space Switch").add_to(...)``.

        Args:
            component: The component to add the space switch beneath
            label: The label for the space switch component
            driven: The address of the control to switch
            default_space: The label of the space which is active by default
            spaces: (label, target address) tuples, in the order they appear

        Returns:
            The space switch component
        """
        space_switch = component.stack.add_component(
            component_type=cls.identifier,
            label=label,
            parent=component,
            inputs={"To Be Driven": driven},
            options={"_Data": cls.data_for(default_space, spaces)},
        )
        return space_switch

    @classmethod
    def data_for(cls, default_space: str, spaces: list) -> dict:
        """
        Returns space switch data for the given (label, target) tuples.
        """
        return dict(
            default_space=default_space,
            spaces=[dict(cls.space_template(), label=label, target=target) for label, target in spaces],
        )

    @classmethod
    def space_template(cls):
        """
        Returns a new space dictionary with default values and a freshly
        generated uuid.
        """
        return dict(
            target="",
            label="",
            position_only=False,
            orientation_only=False,
            uuid_=str(uuid.uuid4()),
        )

    def get_data(self) -> dict:
        """
        Returns the stored data, or an empty structure (no default space and
        no spaces) if nothing has been stored yet.
        """
        data = self.option("_Data").get()

        if not data:
            return dict(default_space="", spaces=list())

        return data

    def get_uuids(self):
        return [space["uuid_"] for space in self.get_data()["spaces"]]

    def get_space_data(self, uuid_) -> dict:
        for data in self.get_data()["spaces"]:
            if data["uuid_"] == uuid_:
                return data
        return None

    def remove_space(self, uuid_):
        data = self.get_data()
        data["spaces"] = [space for space in data["spaces"] if space["uuid_"] != uuid_]
        self.option("_Data").set(data)

    def set_default_space(self, label):
        data = self.get_data()
        data["default_space"] = label
        self.option("_Data").set(data)

    def get_default_space(self):
        return self.get_data().get("default_space", "")

    def add_space(self, space_data):
        """
        Stores the given space, replacing (in place) any space with the same
        uuid, or adding it to the end. Returns the updated data.
        """
        uuid_ = space_data["uuid_"]
        uuids = self.get_uuids()

        data = self.get_data()

        if uuid_ in uuids:
            data["spaces"][uuids.index(uuid_)] = space_data
        else:
            data["spaces"].append(space_data)

        self.option("_Data").set(data)
        return data

    def move_space(self, uuid_, move_by):
        """
        Moves the space with the given uuid by the given number of positions.
        Unknown uuids and moves past either end are ignored.
        """
        uuids = self.get_uuids()
        if uuid_ not in uuids:
            return

        index = uuids.index(uuid_)
        new_index = index + move_by
        if new_index < 0 or new_index >= len(uuids):
            return

        data = self.get_data()
        data["spaces"].insert(new_index, data["spaces"].pop(index))
        self.option("_Data").set(data)

    def set_position_only(self, value: bool) -> None:
        """
        Sets the position_only flag on every space, as it applies to the
        whole space switch.
        """
        data = self.get_data()
        for space in data["spaces"]:
            space["position_only"] = bool(value)
        self.option("_Data").set(data)

    def set_orientation_only(self, value: bool) -> None:
        """
        Sets the orientation_only flag on every space, as it applies to the
        whole space switch.
        """
        data = self.get_data()
        for space in data["spaces"]:
            space["orientation_only"] = bool(value)
        self.option("_Data").set(data)


# --------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class SpaceList(QtWidgets.QWidget):
    """
    The list of spaces, with buttons to add, remove and reorder them.
    """

    changed = QtCore.Signal()
    uuid_selected = QtCore.Signal(str)

    def __init__(self, component, button_size=30, parent=None):
        super().__init__(parent=parent)

        self.component = component
        self._button_size = button_size

        self.setLayout(qtility.layouts.slimify(QtWidgets.QHBoxLayout()))

        self.list_widget = QtWidgets.QListWidget()
        self.layout().addWidget(self.list_widget)

        self.populate()

        self.button_layout = QtWidgets.QVBoxLayout()

        self.add_button = QtWidgets.QPushButton("+")
        self.remove_button = QtWidgets.QPushButton("-")
        self.up_button = QtWidgets.QPushButton("Up")
        self.down_button = QtWidgets.QPushButton("Dn")

        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            button.setFixedSize(self._button_size, self._button_size)
            self.button_layout.addWidget(button)

        self.button_layout.addSpacerItem(
            QtWidgets.QSpacerItem(10, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding),
        )

        self.layout().addLayout(self.button_layout)
        self.layout().setStretch(0, 1)

        self.add_button.clicked.connect(self.add)
        self.remove_button.clicked.connect(self.remove)
        self.up_button.clicked.connect(self.move_up)
        self.down_button.clicked.connect(self.move_down)

        self.list_widget.currentItemChanged.connect(self.propagate_uuid_change)

    def propagate_uuid_change(self, item):
        if item:
            self.uuid_selected.emit(item.uuid_)

    def populate(self):
        self.list_widget.clear()

        for space_data in self.component.get_data()["spaces"]:
            self.add(space_data["label"], space_data["uuid_"])

    def add(self, label=None, uuid_=None):
        """
        Adds a space to the list. If no label is given the user is asked for
        one, and if no uuid is given a new space is stored on the component.
        """
        if not label:
            label = qtility.request.text(title="Space Name", message="Please give a name for this space")

        if not label:
            return

        if not uuid_:
            new_data = self.component.space_template()
            new_data["label"] = label
            uuid_ = new_data["uuid_"]
            self.component.add_space(new_data)

        item = QtWidgets.QListWidgetItem(label)
        item.uuid_ = uuid_
        self.list_widget.addItem(item)

        self.changed.emit()

    def remove(self):
        if not self.list_widget.currentItem():
            return

        item = self.list_widget.takeItem(self.list_widget.currentRow())
        self.component.remove_space(item.uuid_)
        self.changed.emit()

    def move_up(self):
        self._move(-1)

    def move_down(self):
        self._move(1)

    def _move(self, move_by):
        if not self.list_widget.currentItem():
            return

        index = self.list_widget.currentRow()
        new_index = index + move_by
        if new_index < 0 or new_index >= self.list_widget.count():
            return

        item = self.list_widget.takeItem(index)
        self.list_widget.insertItem(new_index, item)
        self.component.move_space(item.uuid_, move_by)
        self.list_widget.setCurrentRow(new_index)
        self.changed.emit()

    def rename_current_item(self, new_name):
        if self.list_widget.currentItem():
            self.list_widget.currentItem().setText(new_name)


# --------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class OptionsBlock(QtWidgets.QWidget):
    """
    Edits the selected space: its label and target, the position only and
    orientation only flags (which apply to every space), and whether it is
    the default space.
    """

    label_changed = QtCore.Signal(str)

    def __init__(self, component, parent=None):
        super().__init__(parent=parent)

        self.setLayout(qtility.layouts.slimify(QtWidgets.QVBoxLayout()))

        self.component = component
        self._ignore_serialisation = False
        self._active_uuid = None

        self.label = QtWidgets.QLineEdit()
        self.target = aniseed.widgets.ObjectSelector(component=component)
        self.position_only = QtWidgets.QCheckBox()
        self.orientation_only = QtWidgets.QCheckBox()
        self.is_default = QtWidgets.QCheckBox()

        widgets_to_wrap = collections.OrderedDict()
        widgets_to_wrap["Label"] = self.label
        widgets_to_wrap["Target"] = self.target
        widgets_to_wrap["-"] = None
        widgets_to_wrap["Position Only (all spaces)"] = self.position_only
        widgets_to_wrap["Orientation Only (all spaces)"] = self.orientation_only
        widgets_to_wrap["--"] = None
        widgets_to_wrap["Is Default Space"] = self.is_default

        tooltip = "Applies to every space in this switch. Toggling here updates all spaces."
        self.position_only.setToolTip(tooltip)
        self.orientation_only.setToolTip(tooltip)

        for label, widget_to_wrap in widgets_to_wrap.items():
            if not widget_to_wrap:
                self.layout().addSpacerItem(
                    QtWidgets.QSpacerItem(5, 5, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed),
                )
            else:
                self.layout().addLayout(qtility.widgets.addLabel(widget_to_wrap, label, 150, slim=False))

        qtility.derive.connect(self.label, self.serialise)
        qtility.derive.connect(self.label, self.label_changed.emit)
        qtility.derive.connect(self.target, self.serialise)
        qtility.derive.connect(self.position_only, self.serialise)
        qtility.derive.connect(self.orientation_only, self.serialise)
        qtility.derive.connect(self.is_default, self.serialise)

        self.setEnabled(False)

    def populate_options(self, uuid_):
        """
        Shows the space with the given uuid, without writing anything back.
        """
        self._ignore_serialisation = True
        self._active_uuid = uuid_

        space_data = self.component.get_space_data(uuid_) if uuid_ else None
        self.setEnabled(space_data is not None)

        if space_data is not None:
            all_spaces = self.component.get_data()["spaces"]

            self.label.setText(space_data["label"])
            self.target.set_value(space_data["target"])
            self.position_only.setChecked(any(space.get("position_only") for space in all_spaces))
            self.orientation_only.setChecked(any(space.get("orientation_only") for space in all_spaces))
            self.is_default.setChecked(space_data["label"] == self.component.get_default_space())

        self._ignore_serialisation = False

    def serialise(self, *args, **kwargs):
        """
        Writes the widgets back to the selected space. Position only and
        orientation only are written to every space (ticking one unticks the
        other), and ticking "Is Default Space" makes this the default.
        """
        if self._ignore_serialisation or not self._active_uuid:
            return

        sender = self.sender()
        if sender is self.position_only and self.position_only.isChecked():
            self._set_checked_quietly(self.orientation_only, False)
        elif sender is self.orientation_only and self.orientation_only.isChecked():
            self._set_checked_quietly(self.position_only, False)

        previous = self.component.get_space_data(self._active_uuid) or dict()
        was_default = previous.get("label") == self.component.get_default_space()

        data = self.component.space_template()
        data.update(
            label=self.label.text(),
            target=self.target.get_value(),
            position_only=self.position_only.isChecked(),
            orientation_only=self.orientation_only.isChecked(),
            uuid_=self._active_uuid,
        )
        self.component.add_space(data)

        self.component.set_position_only(self.position_only.isChecked())
        self.component.set_orientation_only(self.orientation_only.isChecked())

        # -- Renaming the default space keeps it the default
        if self.is_default.isChecked() or was_default:
            self.component.set_default_space(data["label"])

    def _set_checked_quietly(self, checkbox, value):
        self._ignore_serialisation = True
        checkbox.setChecked(value)
        self._ignore_serialisation = False


# --------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class SpaceSwitchUi(QtWidgets.QWidget):
    """
    The space list above the selected space's options. Edits are written
    straight to the component's "_Data" option.
    """

    changed = QtCore.Signal()
    dont_label = True

    def __init__(self, component, parent=None):
        super().__init__(parent=parent)

        self.component = component

        self.setLayout(qtility.layouts.slimify(QtWidgets.QVBoxLayout()))

        self.text_list = SpaceList(component)
        self.options_block = OptionsBlock(component)

        self.layout().addWidget(self.text_list)
        self.layout().addSpacerItem(
            QtWidgets.QSpacerItem(10, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed),
        )
        self.layout().addWidget(self.options_block)

        self.text_list.uuid_selected.connect(self.options_block.populate_options)
        self.options_block.label_changed.connect(self.text_list.rename_current_item)
