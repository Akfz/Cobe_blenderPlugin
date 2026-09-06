import bpy
from .lang import t
from .utils import assign_action_to_armature, is_exportable_action
from .exporter import update_hitbox_preview_toggle, refresh_hitbox_preview

class CobeTexturePath(bpy.types.PropertyGroup):
    bone_name: bpy.props.StringProperty(default="root")
    texture_path: bpy.props.StringProperty(default="textures/entity/model.png")

SCENE_PROPERTY_NAMES = (
    "cobe_ui_tab",
    "cobe_active_rig",
    "cobe_rename_rig_name",
    "cobe_new_bone_name",
    "cobe_texture_paths",
    "cobe_texture_paths_index",
    "cobe_anim_speed",
    "cobe_active_action_name",
    "cobe_model_name",
    "cobe_texture_name",
    "cobe_texture_width",
    "cobe_texture_height",
    "cobe_uv_margin",
    "cobe_scale_factor",
    "cobe_preview_active",
    "cobe_anim_fps",
    "cobe_hitbox_detail",
    "cobe_hitbox_preview_active"
)

def remove_property(owner, name):
    try:
        if hasattr(owner, name):
            delattr(owner, name)
    except Exception:
        pass

def get_ui_tab_items(self, context):
    return [
        ('RIG', t("tab_rig"), ''),
        ('ANIMATIONS', t("tab_animations"), ''),
        ('EXPORT', t("tab_export"), ''),
        ('LANGUAGES', t("tab_languages"), '')
    ]

def get_scene_prop(scene, name, default=None):
    try:
        return getattr(scene, name, default)
    except Exception:
        return default

def get_current_action(scene):
    try:
        arm_obj = get_scene_prop(scene, "cobe_active_rig")
        action = None

        if arm_obj and arm_obj.animation_data and arm_obj.animation_data.action:
            action = arm_obj.animation_data.action

        if not action:
            action_name = get_scene_prop(scene, "cobe_active_action_name", "")
            if action_name:
                action = bpy.data.actions.get(action_name)

        if action and is_exportable_action(action):
            return action
    except Exception:
        pass

    return None

def get_current_action_fps(scene):
    try:
        arm_obj = get_scene_prop(scene, "cobe_active_rig")
        if arm_obj:
            return getattr(arm_obj, "cobe_anim_fps", 20)
    except Exception:
        pass

    return 20

def update_scene_fps(context):
    try:
        scene = context.scene
        fps = get_current_action_fps(scene)
        speed = float(get_scene_prop(scene, "cobe_anim_speed", 1.0))
        scene.render.fps = max(1, int(round(fps * speed)))
    except Exception:
        pass

def update_speed(self, context):
    update_scene_fps(context)

def update_object_fps(self, context):
    try:
        scene = context.scene
        if scene.cobe_active_rig == self:
            update_scene_fps(context)
    except Exception:
        pass

def update_active_action(self, context):
    try:
        scene = context.scene
        arm_obj = get_scene_prop(scene, "cobe_active_rig")
        action_name = get_scene_prop(scene, "cobe_active_action_name", "")
        action = bpy.data.actions.get(action_name) if action_name else None

        if arm_obj and action and is_exportable_action(action):
            assign_action_to_armature(arm_obj, action)

        update_scene_fps(context)
    except Exception:
        pass

def update_active_bone_index(self, context):
    try:
        index = self.cobe_active_bone_index

        if index < 0 or index >= len(self.bones):
            return

        bone_name = self.bones[index].name

        if context.mode == 'EDIT':
            edit_bone = self.edit_bones.get(bone_name)
            if edit_bone:
                self.edit_bones.active = edit_bone
        elif context.mode == 'POSE':
            bone = self.bones.get(bone_name)
            if bone:
                self.bones.active = bone
    except Exception:
        pass

def get_cobe_is_deform(self):
    return self.get("cobe_is_deform_val", True)

def set_cobe_is_deform(self, value):
    self["cobe_is_deform_val"] = value
    armature = self.id_data

    if not isinstance(armature, bpy.types.Armature):
        return

    context = bpy.context
    selected_names = []

    if context.mode == 'EDIT':
        try:
            selected_names = [bone.name for bone in context.selected_editable_bones]
        except Exception:
            selected_names = []
    elif context.mode == 'POSE':
        try:
            selected_names = [bone.name for bone in context.selected_pose_bones]
        except Exception:
            selected_names = []
    else:
        selected_names = [bone.name for bone in armature.bones if bone.select]

    if self.name in selected_names:
        for bone_name in selected_names:
            bone = armature.bones.get(bone_name)
            if bone:
                bone["cobe_is_deform_val"] = value

