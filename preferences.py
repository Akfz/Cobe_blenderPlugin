import bpy
from .prefs import PACKAGE_NAME
from .lang import get_language_items, update_language


class CobePreferences(bpy.types.AddonPreferences):
    bl_idname = PACKAGE_NAME

    cobe_language: bpy.props.EnumProperty(
        items=get_language_items,
        update=update_language
    )

    cobe_show_debug: bpy.props.BoolProperty(
        default=False,
        update=update_language
    )

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "cobe_language")
        row.prop(self, "cobe_show_debug")


classes = (
    CobePreferences,
)
