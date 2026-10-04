import bpy


def is_exportable_action(action):
    return action.name != "SceneAction"


def get_action_slot(action, arm_obj):
    if not hasattr(action, "slots") or not action.slots:
        return None

    names = []
    if arm_obj:
        names.append(arm_obj.name)
        if arm_obj.data:
            names.append(arm_obj.data.name)

    for slot in action.slots:
        slot_name = getattr(slot, "name_display", getattr(slot, "identifier", ""))
        if slot_name in names:
            return slot

    for slot in action.slots:
        slot_name = getattr(slot, "name_display", getattr(slot, "identifier", ""))
        for name in names:
            if name and name in slot_name:
                return slot

    return action.slots[0]


def assign_action_to_armature(arm_obj, action):
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()

    arm_obj.animation_data.action = action

    if action and hasattr(arm_obj.animation_data, "action_slot"):
        slot = get_action_slot(action, arm_obj)
        if slot:
            try:
                arm_obj.animation_data.action_slot = slot
            except Exception:
                pass


def _ensure_in_view_layer(context, arm_obj):
    """Возвращает True, если объект доступен в view_layer (тогда он сможет стать active)."""
    try:
        return arm_obj.name in context.view_layer.objects
    except Exception:
        return False


def enter_armature_edit_mode(context, arm_obj):
    if arm_obj is None:
        raise RuntimeError("enter_armature_edit_mode: armature is None")

    previous_mode = context.mode
    need_switch = previous_mode != 'EDIT_ARMATURE' or context.active_object != arm_obj

    if not need_switch:
        return previous_mode, need_switch

    if context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    try:
        arm_obj.hide_viewport = False
        arm_obj.hide_select = False
        arm_obj.hide_set(False)
    except Exception:
        pass

    if not _ensure_in_view_layer(context, arm_obj):
        try:
            context.scene.collection.objects.link(arm_obj)
        except Exception:
            pass

        try:
            for coll in arm_obj.users_collection:
                for layer_coll in context.view_layer.layer_collection.children:
                    if layer_coll.collection == coll:
                        layer_coll.exclude = False
                        layer_coll.hide_viewport = False
        except Exception:
            pass

    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        try:
            for obj in context.view_layer.objects:
                obj.select_set(False)
        except Exception:
            pass

    try:
        arm_obj.select_set(True)
    except Exception:
        pass

    context.view_layer.objects.active = arm_obj

    if context.active_object is None:
        raise RuntimeError(
            "Не удалось активировать '{}'. Проверьте, что арматура не скрыта и её коллекция не исключена из view layer.".format(arm_obj.name)
        )

    bpy.ops.object.mode_set(mode='EDIT')

    return previous_mode, need_switch


def exit_armature_edit_mode(context, previous_mode, need_switch):
    if not need_switch:
        return

    target_mode = 'POSE' if previous_mode == 'POSE' else 'OBJECT'
    try:
        bpy.ops.object.mode_set(mode=target_mode)
    except Exception:
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass


def get_active_bone_name_from_index(arm_data):
    index = arm_data.cobe_active_bone_index
    if 0 <= index < len(arm_data.bones):
        return arm_data.bones[index].name
    return None


def get_parent_bone_name(context, arm_obj):
    arm_data = arm_obj.data

    bone_name = get_active_bone_name_from_index(arm_data)
    if bone_name:
        return bone_name

    if context.active_bone:
        return context.active_bone.name

    if arm_data.bones.active:
        return arm_data.bones.active.name

    return None
