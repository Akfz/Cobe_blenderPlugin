import bpy
import json
import math
import traceback
import mathutils
from .lang import t
from .prefs import tag_redraw
from .utils import (
    enter_armature_edit_mode,
    exit_armature_edit_mode,
    get_parent_bone_name,
    assign_action_to_armature,
    is_exportable_action
)


def restore_armature_mode(previous_mode):
    target_mode = 'OBJECT'

    if previous_mode == 'EDIT_ARMATURE':
        target_mode = 'EDIT'
    elif previous_mode == 'POSE':
        target_mode = 'POSE'

    try:
        bpy.ops.object.mode_set(mode=target_mode)
    except Exception:
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass


class COBE_OT_TexturePathAction(bpy.types.Operator):
    bl_idname = "cobe.texture_path_action"
    bl_label = "Texture Action"

    action: bpy.props.EnumProperty(items=[
        ('ADD', "Add", ""),
        ('REMOVE', "Remove", "")
    ])

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("texture_action")
        return True

    def execute(self, context):
        scene = context.scene

        if self.action == 'ADD':
            scene.cobe_texture_paths.add()
        elif self.action == 'REMOVE':
            index = scene.cobe_texture_paths_index
            if 0 <= index < len(scene.cobe_texture_paths):
                scene.cobe_texture_paths.remove(index)
                scene.cobe_texture_paths_index = max(0, index - 1)

        return {'FINISHED'}


class COBE_OT_CreateRootBone(bpy.types.Operator):
    bl_idname = "cobe.create_root_bone"
    bl_label = "Create Root"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("create_root")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            arm_obj = context.active_object

        if not arm_obj or arm_obj.type != 'ARMATURE':
            rig_name = scene.cobe_rename_rig_name if scene.cobe_rename_rig_name else "CobeRig"
            arm_data = bpy.data.armatures.new(name=rig_name)
            arm_obj = bpy.data.objects.new(name=rig_name, object_data=arm_data)
            context.collection.objects.link(arm_obj)
            arm_obj.show_name = False
            arm_obj.show_in_front = True
            arm_obj.data.show_names = True
            context.view_layer.objects.active = arm_obj
            arm_obj.select_set(True)

        scene.cobe_active_rig = arm_obj
        arm_data = arm_obj.data
        bone_name = scene.cobe_new_bone_name if scene.cobe_new_bone_name else "root"

        previous_mode, need_switch = enter_armature_edit_mode(context, arm_obj)

        root_bone = arm_data.edit_bones.new(bone_name)
        root_bone.head = mathutils.Vector((0.0, 0.0, 0.0))
        root_bone.tail = mathutils.Vector((0.0, 0.0, 1.0))

        new_bone_name = root_bone.name

        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        index = arm_data.bones.find(new_bone_name)
        if index != -1:
            arm_data.cobe_active_bone_index = index

        restore_armature_mode(previous_mode)
        self.report({'INFO'}, new_bone_name)
        return {'FINISHED'}


class COBE_OT_CreateChildBone(bpy.types.Operator):
    bl_idname = "cobe.create_child_bone"
    bl_label = "Create Child Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("create_child_bone")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            arm_obj = context.active_object

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("not_armature"))
            return {'CANCELLED'}

        scene.cobe_active_rig = arm_obj
        arm_data = arm_obj.data
        parent_name = get_parent_bone_name(context, arm_obj)

        if not parent_name:
            parent_bone = next((bone for bone in arm_data.bones if not bone.parent), None)
            if parent_bone:
                parent_name = parent_bone.name

        if not parent_name:
            self.report({'ERROR'}, t("select_parent"))
            return {'CANCELLED'}

        parent_deform = True
        parent_bone_data = arm_data.bones.get(parent_name)
        if parent_bone_data:
            parent_deform = parent_bone_data.cobe_is_deform

        previous_mode, need_switch = enter_armature_edit_mode(context, arm_obj)
        parent = arm_data.edit_bones.get(parent_name)

        if not parent:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

            restore_armature_mode(previous_mode)
            self.report({'ERROR'}, t("parent_not_found"))
            return {'CANCELLED'}

        bone_name = scene.cobe_new_bone_name if scene.cobe_new_bone_name else "child_bone"
        new_bone = arm_data.edit_bones.new(bone_name)
        new_bone.parent = parent
        new_bone.head = parent.tail.copy()
        new_bone.tail = parent.tail + mathutils.Vector((0.0, 0.0, 0.5))

        new_bone_name = new_bone.name

        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        child_bone = arm_data.bones.get(new_bone_name)
        if child_bone:
            child_bone["cobe_is_deform_val"] = parent_deform

        index = arm_data.bones.find(new_bone_name)
        if index != -1:
            arm_data.cobe_active_bone_index = index

        restore_armature_mode(previous_mode)
        self.report({'INFO'}, t("child_created").format(new_bone_name))
        return {'FINISHED'}