def update_game_scale_preview(self, context):
    try:
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
    except Exception:
        pass

def update_scale_factor(self, context):
    try:
        if context.scene.cobe_preview_active:
            update_game_scale_preview(self, context)
    except Exception:
        pass

def register_properties():
    for name in SCENE_PROPERTY_NAMES:
        remove_property(bpy.types.Scene, name)

    remove_property(bpy.types.Object, "cobe_anim_fps")
    remove_property(bpy.types.Action, "cobe_anim_fps")
    remove_property(bpy.types.Action, "cobe_export_enabled")
    remove_property(bpy.types.Armature, "cobe_active_bone_index")
    remove_property(bpy.types.Bone, "cobe_is_deform")

    bpy.types.Scene.cobe_ui_tab = bpy.props.EnumProperty(items=get_ui_tab_items)

    bpy.types.Scene.cobe_active_rig = bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Active Rig",
        poll=lambda self, obj: obj is not None and obj.type == 'ARMATURE'
    )

    bpy.types.Scene.cobe_rename_rig_name = bpy.props.StringProperty(default="CobeRig")
    bpy.types.Scene.cobe_new_bone_name = bpy.props.StringProperty(default="bone")
    bpy.types.Scene.cobe_texture_paths = bpy.props.CollectionProperty(type=CobeTexturePath)
    bpy.types.Scene.cobe_texture_paths_index = bpy.props.IntProperty(default=0)

    bpy.types.Scene.cobe_anim_speed = bpy.props.FloatProperty(default=1.0, min=0.001, update=update_speed)
    bpy.types.Scene.cobe_active_action_name = bpy.props.StringProperty(update=update_active_action)

    bpy.types.Object.cobe_anim_fps = bpy.props.IntProperty(default=20, min=1, update=update_object_fps)
    bpy.types.Action.cobe_export_enabled = bpy.props.BoolProperty(default=False)

    bpy.types.Armature.cobe_active_bone_index = bpy.props.IntProperty(default=0, update=update_active_bone_index)
    bpy.types.Bone.cobe_is_deform = bpy.props.BoolProperty(get=get_cobe_is_deform, set=set_cobe_is_deform)

    bpy.types.Scene.cobe_model_name = bpy.props.StringProperty(default="CobeModel", name="Model Name")
    bpy.types.Scene.cobe_texture_name = bpy.props.StringProperty(default="model_texture", name="Texture Name")
    bpy.types.Scene.cobe_texture_width = bpy.props.IntProperty(default=64, min=8, max=8192, name="Texture Width")
    bpy.types.Scene.cobe_texture_height = bpy.props.IntProperty(default=32, min=8, max=8192, name="Texture Height")
    bpy.types.Scene.cobe_uv_margin = bpy.props.FloatProperty(default=0.02, min=0.0, max=1.0, precision=4, name="UV Margin")

    bpy.types.Scene.cobe_scale_factor = bpy.props.FloatProperty(default=16.0, min=0.001, update=update_scale_factor)
    bpy.types.Scene.cobe_preview_active = bpy.props.BoolProperty(default=False, update=update_game_scale_preview)

    bpy.types.Scene.cobe_hitbox_detail = bpy.props.IntProperty(
        default=50,
        min=1,
        max=100,
        name="Hitbox Detail"
    )
    
    bpy.types.Scene.cobe_hitbox_detail = bpy.props.IntProperty(
        default=50,
        min=1,
        max=100,
        name="Hitbox Detail",
        update=refresh_hitbox_preview
    )

    bpy.types.Scene.cobe_hitbox_preview_active = bpy.props.BoolProperty(
        default=False,
        name="Preview Hitboxes",
        update=update_hitbox_preview_toggle
    )

def unregister_properties():
    for name in SCENE_PROPERTY_NAMES:
        remove_property(bpy.types.Scene, name)

    remove_property(bpy.types.Object, "cobe_anim_fps")
    remove_property(bpy.types.Action, "cobe_anim_fps")
    remove_property(bpy.types.Action, "cobe_export_enabled")
    remove_property(bpy.types.Armature, "cobe_active_bone_index")
    remove_property(bpy.types.Bone, "cobe_is_deform")

classes = (
    CobeTexturePath,
)