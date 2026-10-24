"""
Mixins used by the experiment components. Each contributes menu entries
through ``mixin_functions``. Compose them alongside RigComponent:

    from aniseed_blender_experimental.mixins import CreateBonesMixin, MirrorMixin

    class Arm(aniseed.RigComponent, CreateBonesMixin, MirrorMixin):
        ...

Import the mixins by name, but never import a RigComponent subclass by name
into a component module: the component factory registers every RigComponent
subclass it finds in a module's namespace.
"""
from .bones import BoneSpec
from .bones import CreateBonesMixin
from .guides import GuideMixin
from .mirroring import MirrorMixin