class COBE_OT_DeleteBone(bpy.types.Operator):
    bl_idname = "cobe.delete_bone"
    bl_label = "Delete Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("delete_bone_op")
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
        index = arm_data.cobe_active_bone_index

        if index < 0 or index >= len(arm_data.bones):
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        bone_name = arm_data.bones[index].name
        previous_mode, need_switch = enter_armature_edit_mode(context, arm_obj)
        edit_bone = arm_data.edit_bones.get(bone_name)

        if edit_bone:
            arm_data.edit_bones.remove(edit_bone)
            deleted = True
        else:
            deleted = False

        exit_armature_edit_mode(context, previous_mode, need_switch)

        if deleted:
            arm_data.cobe_active_bone_index = max(0, index - 1)
            self.report({'INFO'}, t("bone_deleted").format(bone_name))
            return {'FINISHED'}

        self.report({'ERROR'}, t("parent_not_found"))
        return {'CANCELLED'}


class COBE_OT_RenameBone(bpy.types.Operator):
    bl_idname = "cobe.rename_bone"
    bl_label = "Rename Bone"
    bl_options = {'REGISTER', 'UNDO'}

    new_name: bpy.props.StringProperty(name="New Name")

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("rename_bone_op")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        arm_data = arm_obj.data
        index = arm_data.cobe_active_bone_index

        if index < 0 or index >= len(arm_data.bones):
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        bone = arm_data.bones[index]
        old_name = bone.name
        new_name = self.new_name

        if not new_name:
            self.report({'ERROR'}, t("enter_new_bone"))
            return {'CANCELLED'}

        bone.name = new_name

        for texture_path in scene.cobe_texture_paths:
            if texture_path.bone_name == old_name:
                texture_path.bone_name = new_name

        self.report({'INFO'}, t("bone_renamed").format(old_name, new_name))
        return {'FINISHED'}

    def invoke(self, context, event):
        arm_obj = context.scene.cobe_active_rig

        if arm_obj and arm_obj.type == 'ARMATURE':
            arm_data = arm_obj.data
            index = arm_data.cobe_active_bone_index
            if 0 <= index < len(arm_data.bones):
                self.new_name = arm_data.bones[index].name

        return context.window_manager.invoke_props_dialog(self)


class COBE_OT_RenameRig(bpy.types.Operator):
    bl_idname = "cobe.rename_rig"
    bl_label = "Rename Rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("rename_rig_op")
        return True

    def execute(self, context):
        scene = context.scene
        new_name = scene.cobe_rename_rig_name

        if not new_name:
            self.report({'ERROR'}, t("enter_new_rig"))
            return {'CANCELLED'}

        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        arm_obj.name = new_name
        arm_obj.data.name = new_name

        self.report({'INFO'}, t("rig_renamed").format(new_name))
        return {'FINISHED'}


