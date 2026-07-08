import sys
import importlib
import mathutils
import math
import bpy
import json

packageName = __package__
if packageName:
    for sub in ["cobe_format", "lang", "operators", "exporter"]:
        if f"{packageName}.{sub}" in sys.modules: 
            importlib.reload(sys.modules[f"{packageName}.{sub}"])

from . import cobe_format, lang, operators, exporter
from .lang import t, getLanguageItems

class CobeTexturePath(bpy.types.PropertyGroup):
    bone_name: bpy.props.StringProperty(default="root")
    texture_path: bpy.props.StringProperty(default="textures/entity/model.png")

class CobeTexturePathList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "bone_name", text="", emboss=False, icon='BONE_DATA')
        layout.prop(item, "texture_path", text="")

class COBE_OT_TexturePathAction(bpy.types.Operator):
    bl_idname = "cobe.texture_path_action"
    bl_label = "Texture Action"
    action: bpy.props.EnumProperty(items=[('ADD', 'Add', ''), ('REMOVE', 'Remove', '')])
    
    @classmethod
    def poll(cls, context):
        cls.bl_label = t("texture_action")
        return True
    
    def execute(self, context):
        if self.action == 'ADD': context.scene.cobe_texture_paths.add()
        elif self.action == 'REMOVE':
            idx = context.scene.cobe_texture_paths_index
            if 0 <= idx < len(context.scene.cobe_texture_paths):
                context.scene.cobe_texture_paths.remove(idx)
                context.scene.cobe_texture_paths_index = max(0, idx - 1)
        return {'FINISHED'}

class CobeBoneList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row()
        depth = 0
        p = item.parent
        while p:
            depth += 1
            p = p.parent
        
        split = row.split(factor=0.6)
        col_name = split.row(align=True)
        if depth > 0:
            col_name.label(text="   " * depth + "↳", icon='BONE_DATA')
        else:
            col_name.label(text="", icon='OUTLINER_OB_ARMATURE')
            
        col_name.prop(item, "name", text="", emboss=False)
        
        col_parent = split.row()
        col_parent.label(text=t("parent_lbl").format(item.parent.name) if item.parent else t("root_lbl"), icon='LINKED' if item.parent else 'WORLD')

class CobeBindObjectToBone(bpy.types.Operator):
    bl_idname = "cobe.bind_object_to_bone"
    bl_label = "Bind Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("bind_mesh")
        return True

    def execute(self, context):
        armObj = context.scene.cobe_active_rig
        if not armObj:
            self.report({'ERROR'}, t("err_no_active_rig"))
            return {'CANCELLED'}
            
        targetBone = armObj.data.bones[armObj.data.cobe_active_bone_index]
        for meshObj in [o for o in context.selected_objects if o.type == 'MESH']:
            matrixWorld = meshObj.matrix_world.copy()
            meshObj.parent = armObj
            meshObj.parent_type = 'BONE'
            meshObj.parent_bone = targetBone.name
            meshObj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            meshObj.matrix_world = matrixWorld
        return {'FINISHED'}

class COBE_OT_ToggleGameScalePreview(bpy.types.Operator):
    bl_idname = "cobe.toggle_game_scale_preview"
    bl_label = "Toggle In-Game Scale Preview"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.cobe_active_rig is not None

    def execute(self, context):
        scene = context.scene
        armObj = scene.cobe_active_rig
        scale_factor = scene.cobe_scale_factor
        current_scale = armObj.scale[0]
        if abs(current_scale - 1.0) < 0.001:
            armObj.scale = (scale_factor, scale_factor, scale_factor)
            self.report({'INFO'}, t("rig_scaled").format(scale_factor))
        else:
            armObj.scale = (1.0, 1.0, 1.0)
            self.report({'INFO'}, t("rig_scale_reset"))
        return {'FINISHED'}

