"""
The Aniseed Animators Toolkit: a window of tools for animating aniseed rigs.
Its tools are the toolkit tools (see aniseed_blender_standard.toolkit) whose
toolkit is "Animators", from this package's tools folder or any other active
package's.
"""
TOOLKIT = "Animators"


def launch():
    """
    Opens the Animators Toolkit window.
    """
    from aniseed_blender_standard.toolkit import app
    from . import config

    return app.launch(config.AnimatorsToolkitConfig)