class COBE_OT_CreateAnimation(bpy.types.Operator):
    bl_idname = "cobe.create_animation"
    bl_label = "Create Animation"
    bl_options = {'REGISTER', 'UNDO'}

    animName: bpy.props.StringProperty(default="new_animation")

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("create_anim_op")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            arm_obj = context.active_object

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("create_skeleton_first"))
            return {'CANCELLED'}

        scene.cobe_active_rig = arm_obj

        new_action = bpy.data.actions.new(name=self.animName)
        new_action.use_fake_user = True

        if hasattr(new_action, "slots"):
            try:
                new_action.slots.new(id_type='OBJECT', name=arm_obj.name)
            except Exception:
                pass

        new_action.cobe_export_enabled = True
        assign_action_to_armature(arm_obj, new_action)
        scene.cobe_active_action_name = new_action.name

        self.report({'INFO'}, t("anim_created").format(new_action.name))
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class COBE_OT_DeleteAnimation(bpy.types.Operator):
    bl_idname = "cobe.delete_animation"
    bl_label = "Delete Animation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("delete_anim_op")
        return True

    def execute(self, context):
        scene = context.scene
        arm_obj = scene.cobe_active_rig

        if not arm_obj or not arm_obj.animation_data or not arm_obj.animation_data.action:
            self.report({'ERROR'}, t("no_active_anim"))
            return {'CANCELLED'}

        action_to_delete = arm_obj.animation_data.action
        action_name = action_to_delete.name

        bpy.data.actions.remove(action_to_delete)

        candidates = [action for action in bpy.data.actions if is_exportable_action(action)]

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

        self.report({'INFO'}, t("anim_deleted").format(action_name))
        return {'FINISHED'}


class COBE_OT_AutogenBones(bpy.types.Operator):
    bl_idname = "cobe.autogen_bones"
    bl_label = "Autogenerate Bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("autogen_op")
        return True

    def execute(self, context):
        scene = context.scene
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_meshes:
            self.report({'ERROR'}, t("select_mesh"))
            return {'CANCELLED'}

        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            active_obj = context.active_object
            if active_obj and active_obj.type == 'ARMATURE':
                arm_obj = active_obj

        if not arm_obj:
            arm_name = scene.cobe_rename_rig_name if scene.cobe_rename_rig_name else "CobeRig"
            arm_data = bpy.data.armatures.new(name=arm_name)
            arm_obj = bpy.data.objects.new(name=arm_name, object_data=arm_data)
            context.collection.objects.link(arm_obj)
            arm_obj.show_name = False
            arm_obj.show_in_front = True
            arm_obj.data.show_names = True

        scene.cobe_active_rig = arm_obj

        mesh_matrices = {mesh.name: mesh.matrix_world.copy() for mesh in selected_meshes}

        previous_mode, need_switch = enter_armature_edit_mode(context, arm_obj)
        edit_bones = arm_obj.data.edit_bones

        created = 0
        freed = 0
        bone_names = {}

        for mesh_obj in selected_meshes:
            pivot = mesh_matrices[mesh_obj.name].to_translation()
            existing = edit_bones.get(mesh_obj.name)

            if existing:
                existing.head = pivot
                existing.tail = pivot + mathutils.Vector((0.0, 0.2, 0.0))
                existing.parent = None
                existing.use_connect = False
                freed += 1
                bone_names[mesh_obj.name] = existing.name
            else:
                new_bone = edit_bones.new(name=mesh_obj.name)
                new_bone.head = pivot
                new_bone.tail = pivot + mathutils.Vector((0.0, 0.2, 0.0))
                new_bone.parent = None
                new_bone.use_connect = False
                created += 1
                bone_names[mesh_obj.name] = new_bone.name

        exit_armature_edit_mode(context, previous_mode, need_switch)

        for mesh_obj in selected_meshes:
            bone_name = bone_names.get(mesh_obj.name)
            if not bone_name:
                continue

            mesh_obj.parent = arm_obj
            mesh_obj.parent_type = 'BONE'
            mesh_obj.parent_bone = bone_name
            mesh_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            mesh_obj.matrix_world = mesh_matrices[mesh_obj.name]

        msg = t("bones_created").format(created)
        if freed:
            msg += f" (+{freed} freed)"

        self.report({'INFO'}, msg)
        return {'FINISHED'}