def getUiTabItems(self, context):
    return [
        ('RIG', t("tab_rig"), ''),
        ('ANIMATIONS', t("tab_animations"), ''),
        ('EXPORT', t("tab_export"), ''),
        ('LANGUAGES', t("tab_languages"), '')
    ]

class CobeMainPanel(bpy.types.Panel):
    bl_label = "Cobe"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cobe'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text=t("cobe_model"))
        layout.row(align=True).prop(scene, "cobe_ui_tab", expand=True)
        armObj = scene.cobe_active_rig

        if scene.cobe_ui_tab == 'RIG':
            layout.prop(scene, "cobe_active_rig", text=t("active_rig"))
            boxRig = layout.box()
            if armObj:
                row = boxRig.row(align=True)
                row.prop(scene, "cobe_rename_rig_name", text="")
                row.operator("cobe.rename_rig", text=t("rename"))
                rowNull = boxRig.row(align=True)
                if "cobe_null_pose" in armObj.data:
                    rowNull.operator("cobe.clear_null_pose", text=t("btn_clear_null_pose"), icon='CANCEL')
                else:
                    rowNull.operator("cobe.set_null_pose", text=t("btn_set_null_pose"), icon='POSE_HLT')
            boxCreate = layout.box()
            boxCreate.prop(scene, "cobe_new_bone_name", text="")
            row = boxCreate.row(align=True)
            row.operator("cobe.create_bone", text=t("create_root"))
            row.operator("cobe.create_child_bone", text=t("create_child"))
            
            boxBone = layout.box()
            if armObj:
                boxBone.template_list("CobeBoneList", "", armObj.data, "bones", armObj.data, "cobe_active_bone_index")
                row_act = boxBone.row(align=True)
                row_act.operator("cobe.rename_bone", text=t("rename"), icon='TEXT')
                row_act.operator("cobe.delete_bone", text=t("delete_bone"), icon='TRASH')
                
                active_bone_idx = armObj.data.cobe_active_bone_index
                if 0 <= active_bone_idx < len(armObj.data.bones):
                    active_bone = armObj.data.bones[active_bone_idx]
                    boxBoneSettings = layout.box()
                    boxBoneSettings.label(text=t("bone_settings").format(active_bone.name), icon='BONE_DATA')
                    
                    selected_count = 0
                    if context.mode == 'EDIT':
                        try:
                            selected_count = len(context.selected_editable_bones)
                        except AttributeError:
                            pass
                    elif context.mode == 'POSE':
                        try:
                            selected_count = len(context.selected_pose_bones)
                        except AttributeError:
                            pass
                    if selected_count > 1:
                        boxBoneSettings.label(text=t("editing_selected_bones").format(selected_count), icon='LINKED')
                    
                    boxBoneSettings.prop(active_bone, "cobe_is_deform", text=t("is_deform"))
                    boxBoneSettings.prop(active_bone, "cobe_render_type", text=t("render_type"))
                    
            boxTex = layout.box()
            boxTex.label(text=t("texture_paths"), icon='IMAGE_DATA')
            boxTex.template_list("CobeTexturePathList", "", scene, "cobe_texture_paths", scene, "cobe_texture_paths_index")
            rowTex = boxTex.row(align=True)
            rowTex.operator("cobe.texture_path_action", text="+").action = 'ADD'
            rowTex.operator("cobe.texture_path_action", text="-").action = 'REMOVE'

        elif scene.cobe_ui_tab == 'ANIMATIONS':
            layout.prop(scene, "cobe_active_rig", text=t("active_rig"))
            boxAnim = layout.box()
            if armObj:
                boxAnim.prop_search(scene, "cobe_active_action_name", bpy.data, "actions", text=t("anim"))
                row = boxAnim.row(align=True)
                row.operator("cobe.create_animation", text=t("anim_new"))
                row.operator("cobe.delete_animation", text=t("anim_delete"))
                boxSettings = boxAnim.box()
                boxSettings.label(text=t("anim_settings"), icon='TIME')
                boxSettings.prop(scene, "cobe_anim_fps", text=t("fps"))
                boxSettings.prop(scene, "cobe_anim_speed", text=t("speed"))

        elif scene.cobe_ui_tab == 'EXPORT':
            layout.prop(scene, "cobe_active_rig", text=t("active_rig"))
            boxIo = layout.box()
            
            boxIo.prop(scene, "cobe_model_name", text=t("model_name"), icon='OBJECT_DATAMODE')
            
            row_scale = boxIo.row(align=True)
            row_scale.prop(scene, "cobe_scale_factor", text=t("scale_factor"))
            row_scale.prop(scene, "cobe_preview_active", text=t("preview_block_16"), toggle=True, icon='CUBE')
            
            boxList = boxIo.box()
            boxList.label(text=t("select_anims"), icon='ACTION')
            for action in bpy.data.actions:
                row = boxList.row(align=True)
                row.prop(action, "cobe_export_enabled", text="")
                row.label(text=action.name)
            rowMod = boxIo.row(align=True)
            rowMod.operator("cobe.export_json", text=t("export_json"))
            rowAnimIo = boxIo.row(align=True)
            rowAnimIo.operator("cobe.export_animations_json", text=t("export_anims"))
            if armObj and "cobe_null_pose" not in armObj.data:
                boxWarn = layout.box()
                boxWarn.alert = True
                boxWarn.label(text=t("warn_no_null_pose"), icon='ERROR')

        elif scene.cobe_ui_tab == 'LANGUAGES':
            boxLang = layout.box()
            translatorInstance = lang.Translator.getInstance()
            for code, name, _ in translatorInstance.availableLanguages:
                rowLang = boxLang.row()
                btnAction = rowLang.operator("cobe.set_language", text=name)
                btnAction.language_code = code
            boxLang.operator("cobe.reload_languages", text=t("reload_lang"), icon='FILE_REFRESH')
            boxLang.prop(scene, "cobe_show_debug", text=t("show_debug"))

