"""
The Aniseed Riggers Toolkit: a window of tools for working on rigs. Its tools
are the toolkit tools (see aniseed_blender_standard.toolkit) whose toolkit is
"Riggers", from this package's tools folder or any other active package's.
"""
TOOLKIT = "Riggers"


def launch():
    """
    Opens the Riggers Toolkit window.
    """
    from aniseed_blender_standard.toolkit import app
    from . import config

    return app.launch(config.RiggersToolkitConfig)