class COBE_OT_ParentBonesToRoot(bpy.types.Operator):
    bl_idname = "cobe.parent_bones_to_root"
    bl_label = "Bind Selected to Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("parent_root_op")
        return True

    def _collect_selected_bone_names(self, context, arm_obj):
        """Собирает имена выделенных костей из текущего режима (EDIT / POSE / OBJECT)."""
        names = []

        try:
            if context.mode == 'EDIT':
                names = [bone.name for bone in context.selected_editable_bones]
            elif context.mode == 'POSE':
                names = [pose_bone.name for pose_bone in context.selected_pose_bones]
            else:
                names = [bone.name for bone in arm_obj.data.bones if bone.select]
        except Exception:
            names = []

        if not names:
            index = getattr(arm_obj.data, "cobe_active_bone_index", 0)
            if 0 <= index < len(arm_obj.data.bones):
                names = [arm_obj.data.bones[index].name]

        return names

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

        target_index = getattr(arm_data, "cobe_active_bone_index", 0)
        target_name = None

        if 0 <= target_index < len(arm_data.bones):
            target_name = arm_data.bones[target_index].name

        if not target_name:
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        selected_names = self._collect_selected_bone_names(context, arm_obj)

        if not selected_names:
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        previous_mode, need_switch = enter_armature_edit_mode(context, arm_obj)
        edit_bones = arm_obj.data.edit_bones

        target_bone = edit_bones.get(target_name)

        if not target_bone:
            exit_armature_edit_mode(context, previous_mode, need_switch)
            self.report({'ERROR'}, t("parent_not_found"))
            return {'CANCELLED'}

        count = 0
        skipped_cycle = 0

        for bone_name in selected_names:
            if bone_name == target_name:
                continue

            edit_bone = edit_bones.get(bone_name)
            if not edit_bone:
                continue

            parent_check = target_bone
            is_cycle = False
            while parent_check:
                if parent_check == edit_bone:
                    is_cycle = True
                    break
                parent_check = parent_check.parent

            if is_cycle:
                skipped_cycle += 1
                continue

            edit_bone.parent = target_bone
            count += 1

        exit_armature_edit_mode(context, previous_mode, need_switch)

        if skipped_cycle:
            self.report({'WARNING'}, f"{t('bones_linked').format(count)} (skipped {skipped_cycle} cyclic)")
        else:
            self.report({'INFO'}, t("bones_linked").format(count))

        return {'FINISHED'}


class COBE_OT_BakeBones(bpy.types.Operator):
    bl_idname = "cobe.bake_bones"
    bl_label = "Bake Physics"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("bake_op")
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
        mappings = []

        for pose_bone in arm_obj.pose.bones:
            mesh_obj = bpy.data.objects.get(pose_bone.name)
            if mesh_obj and mesh_obj.type == 'MESH':
                mappings.append((pose_bone, mesh_obj))

        if not mappings:
            self.report({'ERROR'}, t("no_meshes_found"))
            return {'CANCELLED'}

        action_name = "baked_animation"
        action = bpy.data.actions.get(action_name)

        if not action:
            action = bpy.data.actions.new(name=action_name)
            action.use_fake_user = True
            if hasattr(action, "slots"):
                try:
                    action.slots.new(id_type='OBJECT', name=arm_obj.name)
                except Exception:
                    pass

        action.cobe_export_enabled = True
        assign_action_to_armature(arm_obj, action)
        scene.cobe_active_action_name = action.name

        original_frame = scene.frame_current

        for frame in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(frame)
            for pose_bone, mesh_obj in mappings:
                target_matrix = arm_obj.matrix_world.inverted() @ mesh_obj.matrix_world
                pose_bone.matrix = target_matrix
                pose_bone.keyframe_insert(data_path="location", frame=frame)

                if pose_bone.rotation_mode == 'QUATERNION':
                    pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                else:
                    pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame)

                pose_bone.keyframe_insert(data_path="scale", frame=frame)

        scene.frame_set(original_frame)
        self.report({'INFO'}, t("bones_baked").format(len(mappings)))
        return {'FINISHED'}