class CobeUtilitiesPanel(bpy.types.Panel):
    bl_label = "Cobe Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cobe'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        armObj = scene.cobe_active_rig
        boxUtils = layout.box()
        boxUtils.operator("cobe.autogen_bones", text=t("btn_autogen"))
        boxUtils.operator("cobe.parent_bones_to_root", text=t("btn_parent_root"))
        boxUtils.operator("cobe.bake_bones", text=t("btn_bake"))
        if armObj:
            boxUtils.operator("cobe.bind_object_to_bone", text=t("bind_mesh"), icon='CONSTRAINT_BONE')

class CobeDebugPanel(bpy.types.Panel):
    bl_label = t("debug_menu_title")
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cobe'

    @classmethod
    def poll(cls, context):
        return context.scene.cobe_show_debug

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        armObj = scene.cobe_active_rig
        boxNull = layout.box()
        boxNull.label(text=t("null_pose_data"), icon='POSE_HLT')
        
        active_bone = None
        if context.mode == 'POSE' and context.active_pose_bone:
            active_bone = context.active_pose_bone.bone
        elif context.mode == 'EDIT' and context.active_bone:
            active_bone = context.active_bone
        elif armObj and context.mode == 'OBJECT' and armObj.data.bones.active:
            active_bone = armObj.data.bones.active
            
        if armObj:
            if active_bone:
                boxNull.label(text=t("selected_bone").format(active_bone.name), icon='BONE_DATA')
                if "cobe_null_pose" in armObj.data:
                    try:
                        pose_data = json.loads(armObj.data["cobe_null_pose"])
                        if active_bone.name in pose_data:
                            flat_mat = pose_data[active_bone.name]
                            mat = mathutils.Matrix([flat_mat[i:i+4] for i in range(0, 16, 4)])
                            loc, rot, scl = mat.decompose()
                            col = boxNull.column(align=True)
                            col.label(text=t("pivot_lbl"))
                            col.label(text=f"  X: {loc.x:.4f}, Y: {loc.y:.4f}, Z: {loc.z:.4f}")
                            col.label(text=t("roll_lbl"))
                            col.label(text=f"  W: {rot.w:.4f}, X: {rot.x:.4f}, Y: {rot.y:.4f}, Z: {rot.z:.4f}")
                            col.label(text=t("scale_lbl"))
                            col.label(text=f"  X: {scl.x:.4f}, Y: {scl.y:.4f}, Z: {scl.z:.4f}")
                        else:
                            boxNull.label(text=t("no_saved_data"), icon='ERROR')
                    except Exception as e:
                        boxNull.label(text=t("err_read_null_pose").format(e), icon='ERROR')
                else:
                    boxNull.label(text=t("null_pose_not_set"), icon='QUESTION')
            else:
                boxNull.label(text=t("select_bone_in_3d"), icon='QUESTION')
        else:
            boxNull.label(text=t("no_rig_found"), icon='ERROR')

