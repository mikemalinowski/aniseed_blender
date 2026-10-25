"""
The app configuration of the Animators Toolkit window. Kept apart from the
package's __init__, as it needs Qt.
"""
import os

from aniseed_blender_standard.toolkit import app

from . import TOOLKIT

RESOURCES = os.path.join(os.path.dirname(__file__), "_res")


class AnimatorsToolkitConfig(app.ToolkitConfig):
    toolkit = TOOLKIT
    label = "Aniseed Animators Toolkit"

    icon = os.path.join(RESOURCES, "icon.png")
    splash_image = icon
    stack_background = os.path.join(RESOURCES, "stack_background.png")