class COBE_OT_SetNullPose(bpy.types.Operator):
    bl_idname = "cobe.set_null_pose"
    bl_label = "Set Null Pose"

    def execute(self, context):
        arm_obj = context.scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            arm_obj = context.active_object

        if not arm_obj or arm_obj.type != 'ARMATURE':
            return {'CANCELLED'}

        pose_dict = {}
        for pose_bone in arm_obj.pose.bones:
            pose_dict[pose_bone.name] = [value for row in pose_bone.matrix for value in row]

        arm_obj.data["cobe_null_pose"] = json.dumps(pose_dict)
        tag_redraw()
        return {'FINISHED'}


class COBE_OT_ClearNullPose(bpy.types.Operator):
    bl_idname = "cobe.clear_null_pose"
    bl_label = "Clear Null Pose"

    def execute(self, context):
        arm_obj = context.scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            return {'CANCELLED'}

        if "cobe_null_pose" in arm_obj.data:
            del arm_obj.data["cobe_null_pose"]

        tag_redraw()
        return {'FINISHED'}


class COBE_OT_ResetToNullPose(bpy.types.Operator):
    bl_idname = "cobe.reset_to_null_pose"
    bl_label = "Reset to Null Pose"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("reset_to_null_pose_op")
        arm_obj = context.scene.cobe_active_rig
        return arm_obj is not None and "cobe_null_pose" in arm_obj.data

    def execute(self, context):
        arm_obj = context.scene.cobe_active_rig

        if not arm_obj:
            return {'CANCELLED'}

        if "cobe_null_pose" not in arm_obj.data:
            self.report({'ERROR'}, t("null_pose_not_set"))
            return {'CANCELLED'}

        try:
            pose_dict = json.loads(arm_obj.data["cobe_null_pose"])

            for pose_bone in arm_obj.pose.bones:
                if pose_bone.name in pose_dict:
                    flat_matrix = pose_dict[pose_bone.name]
                    pose_bone.matrix = mathutils.Matrix([flat_matrix[i:i + 4] for i in range(0, 16, 4)])

            context.view_layer.update()
            self.report({'INFO'}, t("rig_reset_to_null"))
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, t("err_read_null_pose").format(error))
            return {'CANCELLED'}


def collect_meshes_for_texture(context):
    meshes = []

    for obj in context.selected_objects:
        if obj.type == 'MESH':
            meshes.append(obj)

    active_obj = context.active_object

    if active_obj and active_obj.type == 'ARMATURE':
        arm_obj = active_obj
        selected_bone_names = []

        if context.mode == 'POSE':
            selected_bone_names = [pose_bone.name for pose_bone in (context.selected_pose_bones or [])]
        elif context.mode == 'EDIT':
            try:
                selected_bone_names = [edit_bone.name for edit_bone in arm_obj.data.edit_bones if edit_bone.select]
            except Exception:
                selected_bone_names = []
        else:
            index = arm_obj.data.cobe_active_bone_index
            if 0 <= index < len(arm_obj.data.bones):
                selected_bone_names = [arm_obj.data.bones[index].name]

        for bone_name in selected_bone_names:
            for child in arm_obj.children:
                if child.type == 'MESH' and child.parent_type == 'BONE' and child.parent_bone == bone_name:
                    if child not in meshes:
                        meshes.append(child)

    return meshes


