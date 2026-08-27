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


def enter_armature_edit_mode(context, arm_obj):
    previous_mode = context.mode
    need_switch = previous_mode != 'EDIT_ARMATURE' or context.active_object != arm_obj

    if need_switch:
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        bpy.ops.object.select_all(action='DESELECT')
        arm_obj.select_set(True)
        context.view_layer.objects.active = arm_obj
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
