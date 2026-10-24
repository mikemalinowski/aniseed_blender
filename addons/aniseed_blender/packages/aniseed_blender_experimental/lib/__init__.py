"""
Plain bpy helpers used by the experiment components. Nothing in here knows
about aniseed, so each module can be used (and tested) on its own.

    armature    finding the rig's armatures, edit mode, creating bones
    context     a full context and one undo step for right click actions
    curves      reading and writing curves as json friendly data
    mirroring   mirroring bones and points across X
    rigging     constraints, drivers, custom properties and bone collections
    widgets     the control shape library, as mesh objects
"""