def updateActiveAction(self, context):
    action = bpy.data.actions.get(self.cobe_active_action_name)
    armObj = context.scene.cobe_active_rig
    if armObj and action:
        if not armObj.animation_data: 
            armObj.animation_data_create()
        armObj.animation_data.action = action
        if hasattr(armObj.animation_data, "action_slot") and hasattr(action, "slots") and action.slots:
            armObj.animation_data.action_slot = action.slots[0]

def update_blender_fps(self, context):
    context.scene.render.fps = int(round(context.scene.cobe_anim_fps * context.scene.cobe_anim_speed))

def update_active_bone_index(self, context):
    if context.mode == 'EDIT':
        try:
            if 0 <= self.cobe_active_bone_index < len(self.bones):
                bone_name = self.bones[self.cobe_active_bone_index].name
                eb = self.edit_bones.get(bone_name)
                if eb:
                    self.edit_bones.active = eb
        except AttributeError:
            pass
    elif context.mode == 'POSE':
        try:
            if 0 <= self.cobe_active_bone_index < len(self.bones):
                bone_name = self.bones[self.cobe_active_bone_index].name
                b = self.bones.get(bone_name)
                if b:
                    self.bones.active = b
        except AttributeError:
            pass

def update_game_scale_preview(self, context):
    scene = context.scene
    ref_name = "Cobe_GameBlock_Reference"
    ref_obj = bpy.data.objects.get(ref_name)
    if scene.cobe_preview_active:
        if not ref_obj:
            mesh = bpy.data.meshes.new(ref_name + "_Mesh")
            ref_obj = bpy.data.objects.new(ref_name, mesh)
            context.collection.objects.link(ref_obj)
            import bmesh
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            bm.to_mesh(mesh)
            bm.free()
            ref_obj.display_type = 'WIRE'
            ref_obj.show_in_front = True
        size = 16.0 / max(0.001, scene.cobe_scale_factor)
        ref_obj.scale = (size, size, size)
        ref_obj.location = (0.0, 0.0, size / 2.0)
    else:
        if ref_obj:
            bpy.data.objects.remove(ref_obj, do_unlink=True)

def update_scale_factor(self, context):
    if context.scene.cobe_preview_active:
        update_game_scale_preview(self, context)

@bpy.app.handlers.persistent
def sync_cobe_active_bone(scene, *args):
    try:
        context = bpy.context
        obj = context.view_layer.objects.active
        if obj and obj.type == 'ARMATURE':
            arm = obj.data
            if context.mode == 'EDIT':
                active_eb = arm.edit_bones.active
                if active_eb:
                    idx = arm.bones.find(active_eb.name)
                    if idx != -1 and arm.cobe_active_bone_index != idx:
                        arm.cobe_active_bone_index = idx
            elif context.mode == 'POSE':
                active_pb = obj.pose.active_bone
                if active_pb:
                    idx = arm.bones.find(active_pb.name)
                    if idx != -1 and arm.cobe_active_bone_index != idx:
                        arm.cobe_active_bone_index = idx
    except Exception:
        pass

