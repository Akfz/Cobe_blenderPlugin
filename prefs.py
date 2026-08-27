import bpy

PACKAGE_NAME = __package__ if __package__ else __name__


def get_preferences():
    try:
        addon = bpy.context.preferences.addons.get(PACKAGE_NAME)
        return addon.preferences if addon else None
    except Exception:
        return None


def tag_redraw():
    for screen in bpy.data.screens:
        for area in screen.areas:
            area.tag_redraw()
