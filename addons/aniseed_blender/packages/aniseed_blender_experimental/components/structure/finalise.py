"""
Provides "Experiment : Finalise", which tidies the rig up at the end of a
build: hiding the mechanical bones and the deform armature.
"""
import aniseed

from aniseed_blender_experimental.lib import armature as armature_lib


class Finalise(aniseed.RigComponent):
    """
    Hides the control armature's bone collections listed in Hidden Collections
    and, optionally, the deform armature (Make Rig Editable shows it again).
    """

    identifier = "Experiment : Finalise"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.declare_option(
            name="Hidden Collections",
            value=["Mechanics"],
            description="The control armature bone collections to hide",
        )

        self.declare_option(
            name="Hide Deform Armature",
            value=True,
            description="Hides the deform armature, so only the controls are seen",
        )

    def option_widget(self, option_name):
        if option_name == "Hidden Collections":
            return aniseed.widgets.TextList()
        return None

    def run(self):
        control = armature_lib.find_role(self.rig.label, armature_lib.CONTROL)
        if control is not None:
            for name in self.option("Hidden Collections").get():
                collection = control.data.collections_all.get(name)
                if collection is not None:
                    collection.is_visible = False

        deform = armature_lib.find_role(self.rig.label, armature_lib.DEFORM)
        if deform is not None and self.option("Hide Deform Armature").get():
            deform.hide_set(True)

        return True
