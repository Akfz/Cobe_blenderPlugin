import bpy
import json
import mathutils
from .lang import t, Translator
from .prefs import get_preferences
from .utils import is_exportable_action, assign_action_to_armature


BONE_COPY_FIELDS = (
    ("cobe_is_deform", "cobe_is_deform_val"),
)


def has_root_bone(arm_obj):
    if not arm_obj or arm_obj.type != 'ARMATURE' or not arm_obj.data:
        return False
    return any(not bone.parent for bone in arm_obj.data.bones)


def has_bone_index_property(arm_obj):
    return bool(
        arm_obj and
        arm_obj.type == 'ARMATURE' and
        arm_obj.data and
        hasattr(arm_obj.data, "cobe_active_bone_index")
    )


def ensure_valid_bone_index(arm_obj):
    if not has_bone_index_property(arm_obj):
        return

    bones = arm_obj.data.bones
    index = arm_obj.data.cobe_active_bone_index

    if bones and (index < 0 or index >= len(bones)):
        arm_obj.data.cobe_active_bone_index = 0


def get_safe_active_bone(arm_obj):
    if not has_bone_index_property(arm_obj):
        return None

    bones = arm_obj.data.bones
    index = arm_obj.data.cobe_active_bone_index

    if 0 <= index < len(bones):
        return bones[index]

    return None


class COBE_OT_CopyParentBoneData(bpy.types.Operator):
    bl_idname = "cobe.copy_parent_bone_data"
    bl_label = "Copy Parent Data"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("copy_parent_data")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            arm_obj = context.active_object

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        scene.cobe_active_rig = arm_obj
        arm_data = arm_obj.data
        target_names = []

        if context.mode == 'EDIT':
            try:
                target_names = [bone.name for bone in context.selected_editable_bones]
            except Exception:
                target_names = []
        elif context.mode == 'POSE':
            try:
                target_names = [pose_bone.name for pose_bone in context.selected_pose_bones]
            except Exception:
                target_names = []
        else:
            active_bone = get_safe_active_bone(arm_obj)
            if active_bone:
                target_names = [active_bone.name]

        if not target_names:
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        copied = 0

        for bone_name in target_names:
            bone = arm_data.bones.get(bone_name)
            if not bone or not bone.parent:
                continue

            parent = bone.parent

            for field_name, field_key in BONE_COPY_FIELDS:
                if not hasattr(parent, field_name):
                    continue

                value = getattr(parent, field_name)

                if field_key:
                    bone[field_key] = value
                else:
                    try:
                        setattr(bone, field_name, value)
                    except Exception:
                        pass

            copied += 1

        if copied == 0:
            self.report({'ERROR'}, t("select_parent"))
            return {'CANCELLED'}

        self.report({'INFO'}, str(copied))
        return {'FINISHED'}


class COBE_OT_DeleteSelectedAnimation(bpy.types.Operator):
    bl_idname = "cobe.delete_selected_animation"
    bl_label = "Delete Animation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("delete_anim_op")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        action_name = getattr(scene, "cobe_active_action_name", "")
        action = bpy.data.actions.get(action_name) if action_name else None

        if not action and arm_obj and arm_obj.animation_data and arm_obj.animation_data.action:
            action = arm_obj.animation_data.action

        if not action:
            self.report({'ERROR'}, t("no_active_anim"))
            return {'CANCELLED'}

        deleted_name = action.name
        bpy.data.actions.remove(action)

        candidates = [candidate for candidate in bpy.data.actions if is_exportable_action(candidate)]

        if arm_obj:
            if candidates:
                assign_action_to_armature(arm_obj, candidates[0])
                scene.cobe_active_action_name = candidates[0].name
            else:
                if arm_obj.animation_data:
                    arm_obj.animation_data.action = None
                    if hasattr(arm_obj.animation_data, "action_slot"):
                        try:
                            arm_obj.animation_data.action_slot = None
                        except Exception:
                            pass
                scene.cobe_active_action_name = ""
        else:
            scene.cobe_active_action_name = candidates[0].name if candidates else ""

        self.report({'INFO'}, t("anim_deleted").format(deleted_name))
        return {'FINISHED'}


class COBE_OT_KeyframeFps(bpy.types.Operator):
    bl_idname = "cobe.keyframe_fps"
    bl_label = "Keyframe FPS"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        arm_obj.keyframe_insert(data_path="cobe_anim_fps", frame=scene.frame_current)
        return {'FINISHED'}


class CobeTexturePathList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "bone_name", text="", emboss=False, icon='BONE_DATA')
        row.prop(item, "texture_path", text="")


class CobeBoneList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row()

        depth = 0
        parent = item.parent
        while parent:
            depth += 1
            parent = parent.parent

        split = row.split(factor=0.6)
        name_row = split.row(align=True)

        if depth > 0:
            name_row.label(text="    " * depth + "└", icon='BONE_DATA')
        else:
            name_row.label(text="", icon='OUTLINER_OB_ARMATURE')

        name_row.prop(item, "name", text="", emboss=False)

        parent_row = split.row()
        if item.parent:
            parent_row.label(text=t("parent_lbl").format(item.parent.name), icon='LINKED')
        else:
            parent_row.label(text=t("root_lbl"), icon='WORLD')