def get_cobe_is_deform(self):
    return self.get("cobe_is_deform_val", True)

def set_cobe_is_deform(self, value):
    self["cobe_is_deform_val"] = value
    context = bpy.context
    arm = self.id_data
    if not isinstance(arm, bpy.types.Armature):
        return
    selected_names = []
    if context.mode == 'EDIT':
        try:
            selected_names = [b.name for b in context.selected_editable_bones]
        except AttributeError:
            pass
    elif context.mode == 'POSE':
        try:
            selected_names = [b.name for b in context.selected_pose_bones]
        except AttributeError:
            pass
    else:
        selected_names = [b.name for b in arm.bones if b.select]
    if self.name in selected_names:
        for name in selected_names:
            b = arm.bones.get(name)
            if b:
                b["cobe_is_deform_val"] = value

def get_cobe_render_type(self):
    items = ['SOLID', 'CUTOUT_NO_CULL', 'CUTOUT', 'TRANSLUCENT']
    val = self.get("cobe_render_type_val", 'SOLID')
    try:
        return items.index(val)
    except ValueError:
        return 0

def set_cobe_render_type(self, value):
    items = ['SOLID', 'CUTOUT_NO_CULL', 'CUTOUT', 'TRANSLUCENT']
    val = items[value] if (0 <= value < len(items)) else 'SOLID'
    self["cobe_render_type_val"] = val
    context = bpy.context
    arm = self.id_data
    if not isinstance(arm, bpy.types.Armature):
        return
    selected_names = []
    if context.mode == 'EDIT':
        try:
            selected_names = [b.name for b in context.selected_editable_bones]
        except AttributeError:
            pass
    elif context.mode == 'POSE':
        try:
            selected_names = [b.name for b in context.selected_pose_bones]
        except AttributeError:
            pass
    else:
        selected_names = [b.name for b in arm.bones if b.select]
    if self.name in selected_names:
        for name in selected_names:
            b = arm.bones.get(name)
            if b:
                b["cobe_render_type_val"] = val

classes = [
    CobeTexturePath, CobeTexturePathList, COBE_OT_TexturePathAction,
    CobeBoneList, CobeBindObjectToBone, COBE_OT_ToggleGameScalePreview, operators.COBE_OT_SetLanguage, operators.COBE_OT_SetNullPose, operators.COBE_OT_ClearNullPose, 
    CobeMainPanel, CobeUtilitiesPanel, CobeDebugPanel,
    operators.COBE_OT_CreateBone, operators.COBE_OT_CreateChildBone, operators.COBE_OT_DeleteBone,
    operators.COBE_OT_RenameBone, operators.COBE_OT_RenameRig, operators.COBE_OT_CreateAnimation,
    operators.COBE_OT_DeleteAnimation, operators.COBE_OT_AutogenBones, operators.COBE_OT_BakeBones,           
    operators.COBE_OT_ParentBonesToRoot, exporter.CobeExportJson, exporter.CobeExportAnimationsJson
]