def create_texture_material(scene):
    image_name = scene.cobe_texture_name
    width = scene.cobe_texture_width
    height = scene.cobe_texture_height

    image = bpy.data.images.get(image_name)
    if not image:
        image = bpy.data.images.new(name=image_name, width=width, height=height, alpha=True)
        image.pixels = [1.0] * (width * height * 4)

    material_name = image_name + "_Mat"
    material = bpy.data.materials.get(material_name)

    if not material:
        material = bpy.data.materials.new(name=material_name)
        material.use_nodes = True

        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
        texture_node = nodes.new(type='ShaderNodeTexImage')

        texture_node.image = image
        texture_node.interpolation = 'Closest'
        texture_node.extension = 'CLIP'

        output_node.location = (300, 0)
        principled_node.location = (10, 0)
        texture_node.location = (-300, 0)

        links.new(texture_node.outputs['Color'], principled_node.inputs['Base Color'])
        links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
    else:
        if material.node_tree:
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    node.image = image
                    node.interpolation = 'Closest'
                    node.extension = 'CLIP'

    return material, width, height


def collect_mesh_sizes(meshes):
    sizes = []

    for obj in meshes:
        mesh = obj.data
        coords = [vertex.co for vertex in mesh.vertices]

        if not coords:
            continue

        min_x = round(min(co.x for co in coords), 4)
        max_x = round(max(co.x for co in coords), 4)
        min_y = round(min(co.y for co in coords), 4)
        max_y = round(max(co.y for co in coords), 4)
        min_z = round(min(co.z for co in coords), 4)
        max_z = round(max(co.z for co in coords), 4)

        size_x = max(0.001, max_x - min_x)
        size_y = max(0.001, max_y - min_y)
        size_z = max(0.001, max_z - min_z)

        sizes.append({
            'obj': obj,
            'size_x': size_x,
            'size_y': size_y,
            'size_z': size_z,
            'w_m': 2.0 * size_y + 2.0 * size_x,
            'h_m': size_y + size_z,
            'min_x': min_x,
            'max_x': max_x,
            'min_y': min_y,
            'max_y': max_y,
            'min_z': min_z,
            'max_z': max_z
        })

    return sizes


def pack_texture_islands(mesh_sizes, width, height, padding):
    if not mesh_sizes:
        return None, 0.0

    avail_w = max(1.0, width - 2 * padding)
    avail_h = max(1.0, height - 2 * padding)

    if len(mesh_sizes) == 1:
        pixels_per_unit = min(avail_w / mesh_sizes[0]['w_m'], avail_h / mesh_sizes[0]['h_m'])
    else:
        max_single_w = max(item['w_m'] for item in mesh_sizes)
        max_single_h = max(item['h_m'] for item in mesh_sizes)
        pixels_per_unit = min(avail_w / max_single_w, avail_h / max_single_h)

    total_area = sum(item['w_m'] * item['h_m'] for item in mesh_sizes)
    if total_area > 0.0:
        pixels_per_unit = min(pixels_per_unit, math.sqrt((avail_w * avail_h) / total_area))

    for attempt in range(150):
        positions = {}
        sorted_sizes = sorted(mesh_sizes, key=lambda item: item['h_m'] * pixels_per_unit, reverse=True)

        current_x = padding
        current_y = padding
        row_height = 0
        failed = False

        for item in sorted_sizes:
            x_px = int(round(item['size_x'] * pixels_per_unit))
            y_px = int(round(item['size_y'] * pixels_per_unit))
            z_px = int(round(item['size_z'] * pixels_per_unit))

            w_px = 2 * y_px + 2 * x_px
            h_px = y_px + z_px

            if current_x + w_px + padding > width:
                current_x = padding
                current_y += row_height + padding
                row_height = 0

            if current_y + h_px + padding > height:
                failed = True
                break

            positions[item['obj'].name] = (current_x, current_y)
            current_x += w_px + padding
            row_height = max(row_height, h_px)

        if not failed:
            return positions, pixels_per_unit

        pixels_per_unit /= 1.1
        if pixels_per_unit < 0.05:
            break

    return None, 0.0