class CobeMainPanel(bpy.types.Panel):
    bl_label = "Cobe"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cobe"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text=t("cobe_model"))
        layout.row(align=True).prop(scene, "cobe_ui_tab", expand=True)

        arm_obj = scene.cobe_active_rig

        if scene.cobe_ui_tab == 'RIG':
            layout.prop(scene, "cobe_active_rig", text=t("active_rig"))

            if arm_obj and arm_obj.data:
                ensure_valid_bone_index(arm_obj)

                box_rig = layout.box()
                row = box_rig.row(align=True)
                row.prop(scene, "cobe_rename_rig_name", text="")
                row.operator("cobe.rename_rig", text=t("rename"))

                row_null = box_rig.row(align=True)
                if "cobe_null_pose" in arm_obj.data:
                    row_null.operator("cobe.reset_to_null_pose", text=t("reset_to_null_pose_op"), icon='POSE_HLT')
                    row_null.operator("cobe.clear_null_pose", text=t("btn_clear_null_pose"), icon='CANCEL')
                else:
                    row_null.operator("cobe.set_null_pose", text=t("btn_set_null_pose"), icon='POSE_HLT')

            box_create = layout.box()
            box_create.prop(scene, "cobe_new_bone_name", text="")
            row_create = box_create.row(align=True)

            if not has_root_bone(arm_obj):
                row_create.operator("cobe.create_root_bone", text=t("create_root"))
            else:
                row_create.operator("cobe.create_child_bone", text=t("create_child"))

            if has_bone_index_property(arm_obj):
                box_bone = layout.box()
                box_bone.template_list("CobeBoneList", "", arm_obj.data, "bones", arm_obj.data, "cobe_active_bone_index")

                row_actions = box_bone.row(align=True)
                row_actions.operator("cobe.rename_bone", text=t("rename"), icon='TEXT')
                row_actions.operator("cobe.delete_bone", text=t("delete_bone"), icon='TRASH')

                active_bone = get_safe_active_bone(arm_obj)

                if active_bone:
                    box_settings = layout.box()
                    box_settings.label(text=t("bone_settings").format(active_bone.name), icon='BONE_DATA')

                    selected_count = 0
                    try:
                        if context.mode == 'EDIT':
                            selected_count = len(context.selected_editable_bones)
                        elif context.mode == 'POSE':
                            selected_count = len(context.selected_pose_bones)
                    except Exception:
                        selected_count = 0

                    if selected_count > 1:
                        box_settings.label(text=t("editing_selected_bones").format(selected_count), icon='LINKED')

                    row_copy = box_settings.row(align=True)
                    row_copy.operator("cobe.copy_parent_bone_data", text=t("copy_parent_data"), icon='COPYDOWN')
                    row_copy.enabled = bool(active_bone.parent)

                    box_settings.prop(active_bone, "cobe_is_deform", text=t("is_deform"))

            box_texture = layout.box()
            box_texture.label(text=t("texture_paths"), icon='IMAGE_DATA')
            box_texture.template_list("CobeTexturePathList", "", scene, "cobe_texture_paths", scene, "cobe_texture_paths_index")

            row_texture = box_texture.row(align=True)
            row_texture.operator("cobe.texture_path_action", text="+").action = 'ADD'
            row_texture.operator("cobe.texture_path_action", text="-").action = 'REMOVE'

        elif scene.cobe_ui_tab == 'ANIMATIONS':
            layout.prop(scene, "cobe_active_rig", text=t("active_rig"))

            if arm_obj:
                box_anim = layout.box()
                box_anim.prop_search(scene, "cobe_active_action_name", bpy.data, "actions", text=t("anim"))

                row_anim = box_anim.row(align=True)
                row_anim.operator("cobe.create_animation", text=t("anim_new"))
                row_anim.operator("cobe.delete_selected_animation", text=t("anim_delete"))

                box_settings = box_anim.box()
                box_settings.label(text=t("anim_settings"), icon='TIME')

                row_fps = box_settings.row(align=True)
                row_fps.prop(arm_obj, "cobe_anim_fps", text=t("fps"))
                row_fps.operator("cobe.keyframe_fps", text="", icon='KEY_HLT')

                box_settings.prop(scene, "cobe_anim_speed", text=t("speed"))

        elif scene.cobe_ui_tab == 'EXPORT':
            layout.prop(scene, "cobe_active_rig", text=t("active_rig"))

            box_export = layout.box()
            box_export.prop(scene, "cobe_model_name", text=t("model_name"), icon='OBJECT_DATAMODE')

            row_scale = box_export.row(align=True)
            row_scale.prop(scene, "cobe_scale_factor", text=t("scale_factor"))
            row_scale.prop(scene, "cobe_preview_active", text=t("preview_block_16"), toggle=True, icon='CUBE')

            box_list = box_export.box()
            box_list.label(text=t("select_anims"), icon='ACTION')

            for action in bpy.data.actions:
                if not is_exportable_action(action):
                    continue

                row_action = box_list.row(align=True)

                if hasattr(action, "cobe_export_enabled"):
                    row_action.prop(action, "cobe_export_enabled", text="")
                else:
                    row_action.label(text="", icon='ERROR')

                row_action.label(text=action.name)

            row_export = box_export.row(align=True)
            row_export.operator("cobe.export_json", text=t("export_json"))
            row_export.operator("cobe.export_animations_json", text=t("export_anims"))

            if arm_obj and arm_obj.data and "cobe_null_pose" not in arm_obj.data:
                box_warn = layout.box()
                box_warn.alert = True
                box_warn.label(text=t("warn_no_null_pose"), icon='ERROR')

        elif scene.cobe_ui_tab == 'LANGUAGES':
            box_lang = layout.box()
            translator = Translator.getInstance()

            for code, name, _ in translator.availableLanguages:
                row_lang = box_lang.row()
                props = row_lang.operator("cobe.set_language", text=name)
                props.language_code = code

            box_lang.operator("cobe.reload_languages", text=t("reload_lang"), icon='FILE_REFRESH')

            prefs = get_preferences()
            if prefs:
                box_lang.prop(prefs, "cobe_show_debug", text=t("show_debug"))