def register():
    lang.register()
    for cls in classes: 
        if issubclass(cls, bpy.types.Operator):
            @classmethod
            def dynamic_description(c, context, properties):
                key = c.bl_idname.replace(".", "_") + "_desc"
                desc = t(key)
                if desc == key:
                    return t(c.bl_idname.replace(".", "_") + "_lbl")
                return desc
            cls.description = dynamic_description
            
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.cobe_ui_tab = bpy.props.EnumProperty(items=getUiTabItems)
    bpy.types.Scene.cobe_rename_rig_name = bpy.props.StringProperty(default="CobeRig")
    bpy.types.Scene.cobe_rename_bone_name = bpy.props.StringProperty(default="new_bone")
    bpy.types.Scene.cobe_scale_factor = bpy.props.FloatProperty(default=16.0, min=0.001, update=update_scale_factor)
    bpy.types.Scene.cobe_texture_paths = bpy.props.CollectionProperty(type=CobeTexturePath)
    bpy.types.Scene.cobe_texture_paths_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.cobe_new_bone_name = bpy.props.StringProperty(default="bone")
    bpy.types.Scene.cobe_anim_fps = bpy.props.IntProperty(default=20, min=1, update=update_blender_fps)
    bpy.types.Scene.cobe_anim_speed = bpy.props.FloatProperty(default=1.0, min=0.001, update=update_blender_fps)
    bpy.types.Scene.cobe_active_action_name = bpy.props.StringProperty(update=updateActiveAction)
    bpy.types.Action.cobe_export_enabled = bpy.props.BoolProperty(default=False)
    
    bpy.types.Armature.cobe_active_bone_index = bpy.props.IntProperty(
        name="Active Bone Index",
        default=0,
        update=update_active_bone_index
    )
    
    bpy.types.Scene.cobe_language = bpy.props.EnumProperty(items=getLanguageItems, update=lang.updateLanguage)
    bpy.types.Scene.cobe_show_debug = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.cobe_active_rig = bpy.props.PointerProperty(type=bpy.types.Object, name="Active Rig", poll=lambda s, o: o.type == 'ARMATURE')
    bpy.types.Scene.cobe_preview_active = bpy.props.BoolProperty(name="Preview Active", default=False, update=update_game_scale_preview)
    
    bpy.types.Scene.cobe_model_name = bpy.props.StringProperty(default="CobeModel", name="Model Name")
    
    bpy.types.Bone.cobe_is_deform = bpy.props.BoolProperty(
        name="Is Deform",
        get=get_cobe_is_deform,
        set=set_cobe_is_deform,
        description="bone_is_deform_desc"
    )
    bpy.types.Bone.cobe_render_type = bpy.props.EnumProperty(
        items=[
            ('SOLID', 'Solid', ''),
            ('CUTOUT_NO_CULL', 'Cutout No Cull', ''),
            ('CUTOUT', 'Cutout', ''),
            ('TRANSLUCENT', 'Translucent', '')
        ],
        name="Render Type",
        get=get_cobe_render_type,
        set=set_cobe_render_type,
        description="bone_render_type_desc"
    )
    
    bpy.app.handlers.depsgraph_update_post.append(sync_cobe_active_bone)

def unregister():
    for cls in reversed(classes): 
        bpy.utils.unregister_class(cls)
    lang.unregister()
    
    del bpy.types.Scene.cobe_ui_tab
    del bpy.types.Scene.cobe_rename_rig_name
    del bpy.types.Scene.cobe_rename_bone_name
    del bpy.types.Scene.cobe_scale_factor
    del bpy.types.Scene.cobe_texture_paths
    del bpy.types.Scene.cobe_texture_paths_index
    del bpy.types.Scene.cobe_new_bone_name
    del bpy.types.Scene.cobe_anim_fps
    del bpy.types.Scene.cobe_anim_speed
    del bpy.types.Scene.cobe_active_action_name
    del bpy.types.Action.cobe_export_enabled
    del bpy.types.Armature.cobe_active_bone_index
    if hasattr(bpy.types.Scene, "cobe_language"):
        del bpy.types.Scene.cobe_language
    del bpy.types.Scene.cobe_show_debug
    del bpy.types.Scene.cobe_active_rig
    del bpy.types.Scene.cobe_preview_active
    del bpy.types.Scene.cobe_model_name
    del bpy.types.Bone.cobe_is_deform
    del bpy.types.Bone.cobe_render_type
    
    if sync_cobe_active_bone in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(sync_cobe_active_bone)