def assign_mesh_uv(mesh, item, pixels_per_unit, offset_u, offset_v, width, height):
    if not mesh.uv_layers:
        mesh.uv_layers.new()

    uv_layer = mesh.uv_layers.active

    x_px = int(round(item['size_x'] * pixels_per_unit))
    y_px = int(round(item['size_y'] * pixels_per_unit))
    z_px = int(round(item['size_z'] * pixels_per_unit))

    directions = [
        (mathutils.Vector((1, 0, 0)), 'RIGHT'),
        (mathutils.Vector((-1, 0, 0)), 'LEFT'),
        (mathutils.Vector((0, 1, 0)), 'BACK'),
        (mathutils.Vector((0, -1, 0)), 'FRONT'),
        (mathutils.Vector((0, 0, 1)), 'TOP'),
        (mathutils.Vector((0, 0, -1)), 'BOTTOM'),
    ]

    for poly in mesh.polygons:
        normal = poly.normal
        best_dir = 'FRONT'
        best_dot = -2.0

        for vector, name in directions:
            dot = normal.dot(vector)
            if dot > best_dot:
                best_dot = dot
                best_dir = name

        poly_u_values = []
        poly_v_values = []

        for loop_index in poly.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            vertex_co = mesh.vertices[vertex_index].co

            x = round(vertex_co.x, 4)
            y = round(vertex_co.y, 4)
            z = round(vertex_co.z, 4)

            if best_dir == 'LEFT':
                u_value, v_value = y, z
            elif best_dir == 'FRONT':
                u_value, v_value = x, z
            elif best_dir == 'RIGHT':
                u_value, v_value = -y, z
            elif best_dir == 'BACK':
                u_value, v_value = -x, z
            elif best_dir == 'TOP':
                u_value, v_value = x, -y
            else:
                u_value, v_value = x, y

            poly_u_values.append(u_value)
            poly_v_values.append(v_value)

        min_poly_u = min(poly_u_values)
        max_poly_u = max(poly_u_values)
        min_poly_v = min(poly_v_values)
        max_poly_v = max(poly_v_values)

        if best_dir == 'LEFT':
            min_u_m, max_u_m = item['min_y'], item['max_y']
            min_v_m, max_v_m = item['min_z'], item['max_z']
            u_px_size, v_px_size = y_px, z_px
            u_face_offset, v_face_offset = 0, 0
        elif best_dir == 'FRONT':
            min_u_m, max_u_m = item['min_x'], item['max_x']
            min_v_m, max_v_m = item['min_z'], item['max_z']
            u_px_size, v_px_size = x_px, z_px
            u_face_offset, v_face_offset = y_px, 0
        elif best_dir == 'RIGHT':
            min_u_m, max_u_m = -item['max_y'], -item['min_y']
            min_v_m, max_v_m = item['min_z'], item['max_z']
            u_px_size, v_px_size = y_px, z_px
            u_face_offset, v_face_offset = y_px + x_px, 0
        elif best_dir == 'BACK':
            min_u_m, max_u_m = -item['max_x'], -item['min_x']
            min_v_m, max_v_m = item['min_z'], item['max_z']
            u_px_size, v_px_size = x_px, z_px
            u_face_offset, v_face_offset = y_px + x_px + y_px, 0
        elif best_dir == 'TOP':
            min_u_m, max_u_m = item['min_x'], item['max_x']
            min_v_m, max_v_m = -item['max_y'], -item['min_y']
            u_px_size, v_px_size = x_px, y_px
            u_face_offset, v_face_offset = y_px, z_px
        else:
            min_u_m, max_u_m = item['min_x'], item['max_x']
            min_v_m, max_v_m = item['min_y'], item['max_y']
            u_px_size, v_px_size = x_px, y_px
            u_face_offset, v_face_offset = y_px + x_px, z_px

        size_u_m = max(0.001, max_u_m - min_u_m)
        size_v_m = max(0.001, max_v_m - min_v_m)

        poly_u_min_px = int(round(((min_poly_u - min_u_m) / size_u_m) * u_px_size))
        poly_u_max_px = int(round(((max_poly_u - min_u_m) / size_u_m) * u_px_size))
        poly_v_min_px = int(round(((min_poly_v - min_v_m) / size_v_m) * v_px_size))
        poly_v_max_px = int(round(((max_poly_v - min_v_m) / size_v_m) * v_px_size))

        for i, loop_index in enumerate(poly.loop_indices):
            u_value = poly_u_values[i]
            v_value = poly_v_values[i]

            u_is_min = abs(u_value - min_poly_u) < abs(u_value - max_poly_u)
            v_is_min = abs(v_value - min_poly_v) < abs(v_value - max_poly_v)

            u_px = poly_u_min_px if u_is_min else poly_u_max_px
            v_px = poly_v_min_px if v_is_min else poly_v_max_px

            u_scaled = u_px + u_face_offset + offset_u
            v_scaled = v_px + v_face_offset + offset_v

            uv_layer.data[loop_index].uv = (u_scaled / width, v_scaled / height)