class CobeUtilitiesPanel(bpy.types.Panel):
    bl_label = "Cobe Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cobe"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        box_utils = layout.box()
        box_utils.label(text=t("tab_utilities"), icon='TOOL_SETTINGS')
        box_utils.operator("cobe.autogen_bones", text=t("btn_autogen"))
        box_utils.operator("cobe.parent_bones_to_root", text=t("btn_parent_root"))
        box_utils.operator("cobe.bake_bones", text=t("btn_bake"))

        if has_bone_index_property(arm_obj):
            box_utils.operator("cobe.bind_object_to_bone", text=t("bind_mesh"), icon='CONSTRAINT_BONE')

        box_uv = layout.box()
        box_uv.label(text=t("tab_uv_texture"), icon='TEXTURE')

        column = box_uv.column(align=True)
        column.prop(scene, "cobe_texture_name", text=t("texture_name"))

        row_size = column.row(align=True)
        row_size.prop(scene, "cobe_texture_width", text=t("texture_width"))
        row_size.prop(scene, "cobe_texture_height", text=t("texture_height"))

        column.prop(scene, "cobe_uv_margin", text=t("uv_margin"))
        box_uv.operator("cobe.generate_texture_uv", text=t("generate_tex_uv"), icon='COLOR')


class CobeDebugPanel(bpy.types.Panel):
    bl_label = "Debug"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cobe"

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("debug_menu_title")
        prefs = get_preferences()
        return bool(prefs and prefs.cobe_show_debug)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        box_debug = layout.box()
        box_debug.label(text=t("null_pose_data"), icon='POSE_HLT')

        if not arm_obj or not arm_obj.data:
            box_debug.label(text=t("no_rig_found"), icon='ERROR')
            return

        active_bone = None

        if context.mode == 'POSE' and context.active_pose_bone:
            active_bone = context.active_pose_bone.bone
        elif context.mode == 'EDIT' and context.active_bone:
            active_bone = context.active_bone
        elif context.mode == 'OBJECT' and arm_obj.data.bones.active:
            active_bone = arm_obj.data.bones.active

        if not active_bone:
            box_debug.label(text=t("select_bone_in_3d"), icon='QUESTION')
            return

        box_debug.label(text=t("selected_bone").format(active_bone.name), icon='BONE_DATA')

        if "cobe_null_pose" not in arm_obj.data:
            box_debug.label(text=t("null_pose_not_set"), icon='QUESTION')
            return

        try:
            pose_data = json.loads(arm_obj.data["cobe_null_pose"])

            if active_bone.name not in pose_data:
                box_debug.label(text=t("no_saved_data"), icon='ERROR')
                return

            flat_matrix = pose_data[active_bone.name]
            matrix = mathutils.Matrix([flat_matrix[i:i + 4] for i in range(0, 16, 4)])
            location, rotation, scale = matrix.decompose()

            column = box_debug.column(align=True)
            column.label(text=t("pivot_lbl"))
            column.label(text=f"  X: {location.x:.4f}, Y: {location.y:.4f}, Z: {location.z:.4f}")
            column.label(text=t("roll_lbl"))
            column.label(text=f"  W: {rotation.w:.4f}, X: {rotation.x:.4f}, Y: {rotation.y:.4f}, Z: {rotation.z:.4f}")
            column.label(text=t("scale_lbl"))
            column.label(text=f"  X: {scale.x:.4f}, Y: {scale.y:.4f}, Z: {scale.z:.4f}")
        except Exception as error:
            box_debug.label(text=t("err_read_null_pose").format(error), icon='ERROR')


classes = (
    COBE_OT_CopyParentBoneData,
    COBE_OT_DeleteSelectedAnimation,
    COBE_OT_KeyframeFps,
    CobeTexturePathList,
    CobeBoneList,
    CobeMainPanel,
    CobeUtilitiesPanel,
    CobeDebugPanel
)
