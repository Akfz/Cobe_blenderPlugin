import bpy
from . import lang, preferences, properties, operators, exporter, ui_panels
from .prefs import get_preferences
from .lang import Translator


@bpy.app.handlers.persistent
def sync_cobe_active_bone(scene, *args):
    try:
        context = bpy.context
        obj = context.view_layer.objects.active

        if obj and obj.type == 'ARMATURE':
            armature = obj.data

            if context.mode == 'EDIT':
                active_edit_bone = armature.edit_bones.active
                if active_edit_bone:
                    index = armature.bones.find(active_edit_bone.name)
                    if index != -1 and armature.cobe_active_bone_index != index:
                        armature.cobe_active_bone_index = index
            elif context.mode == 'POSE':
                active_pose_bone = obj.pose.active_bone
                if active_pose_bone:
                    index = armature.bones.find(active_pose_bone.name)
                    if index != -1 and armature.cobe_active_bone_index != index:
                        armature.cobe_active_bone_index = index
    except Exception:
        pass


def get_classes():
    return (
        preferences.classes +
        properties.classes +
        lang.classes +
        operators.classes +
        exporter.classes +
        ui_panels.classes
    )


def unregister_classes(classes):
    for cls in reversed(classes):
        try:
            if getattr(cls, "is_registered", False):
                bpy.utils.unregister_class(cls)
        except Exception:
            pass


def register_classes(classes):
    for cls in classes:
        try:
            if not getattr(cls, "is_registered", False):
                bpy.utils.register_class(cls)
        except Exception:
            pass


def register():
    lang.load_translations()

    try:
        properties.unregister_properties()
    except Exception:
        pass

    classes = get_classes()
    unregister_classes(classes)
    register_classes(classes)

    properties.register_properties()

    if sync_cobe_active_bone not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(sync_cobe_active_bone)

    prefs = get_preferences()
    if prefs:
        Translator.getInstance().current_language = prefs.cobe_language


def unregister():
    if sync_cobe_active_bone in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(sync_cobe_active_bone)

    try:
        properties.unregister_properties()
    except Exception:
        pass

    unregister_classes(get_classes())