class COBE_OT_GenerateTextureUv(bpy.types.Operator):
    bl_idname = "cobe.generate_texture_uv"
    bl_label = "Generate Texture & UV"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("generate_tex_uv")
        return True

    def execute(self, context):
        try:
            scene = context.scene
            meshes = collect_meshes_for_texture(context)

            if not meshes:
                self.report({'ERROR'}, t("no_meshes_selected"))
                return {'CANCELLED'}

            material, width, height = create_texture_material(scene)

            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

            bpy.ops.object.select_all(action='DESELECT')

            for obj in meshes:
                context.view_layer.objects.active = obj
                obj.select_set(True)

                if not obj.data.materials:
                    obj.data.materials.append(material)
                else:
                    obj.data.materials[0] = material

            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            mesh_sizes = collect_mesh_sizes(meshes)
            if not mesh_sizes:
                self.report({'ERROR'}, t("no_meshes_selected"))
                return {'CANCELLED'}

            padding = max(0, int(round(scene.cobe_uv_margin * width)))
            positions, pixels_per_unit = pack_texture_islands(mesh_sizes, width, height, padding)

            if positions is None:
                self.report({'ERROR'}, t("tex_uv_no_space"))
                return {'CANCELLED'}

            for item in mesh_sizes:
                offset_u, offset_v = positions[item['obj'].name]
                assign_mesh_uv(item['obj'].data, item, pixels_per_unit, offset_u, offset_v, width, height)

            if context.screen:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                space.shading.type = 'MATERIAL'

            self.report({'INFO'}, t("tex_uv_success"))
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            traceback.print_exc()
            return {'CANCELLED'}


class CobeBindObjectToBone(bpy.types.Operator):
    bl_idname = "cobe.bind_object_to_bone"
    bl_label = "Bind Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("bind_mesh")
        return True

    def execute(self, context):
        arm_obj = context.scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            arm_obj = context.active_object

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("err_no_active_rig"))
            return {'CANCELLED'}

        context.scene.cobe_active_rig = arm_obj
        arm_data = arm_obj.data
        index = arm_data.cobe_active_bone_index

        if index < 0 or index >= len(arm_data.bones):
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        target_bone = arm_data.bones[index]
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_meshes:
            self.report({'ERROR'}, t("select_mesh"))
            return {'CANCELLED'}

        for mesh_obj in selected_meshes:
            matrix_world = mesh_obj.matrix_world.copy()
            mesh_obj.parent = arm_obj
            mesh_obj.parent_type = 'BONE'
            mesh_obj.parent_bone = target_bone.name
            mesh_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            mesh_obj.matrix_world = matrix_world

        return {'FINISHED'}


classes = (
    COBE_OT_TexturePathAction,
    COBE_OT_CreateRootBone,
    COBE_OT_CreateChildBone,
    COBE_OT_DeleteBone,
    COBE_OT_RenameBone,
    COBE_OT_RenameRig,
    COBE_OT_CreateAnimation,
    COBE_OT_DeleteAnimation,
    COBE_OT_AutogenBones,
    COBE_OT_ParentBonesToRoot,
    COBE_OT_BakeBones,
    COBE_OT_SetNullPose,
    COBE_OT_ClearNullPose,
    COBE_OT_ResetToNullPose,
    COBE_OT_GenerateTextureUv,
    CobeBindObjectToBone
)
